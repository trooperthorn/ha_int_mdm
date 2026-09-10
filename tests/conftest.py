"""Shared fixtures: a fake DPC client and a configured entry."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_mdm.api import (
    DeviceStatus,
    LocalMdmAuthError,
    LocalMdmConnectionError,
    LocalMdmPolicyRefusedError,
)
from custom_components.local_mdm.const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DOMAIN,
    ENFORCEMENT_APPLIED,
    POLICY_FLAGS,
)
from custom_components.local_mdm.policy import validate_policy

pytest_plugins = "pytest_homeassistant_custom_component"

DEVICE_ID = "tablet-kitchen"
TOKEN = "pairing-token-123"
WEBHOOK_ID = "a" * 64


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def status_payload(**overrides: Any) -> dict[str, Any]:
    """A complete DPC status document with every flag off."""
    policy = dict.fromkeys(POLICY_FLAGS, False)
    policy["kiosk_packages"] = []
    payload: dict[str, Any] = {
        "device_id": DEVICE_ID,
        "dpc_version": "2026.09.10.1",
        "is_device_owner": True,
        "policy_version": 3,
        "policy": policy,
        "enforcement": dict.fromkeys(POLICY_FLAGS, ENFORCEMENT_APPLIED),
        "lock_task_active": False,
        "battery": {"level": 87, "charging": True},
        "network": {"wifi_connected": True},
        "reported_at": "2026-09-10T12:00:00+00:00",
        "os": {
            "release": "15",
            "sdk": 35,
            "security_patch": "2024-09-05",
            "build": "AE3A.240806.043",
        },
        "system_update": {"policy": 1, "pending": False},
        "installed": {"io.homeassistant.companion.android": "2026.6.5"},
    }
    payload.update(overrides)
    return payload


class FakeClient:
    """Stands in for LocalMdmClient; behaves like a compliant DPC."""

    def __init__(self) -> None:
        self.payload = status_payload()
        self.webhook_url: str | None = None
        self.policy_calls: list[tuple[dict[str, Any], int]] = []
        self.lock_calls = 0
        self.fail_with: Exception | None = None
        self.webhook_fail_with: Exception | None = None

    def _raise_if_failing(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def async_get_status(self) -> DeviceStatus:
        self._raise_if_failing()
        return DeviceStatus.from_payload(copy.deepcopy(self.payload))

    async def async_set_policy(self, policy: dict[str, Any], version: int) -> DeviceStatus:
        self._raise_if_failing()
        safe = validate_policy(policy)
        self.policy_calls.append((safe, version))
        self.payload["policy"] = safe
        self.payload["policy_version"] = version
        self.payload["enforcement"] = dict.fromkeys(POLICY_FLAGS, ENFORCEMENT_APPLIED)
        self.payload["lock_task_active"] = safe["kiosk_mode"]
        return DeviceStatus.from_payload(copy.deepcopy(self.payload))

    async def async_set_webhook(self, url: str) -> None:
        if self.webhook_fail_with is not None:
            raise self.webhook_fail_with
        self.webhook_url = url

    async def async_lock_screen(self) -> None:
        self._raise_if_failing()
        self.lock_calls += 1


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture(autouse=True)
def patch_client(fake_client: FakeClient):
    with (
        patch("custom_components.local_mdm.LocalMdmClient", return_value=fake_client),
        patch("custom_components.local_mdm.config_flow.LocalMdmClient", return_value=fake_client),
    ):
        yield


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE_ID,
        title=f"Tablet {DEVICE_ID}",
        data={
            CONF_HOST: "192.0.2.10",
            CONF_PORT: 8484,
            CONF_TOKEN: TOKEN,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
        },
        options={CONF_SCAN_INTERVAL: 60},
    )


@pytest.fixture
async def setup_entry(hass, config_entry: MockConfigEntry) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


__all__ = [
    "DEVICE_ID",
    "TOKEN",
    "WEBHOOK_ID",
    "FakeClient",
    "LocalMdmAuthError",
    "LocalMdmConnectionError",
    "LocalMdmPolicyRefusedError",
    "status_payload",
]
