"""Fleet status: one sensor per tablet that dashboards can list without knowing entity ids."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE

from custom_components.local_mdm.api import DeviceStatus
from custom_components.local_mdm.sensor import fleet_status

from .conftest import FakeClient, LocalMdmConnectionError, status_payload


def _state(hass):
    states = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_fleet_status")]
    assert len(states) == 1
    return states[0]


async def test_compliant_tablet_is_online(hass, setup_entry):
    state = _state(hass)
    assert state.state == "online"
    assert state.attributes["reasons"] == []
    assert state.attributes["reachable"] is True
    assert state.attributes["tablet"] == setup_entry.title
    assert state.attributes["battery"] == 87
    assert state.attributes["options"] == [
        "online",
        "offline",
        "never_reported",
        "misconfigured",
        "needs_attention",
    ]


async def test_unreachable_tablet_reports_offline_not_unavailable(
    hass, setup_entry, fake_client: FakeClient
):
    fake_client.fail_with = LocalMdmConnectionError("no route to host")
    await setup_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = _state(hass)
    assert state.state == "offline"
    assert state.state != STATE_UNAVAILABLE
    assert state.attributes["reasons"] == ["not_reachable"]
    assert state.attributes["reachable"] is False
    # The last report survives, so the dashboard can say when it was last seen.
    assert state.attributes["last_report"] == "2026-09-10T12:00:00+00:00"


async def test_tablet_offline_since_startup_never_reported(
    hass, config_entry, fake_client: FakeClient
):
    fake_client.fail_with = LocalMdmConnectionError("asleep")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = _state(hass)
    assert state.state == "never_reported"
    assert state.attributes["reasons"] == ["not_reachable"]


async def test_not_device_owner_is_misconfigured(hass, setup_entry, fake_client: FakeClient):
    fake_client.payload["is_device_owner"] = False
    await setup_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = _state(hass)
    assert state.state == "misconfigured"
    assert "not_device_owner" in state.attributes["reasons"]


async def test_enforcement_failure_needs_attention(hass, setup_entry, fake_client: FakeClient):
    key = next(iter(fake_client.payload["enforcement"]))
    fake_client.payload["enforcement"][key] = "failed"
    await setup_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = _state(hass)
    assert state.state == "needs_attention"
    assert state.attributes["reasons"] == ["enforcement_failures"]
    assert state.attributes["enforcement_failures"] == [key]


def test_unreachable_wins_over_other_reasons():
    status = DeviceStatus.from_payload(status_payload(is_device_owner=False))
    offline = DeviceStatus(**{**status.__dict__, "is_reachable": False})
    assert fleet_status(offline) == ("offline", ["not_reachable"])
