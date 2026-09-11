"""Coordinator: owns desired policy, pushes it, and merges DPC reports."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    DeviceStatus,
    LocalMdmAuthError,
    LocalMdmClient,
    LocalMdmConnectionError,
    LocalMdmPolicyRefusedError,
)
from .const import DOMAIN, POLICY_KIOSK_PACKAGES
from .policy import InvalidPolicyError, UnsafePolicyError, default_policy, validate_policy

_LOGGER = logging.getLogger(__name__)

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
        return await self._fetch()

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
        return True

    async def async_set_policy_flag(self, key: str, value: bool) -> None:
        """Change one flag in the desired policy and push the whole document."""
        await self.async_apply_policy({**self.desired_policy, key: value})

    async def async_set_kiosk_packages(self, packages: list[str]) -> None:
        """Replace the kiosk package list and push."""
        await self.async_apply_policy({**self.desired_policy, POLICY_KIOSK_PACKAGES: packages})

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
