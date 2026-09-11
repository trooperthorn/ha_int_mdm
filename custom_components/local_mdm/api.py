"""Async HTTP client for the Local MDM Device Policy Controller.

This module imports nothing from Home Assistant. Coordinator and entity code
translate its exceptions; templates and diagnostics see only the dataclasses
defined here. docs/protocol.md documents the wire contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    ENFORCEMENT_APPLIED,
    REQUEST_TIMEOUT,
    TIER_ADMIN,
    TIER_LIMITS,
    TIER_NONE,
    TIER_OWNER,
)
from .policy import validate_policy

API_VERSION = "v1"


class LocalMdmError(Exception):
    """Base error for the DPC client."""


class LocalMdmConnectionError(LocalMdmError):
    """The DPC did not answer or answered with a transport error."""


class LocalMdmAuthError(LocalMdmError):
    """The DPC rejected the bearer token."""


class LocalMdmPolicyRefusedError(LocalMdmError):
    """The DPC refused a policy, for example a kiosk with no packages."""


def _tier(payload: dict[str, Any]) -> str:
    """Tier from the payload; older DPCs only send is_device_owner."""
    tier = payload.get("tier")
    if tier in (TIER_OWNER, TIER_ADMIN, TIER_NONE):
        return str(tier)
    return TIER_OWNER if payload.get("is_device_owner") else TIER_NONE


@dataclass(frozen=True)
class DeviceStatus:
    """Snapshot of the tablet as reported by the DPC."""

    device_id: str
    dpc_version: str
    is_device_owner: bool
    policy_version: int
    policy: dict[str, Any]
    enforcement: dict[str, str]
    lock_task_active: bool
    tier: str = TIER_NONE
    battery_level: int | None = None
    battery_charging: bool | None = None
    wifi_connected: bool | None = None
    wifi_enabled: bool | None = None
    wifi_ssid: str | None = None
    reported_at: str | None = None
    os_release: str | None = None
    security_patch: str | None = None
    os_build: str | None = None
    update_pending: bool | None = None
    update_received_at: str | None = None
    installed: dict[str, str | None] = field(default_factory=dict)
    last_install: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def enforcement_failures(self) -> list[str]:
        """Policy keys the DPC reported as anything other than applied."""
        return sorted(
            k
            for k, v in self.enforcement.items()
            if v != ENFORCEMENT_APPLIED and v not in TIER_LIMITS
        )

    @property
    def tier_limited(self) -> list[str]:
        """Policy keys the tier cannot fully enforce (limited or unsupported)."""
        return sorted(k for k, v in self.enforcement.items() if v in TIER_LIMITS)

    def is_enforced(self, key: str) -> bool:
        """True when the DPC reports ``key`` on and applied."""
        return bool(self.policy.get(key)) and self.enforcement.get(key) == ENFORCEMENT_APPLIED

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DeviceStatus:
        """Build a status from a JSON body, raising ValueError when malformed."""
        try:
            device_id = str(payload["device_id"])
            policy = dict(payload.get("policy") or {})
            enforcement = {str(k): str(v) for k, v in (payload.get("enforcement") or {}).items()}
            battery = payload.get("battery") or {}
            network = payload.get("network") or {}
            os_info = payload.get("os") or {}
            update = payload.get("system_update") or {}
            installed = {str(k): _opt_str(v) for k, v in (payload.get("installed") or {}).items()}
            last_install = payload.get("last_install")
            return cls(
                device_id=device_id,
                dpc_version=str(payload.get("dpc_version", "unknown")),
                is_device_owner=bool(payload.get("is_device_owner", False)),
                policy_version=int(payload.get("policy_version", 0)),
                tier=_tier(payload),
                policy=policy,
                enforcement=enforcement,
                lock_task_active=bool(payload.get("lock_task_active", False)),
                battery_level=_opt_int(battery.get("level")),
                battery_charging=_opt_bool(battery.get("charging")),
                wifi_connected=_opt_bool(network.get("wifi_connected")),
                wifi_enabled=_opt_bool(network.get("wifi_enabled")),
                wifi_ssid=_opt_str(network.get("ssid")),
                reported_at=_opt_str(payload.get("reported_at")),
                os_release=_opt_str(os_info.get("release")),
                security_patch=_opt_str(os_info.get("security_patch")),
                os_build=_opt_str(os_info.get("build")),
                update_pending=_opt_bool(update.get("pending")),
                update_received_at=_opt_str(update.get("received_at")),
                installed=installed,
                last_install=dict(last_install) if isinstance(last_install, dict) else None,
                raw=payload,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise ValueError(f"Malformed DPC status payload: {err}") from err


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _opt_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


class LocalMdmClient:
    """Talk to one DPC over HTTP on the local network."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        token: str,
        *,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/{API_VERSION}"
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _request(self, method: str, path: str, json: Any = None) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=json,
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                if response.status in (401, 403):
                    raise LocalMdmAuthError("DPC rejected the token")
                if response.status == 422:
                    detail = await _safe_text(response)
                    raise LocalMdmPolicyRefusedError(detail or "DPC refused the policy")
                if response.status >= 400:
                    detail = await _safe_text(response)
                    raise LocalMdmConnectionError(f"DPC returned HTTP {response.status}: {detail}")
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise LocalMdmConnectionError(f"Cannot reach DPC: {err}") from err
        if not isinstance(body, dict):
            raise LocalMdmConnectionError("DPC returned a non-object JSON body")
        return body

    async def async_get_status(self) -> DeviceStatus:
        """Fetch the current status document."""
        body = await self._request("GET", "/status")
        try:
            return DeviceStatus.from_payload(body)
        except ValueError as err:
            raise LocalMdmConnectionError(str(err)) from err

    async def async_set_policy(self, policy: dict[str, Any], version: int) -> DeviceStatus:
        """Validate, then push a full policy document; returns the post-apply status."""
        safe = validate_policy(policy)
        body = await self._request("PUT", "/policy", {"version": version, "policy": safe})
        try:
            return DeviceStatus.from_payload(body)
        except ValueError as err:
            raise LocalMdmConnectionError(str(err)) from err

    async def async_set_webhook(self, url: str) -> None:
        """Tell the DPC where to POST state reports."""
        await self._request("PUT", "/webhook", {"url": url})

    async def async_lock_screen(self) -> None:
        """Lock the tablet screen immediately."""
        await self._request("POST", "/actions/lock_screen")

    async def async_reboot(self) -> None:
        """Reboot the tablet (Device Owner only)."""
        await self._request("POST", "/actions/reboot")

    async def async_install_package(self, url: str, sha256: str | None = None) -> None:
        """Ask the DPC to download and silently install an APK.

        The DPC answers 202 as soon as the download starts; progress and the
        outcome arrive through the status document's ``last_install``.
        """
        body: dict[str, str] = {"url": url}
        if sha256:
            body["sha256"] = sha256.lower().removeprefix("sha256:")
        await self._request("POST", "/actions/install_package", body)

    async def async_configure_wifi(self, ssid: str, password: str | None, hidden: bool) -> None:
        """Hand a Wi-Fi network to the tablet; Android stores it, the DPC does not."""
        body: dict[str, Any] = {"ssid": ssid, "hidden": hidden}
        if password:
            body["password"] = password
        await self._request("POST", "/actions/configure_wifi", body)


async def _safe_text(response: aiohttp.ClientResponse) -> str:
    try:
        return (await response.text())[:200]
    except aiohttp.ClientError, UnicodeDecodeError:
        return ""
