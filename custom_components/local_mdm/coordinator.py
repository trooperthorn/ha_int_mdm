"""Coordinator: owns desired policy, pushes it, and merges DPC reports."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import (
    DeviceStatus,
    LocalMdmAuthError,
    LocalMdmClient,
    LocalMdmConnectionError,
    LocalMdmError,
    LocalMdmPolicyRefusedError,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_MAC,
    DOMAIN,
    POLICY_ALLOWED_PACKAGES,
    POLICY_KIOSK_PACKAGES,
)
from .policy import InvalidPolicyError, UnsafePolicyError, default_policy, validate_policy
from .unifi import async_ip_for_macs, async_mac_for_ip

_LOGGER = logging.getLogger(__name__)

# A report that disagrees with the desired policy triggers one re-push, at
# most this often, so a tablet that keeps refusing cannot be hammered.
RECONCILE_MIN_INTERVAL = 30.0
# A tablet that stops answering is looked up in UniFi by MAC, and a new
# address probed, at most this often.
RELOCATE_MIN_INTERVAL = 60.0

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
        # False until the tablet has answered once since this entry loaded.
        # Until then desired_policy is a placeholder, and treating it as the
        # truth would push "everything off" over a tablet that was merely
        # offline while Home Assistant started.
        self._policy_known = False
        self._push_lock = asyncio.Lock()
        self._last_reconcile: float | None = None
        self._last_relocate: float | None = None
        self._known_mac: str | None = None
        self._webhook_url: str | None = None
        self._webhook_pending = False
        # The DPC's status document only tracks the outcome of install_package
        # (last_install); lock_screen, reboot, and configure_wifi answer
        # {"ok": true} with nothing to poll afterwards, so their result is
        # recorded here instead, one entry per action, keyed by the sensor's
        # translation key.
        self.last_actions: dict[str, dict[str, Any]] = {}

    def _record_action(self, key: str, *, message: str | None = None) -> None:
        """Record the outcome of an immediate action and notify listeners."""
        self.last_actions[key] = {
            "result": "error" if message else "ok",
            "message": message,
            "at": dt_util.utcnow().isoformat(),
        }
        self.async_update_listeners()

    @property
    def policy_known(self) -> bool:
        """True once the tablet's applied policy has been read."""
        return self._policy_known

    async def _async_setup(self) -> None:
        # The tablet's applied policy is the source of truth after a restart;
        # the DPC persists it, Home Assistant does not. An unreachable tablet
        # leaves the policy unknown until its first answer (_on_status).
        status = await self._fetch()
        if status.is_reachable:
            self._adopt_policy(status)

    def _adopt_policy(self, status: DeviceStatus) -> None:
        try:
            self.desired_policy = validate_policy(status.policy)
        except (UnsafePolicyError, InvalidPolicyError) as err:
            _LOGGER.warning(
                "DPC reported a policy this integration cannot own (%s); using defaults", err
            )
            self.desired_policy = default_policy()
        self._policy_version = max(self._policy_version, status.policy_version)
        self._policy_known = True

    async def _async_update_data(self) -> DeviceStatus:
        status = await self._fetch()
        self._on_status(status)
        return status

    def _on_status(self, status: DeviceStatus, *, via_webhook: bool = False) -> None:
        """Bookkeeping shared by polls and webhook reports; runs before data is replaced."""
        if status.is_reachable:
            came_back = self.data is not None and not self.data.is_reachable
            if not self._policy_known:
                self._adopt_policy(status)
            if via_webhook:
                # The report arrived, so the tablet holds a working URL.
                self._webhook_pending = False
            elif self._webhook_pending or came_back:
                # A tablet that was away may have missed a changed Home
                # Assistant address; resending the URL is cheap.
                self._schedule_webhook()
        self._reconcile_if_drifted(status)
        self._sync_mac(status)

    async def async_send_webhook(self, url: str) -> None:
        """Tell the tablet where to report; retried when it is next reachable.

        An unreachable tablet is not a setup failure: the URL is kept and sent
        again on the tablet's next answer. Only a rejected token raises.
        """
        self._webhook_url = url
        try:
            await self.client.async_set_webhook(url)
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmError as err:
            _LOGGER.debug("Webhook URL not delivered yet (%s); will resend", err)
            self._webhook_pending = True
        else:
            self._webhook_pending = False

    def _schedule_webhook(self) -> None:
        if self._webhook_url is None:
            return
        # Cleared now so the next poll does not queue a duplicate; the send
        # sets it again if it fails.
        self._webhook_pending = False
        self.config_entry.async_create_background_task(
            self.hass, self._resend_webhook(self._webhook_url), f"{DOMAIN}_webhook"
        )

    async def _resend_webhook(self, url: str) -> None:
        try:
            await self.async_send_webhook(url)
        except ConfigEntryAuthFailed:
            self.config_entry.async_start_reauth(self.hass)

    def _sync_mac(self, status: DeviceStatus) -> None:
        """Register the tablet's Wi-Fi MAC as a device connection.

        With a MAC connection the device merges with the same tablet in any
        integration keyed by MAC, the UniFi Network client above all. The DPC
        reports the MAC in use only where Android still honours the Device
        Owner exemption (Android 16 does not), so the fallbacks are the MAC of
        the UniFi client the entry was paired from, then the UniFi tracker
        whose IP is this tablet's host: both are the MAC the access point sees.
        """
        mac = status.wifi_mac or self.config_entry.data.get(CONF_MAC) or self._mac_from_unifi()
        if not mac or mac == self._known_mac:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, status.device_id), self.config_entry.entry_id
        )
        if device is None:
            return
        registry.async_update_device(
            device.id, new_connections=device.connections | {(dr.CONNECTION_NETWORK_MAC, mac)}
        )
        self._known_mac = mac

    def _mac_from_unifi(self) -> str | None:
        host = self.config_entry.data.get(CONF_HOST)
        return async_mac_for_ip(self.hass, host) if host else None

    def _known_macs(self) -> set[str]:
        """Every MAC this tablet is known by: entry data and device connections."""
        macs: set[str] = set()
        if mac := self.config_entry.data.get(CONF_MAC):
            macs.add(mac)
        device = dr.async_get(self.hass).async_get_device_by_identifier(
            (DOMAIN, self.config_entry.data[CONF_DEVICE_ID]), self.config_entry.entry_id
        )
        if device is not None:
            macs.update(
                value for kind, value in device.connections if kind == dr.CONNECTION_NETWORK_MAC
            )
        return macs

    async def _relocate(self) -> DeviceStatus | None:
        """Follow a tablet whose address changed, using UniFi's view of its MAC.

        With a fixed IP in UniFi this should not fire; it covers a missing or
        mistyped reservation. The new address is adopted only when the tablet
        there accepts the stored token and reports this entry's device id, so
        a stale tracker cannot redirect the entry to another device.
        """
        now = time.monotonic()
        if self._last_relocate is not None and now - self._last_relocate < RELOCATE_MIN_INTERVAL:
            return None
        macs = self._known_macs()
        if not macs:
            return None
        ip = async_ip_for_macs(self.hass, macs)
        if ip is None or ip == self.client.host:
            return None
        self._last_relocate = now
        candidate = self.client.with_host(ip)
        try:
            status = await candidate.async_get_status()
        except LocalMdmError as err:
            _LOGGER.debug("UniFi places the tablet at %s but it did not answer: %s", ip, err)
            return None
        if status.device_id != self.config_entry.data[CONF_DEVICE_ID]:
            _LOGGER.warning(
                "UniFi places this tablet's MAC at %s, but the device there is %s; not following",
                ip,
                status.device_id,
            )
            return None
        _LOGGER.info(
            "Tablet moved from %s to %s (found through UniFi); following it", self.client.host, ip
        )
        self.client = candidate
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: ip}
        )
        return status

    def _reconcile_if_drifted(self, status: DeviceStatus) -> None:
        """Re-push the desired policy when the tablet reports a different one.

        A push sent while the tablet is still booting can be acknowledged and
        then lost to the boot-time re-apply (seen after a firmware update on
        2026-09-11). Home Assistant owns the desired policy after setup, so a
        report that disagrees is drift, not a new source of truth.
        """
        if (
            not status.is_reachable
            or not self._policy_known
            or self.data is None
            or self._push_lock.locked()
        ):
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
        """Fetch the tablet's status, or fall back to it being unreachable.

        A tablet that is asleep, mid-reboot, or off Wi-Fi must not block this
        config entry from loading, nor make every entity unavailable for as
        long as the retry backoff takes: connectivity is data
        (DeviceStatus.is_reachable), not a coordinator failure. Only a bad
        token is treated as an integration failure, since that needs reauth
        rather than a retry.
        """
        try:
            return await self.client.async_get_status()
        except LocalMdmAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmConnectionError as err:
            if (status := await self._relocate()) is not None:
                return status
            _LOGGER.debug("Tablet unreachable (%s); keeping the last-known status", err)
            base = self.data or DeviceStatus.offline(self.config_entry.data[CONF_DEVICE_ID])
            return replace(base, is_reachable=False)

    async def _async_ensure_policy_known(self) -> None:
        """Read the tablet's policy before building a change on top of it.

        Every write merges into desired_policy, so writing while it is still
        the placeholder would turn off whatever the tablet has on.
        """
        if self._policy_known:
            return
        status = await self._fetch()
        if not status.is_reachable:
            raise HomeAssistantError(
                "The tablet has not answered since Home Assistant started, so its "
                "current policy is unknown; nothing was sent"
            )
        self._adopt_policy(status)
        self.async_set_updated_data(status)

    def async_handle_push(self, payload: dict[str, Any]) -> bool:
        """Accept a webhook report; returns False when it is not for this device."""
        try:
            status = DeviceStatus.from_payload(payload)
        except ValueError as err:
            _LOGGER.warning("Ignoring malformed DPC report: %s", err)
            return False
        expected = self.config_entry.data[CONF_DEVICE_ID]
        if status.device_id != expected:
            _LOGGER.warning(
                "Ignoring report from device %s on the webhook for %s", status.device_id, expected
            )
            return False
        self._policy_version = max(self._policy_version, status.policy_version)
        self._on_status(status, via_webhook=True)
        self.async_set_updated_data(status)
        return True

    async def async_set_policy_flag(self, key: str, value: bool) -> None:
        """Change one flag in the desired policy and push the whole document."""
        await self._async_ensure_policy_known()
        await self.async_apply_policy({**self.desired_policy, key: value})

    async def async_set_kiosk_packages(self, packages: list[str]) -> None:
        """Replace the kiosk package list and push."""
        await self._async_ensure_policy_known()
        await self.async_apply_policy({**self.desired_policy, POLICY_KIOSK_PACKAGES: packages})

    async def async_approve_package(self, package: str) -> None:
        """Approve a package held by the allowlist: add it and push."""
        await self._async_ensure_policy_known()
        current = list(self.desired_policy.get(POLICY_ALLOWED_PACKAGES, []))
        if package not in current:
            current.append(package)
        await self.async_set_policy_value(POLICY_ALLOWED_PACKAGES, current)

    async def async_set_policy_value(self, key: str, value: Any) -> None:
        """Change one non-flag value (app mode, allowed packages) and push."""
        await self._async_ensure_policy_known()
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
            self._record_action("last_lock_screen", message=str(err))
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmConnectionError as err:
            self._record_action("last_lock_screen", message=str(err))
            raise HomeAssistantError(f"Could not lock the screen: {err}") from err
        self._record_action("last_lock_screen")

    async def async_reboot(self) -> None:
        """Reboot the tablet now."""
        try:
            await self.client.async_reboot()
        except LocalMdmAuthError as err:
            self._record_action("last_reboot", message=str(err))
            raise ConfigEntryAuthFailed(str(err)) from err
        except (LocalMdmPolicyRefusedError, LocalMdmConnectionError) as err:
            self._record_action("last_reboot", message=str(err))
            raise HomeAssistantError(f"Could not reboot: {err}") from err
        self._record_action("last_reboot")

    async def async_configure_wifi(self, ssid: str, password: str | None, hidden: bool) -> None:
        """Provision a Wi-Fi network on the tablet."""
        try:
            await self.client.async_configure_wifi(ssid, password, hidden)
        except LocalMdmAuthError as err:
            self._record_action("last_configure_wifi", message=str(err))
            raise ConfigEntryAuthFailed(str(err)) from err
        except LocalMdmPolicyRefusedError as err:
            self._record_action("last_configure_wifi", message=str(err))
            raise HomeAssistantError(f"DPC refused the Wi-Fi network: {err}") from err
        except LocalMdmConnectionError as err:
            self._record_action("last_configure_wifi", message=str(err))
            raise HomeAssistantError(f"Could not configure Wi-Fi: {err}") from err
        self._record_action("last_configure_wifi")

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
