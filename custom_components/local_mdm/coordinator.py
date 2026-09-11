"""Coordinator: owns desired policy, pushes it, and merges DPC reports."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DeviceStatus,
    LocalMdmAuthError,
    LocalMdmClient,
    LocalMdmConnectionError,
    LocalMdmPolicyRefusedError,
)
from .const import DOMAIN, POLICY_ALLOWED_PACKAGES, POLICY_KIOSK_PACKAGES
from .policy import InvalidPolicyError, UnsafePolicyError, default_policy, validate_policy

_LOGGER = logging.getLogger(__name__)

# A report that disagrees with the desired policy triggers one re-push, at
# most this often, so a tablet that keeps refusing cannot be hammered.
RECONCILE_MIN_INTERVAL = 30.0
# The UniFi Network integration; its client trackers carry ip and mac attributes.
UNIFI_DOMAIN = "unifi"

type LocalMdmConfigEntry = ConfigEntry[LocalMdmCoordinator]


class LocalMdmCoordinator(DataUpdateCoordinator[DeviceStatus]):
    """Push-first (webhook) with a polling fallback."""

    config_entry: LocalMdmConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LocalMdmConfigEntry,
        client: LocalMdmClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.desired_policy: dict[str, Any] = default_policy()
        self._policy_version = 0
        self._push_lock = asyncio.Lock()
        self._last_reconcile: float | None = None
        self._known_mac: str | None = None

    async def _async_setup(self) -> None:
        # The tablet's applied policy is the source of truth after a restart;
        # the DPC persists it, Home Assistant does not.
        status = await self._fetch()
        try:
            self.desired_policy = validate_policy(status.policy)
        except (UnsafePolicyError, InvalidPolicyError) as err:
            _LOGGER.warning(
                "DPC reported a policy this integration cannot own (%s); using defaults", err
            )
            self.desired_policy = default_policy()
        self._policy_version = status.policy_version

    async def _async_update_data(self) -> DeviceStatus:
        status = await self._fetch()
        self._reconcile_if_drifted(status)
        self._sync_mac(status)
        return status

    def _sync_mac(self, status: DeviceStatus) -> None:
        """Register the tablet's Wi-Fi MAC as a device connection.

        With a MAC connection the device merges with the same tablet in any
        integration keyed by MAC, the UniFi Network client above all. The DPC
        reports the MAC in use only where Android still honours the Device
        Owner exemption (Android 16 does not), so the fallback is the UniFi
        tracker whose IP is this tablet's host: it carries the randomised MAC
        the access point actually sees.
        """
        mac = status.wifi_mac or self._mac_from_unifi()
        if not mac or mac == self._known_mac:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, status.device_id)})
        if device is None:
            return
        registry.async_update_device(
            device.id, merge_connections={(dr.CONNECTION_NETWORK_MAC, mac)}
        )
        self._known_mac = mac

    def _mac_from_unifi(self) -> str | None:
        host = self.config_entry.data.get(CONF_HOST)
        if not host:
            return None
        ent_reg = er.async_get(self.hass)
        for state in self.hass.states.async_all("device_tracker"):
            if state.attributes.get("ip") != host:
                continue
            entry = ent_reg.async_get(state.entity_id)
            if entry is None or entry.platform != UNIFI_DOMAIN:
                continue
            mac = state.attributes.get("mac")
            if isinstance(mac, str) and len(mac) == 17:
                return mac.lower()
        return None

    def _reconcile_if_drifted(self, status: DeviceStatus) -> None:
        """Re-push the desired policy when the tablet reports a different one.

        A push sent while the tablet is still booting can be acknowledged and
        then lost to the boot-time re-apply (seen after a firmware update on
        2026-09-11). Home Assistant owns the desired policy after setup, so a
        report that disagrees is drift, not a new source of truth.
        """
        if self.data is None or self._push_lock.locked():
            return
        try:
            reported = validate_policy(status.policy)
        except UnsafePolicyError, InvalidPolicyError:
            return
        if reported == self.desired_policy:
            return
        now = time.monotonic()
        if self._last_reconcile is not None and now - self._last_reconcile < RECONCILE_MIN_INTERVAL:
            return
        self._last_reconcile = now
        _LOGGER.info("Tablet policy drifted from the desired policy; re-pushing")
        self.config_entry.async_create_background_task(
            self.hass, self._reconcile(), f"{DOMAIN}_reconcile"
        )

    async def _reconcile(self) -> None:
        try:
            await self.async_apply_policy(self.desired_policy)
        except HomeAssistantError as err:
            _LOGGER.warning("Re-push after drift failed: %s", err)

    async def _fetch(self) -> DeviceStatus:
        try:
            return await self.client.async_get_status()
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmConnectionError as err:
            raise UpdateFailed(str(err)) from err

    def async_handle_push(self, payload: dict[str, Any]) -> bool:
        """Accept a webhook report; returns False when it is not for this device."""
        try:
            status = DeviceStatus.from_payload(payload)
        except ValueError as err:
            _LOGGER.warning("Ignoring malformed DPC report: %s", err)
            return False
        if self.data is not None and status.device_id != self.data.device_id:
            _LOGGER.warning(
                "Ignoring report from device %s on the webhook for %s",
                status.device_id,
                self.data.device_id,
            )
            return False
        self._policy_version = max(self._policy_version, status.policy_version)
        self.async_set_updated_data(status)
        self._reconcile_if_drifted(status)
        self._sync_mac(status)
        return True

    async def async_set_policy_flag(self, key: str, value: bool) -> None:
        """Change one flag in the desired policy and push the whole document."""
        await self.async_apply_policy({**self.desired_policy, key: value})

    async def async_set_kiosk_packages(self, packages: list[str]) -> None:
        """Replace the kiosk package list and push."""
        await self.async_apply_policy({**self.desired_policy, POLICY_KIOSK_PACKAGES: packages})

    async def async_approve_package(self, package: str) -> None:
        """Approve a package held by the allowlist: add it and push."""
        current = list(self.desired_policy.get(POLICY_ALLOWED_PACKAGES, []))
        if package not in current:
            current.append(package)
        await self.async_set_policy_value(POLICY_ALLOWED_PACKAGES, current)

    async def async_set_policy_value(self, key: str, value: Any) -> None:
        """Change one non-flag value (app mode, allowed packages) and push."""
        await self.async_apply_policy({**self.desired_policy, key: value})

    async def async_apply_policy(self, policy: dict[str, Any]) -> None:
        """Validate and push a full policy; raises HomeAssistantError on refusal."""
        try:
            safe = validate_policy(policy)
        except (UnsafePolicyError, InvalidPolicyError) as err:
            raise HomeAssistantError(f"Policy refused before sending: {err}") from err

        async with self._push_lock:
            version = self._policy_version + 1
            try:
                status = await self.client.async_set_policy(safe, version)
            except LocalMdmAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except LocalMdmPolicyRefusedError as err:
                raise HomeAssistantError(f"DPC refused the policy: {err}") from err
            except LocalMdmConnectionError as err:
                raise HomeAssistantError(f"Could not push policy: {err}") from err
            self.desired_policy = safe
            self._policy_version = max(version, status.policy_version)
            self.async_set_updated_data(status)

    async def async_lock_screen(self) -> None:
        """Lock the screen now."""
        try:
            await self.client.async_lock_screen()
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmConnectionError as err:
            raise HomeAssistantError(f"Could not lock the screen: {err}") from err

    async def async_reboot(self) -> None:
        """Reboot the tablet now."""
        try:
            await self.client.async_reboot()
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (LocalMdmPolicyRefusedError, LocalMdmConnectionError) as err:
            raise HomeAssistantError(f"Could not reboot: {err}") from err

    async def async_configure_wifi(self, ssid: str, password: str | None, hidden: bool) -> None:
        """Provision a Wi-Fi network on the tablet."""
        try:
            await self.client.async_configure_wifi(ssid, password, hidden)
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmPolicyRefusedError as err:
            raise HomeAssistantError(f"DPC refused the Wi-Fi network: {err}") from err
        except LocalMdmConnectionError as err:
            raise HomeAssistantError(f"Could not configure Wi-Fi: {err}") from err

    async def async_install_package(self, url: str, sha256: str | None) -> None:
        """Start a silent APK install; the result arrives as a report."""
        try:
            await self.client.async_install_package(url, sha256)
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmPolicyRefusedError as err:
            raise HomeAssistantError(f"DPC refused the install: {err}") from err
        except LocalMdmConnectionError as err:
            raise HomeAssistantError(f"Could not start the install: {err}") from err
