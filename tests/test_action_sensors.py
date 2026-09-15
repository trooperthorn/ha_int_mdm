"""last_actions: lock_screen, reboot, and configure_wifi keep their own history."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .conftest import FakeClient, LocalMdmAuthError, LocalMdmConnectionError


def _find(hass, key: str):
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith(f"_{key}"):
            return state
    return None


async def test_actions_start_unknown(hass, setup_entry):
    # Entity id suffixes come from the translated name, not the raw key
    # ("last_configure_wifi" -> ..._last_wi_fi_configure).
    for suffix in ("last_lock_screen", "last_reboot", "last_wi_fi_configure"):
        state = _find(hass, suffix)
        assert state is not None
        assert state.state == "unknown"


async def test_lock_screen_success_records_ok(hass, setup_entry, fake_client: FakeClient):
    coordinator = setup_entry.runtime_data
    await coordinator.async_lock_screen()
    await hass.async_block_till_done()

    action = coordinator.last_actions["last_lock_screen"]
    assert action["result"] == "ok"
    assert action["message"] is None
    assert action["at"]

    state = _find(hass, "last_lock_screen")
    assert state is not None
    assert state.state == "ok"


async def test_reboot_failure_records_error_without_clobbering_success(
    hass, setup_entry, fake_client: FakeClient
):
    coordinator = setup_entry.runtime_data
    await coordinator.async_reboot()
    assert coordinator.last_actions["last_reboot"]["result"] == "ok"

    fake_client.fail_with = LocalMdmConnectionError("no route to host")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_reboot()

    action = coordinator.last_actions["last_reboot"]
    assert action["result"] == "error"
    assert "no route to host" in action["message"]

    state = _find(hass, "last_reboot")
    assert state.state == "error"
    assert "no route to host" in state.attributes["message"]


async def test_configure_wifi_auth_error_still_reauths_and_records(
    hass, setup_entry, fake_client: FakeClient
):
    coordinator = setup_entry.runtime_data
    fake_client.fail_with = LocalMdmAuthError("bad token")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.async_configure_wifi("IoT-Tablets", "hunter2", False)

    action = coordinator.last_actions["last_configure_wifi"]
    assert action["result"] == "error"
    assert "bad token" in action["message"]


async def test_actions_keep_independent_history(hass, setup_entry, fake_client: FakeClient):
    """A reboot's outcome must not overwrite lock_screen's, or vice versa."""
    coordinator = setup_entry.runtime_data
    await coordinator.async_lock_screen()

    fake_client.fail_with = LocalMdmConnectionError("down")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_reboot()

    assert coordinator.last_actions["last_lock_screen"]["result"] == "ok"
    assert coordinator.last_actions["last_reboot"]["result"] == "error"
