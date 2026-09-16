"""Setup, unload, and webhook registration."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.local_mdm.const import DOMAIN

from .conftest import DEVICE_ID, WEBHOOK_ID, FakeClient, LocalMdmAuthError, LocalMdmConnectionError


async def test_setup_registers_webhook_and_pushes_url(hass, setup_entry, fake_client: FakeClient):
    assert setup_entry.state is ConfigEntryState.LOADED
    assert fake_client.webhook_url is not None
    assert fake_client.webhook_url.endswith(f"/api/webhook/{WEBHOOK_ID}")
    assert "://" in fake_client.webhook_url

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), setup_entry.entry_id
    )
    assert device is not None
    assert device.sw_version == "2026.09.10.1"

    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_succeeds_when_dpc_unreachable(hass, config_entry, fake_client: FakeClient):
    """A tablet that's asleep/off Wi-Fi at setup must not block the entry.

    Every entity should still be created, reporting the offline() default
    (there is no prior status to fall back on yet) with reachable off,
    instead of the whole config entry failing to load.
    """
    fake_client.fail_with = LocalMdmConnectionError("down")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    reachable = hass.states.get("binary_sensor.tablet_tablet_kitchen_reachable")
    assert reachable is not None and reachable.state == "off"
    battery = hass.states.get("sensor.tablet_tablet_kitchen_battery")
    assert battery is not None and battery.state == "unknown"


async def test_setup_starts_reauth_on_bad_token(hass, config_entry, fake_client: FakeClient):
    fake_client.fail_with = LocalMdmAuthError("bad")
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_setup_retries_when_webhook_push_fails(hass, config_entry, fake_client: FakeClient):
    fake_client.webhook_fail_with = LocalMdmConnectionError("down")
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_poll_fallback_keeps_last_value_and_flags_unreachable(
    hass, setup_entry, fake_client: FakeClient
):
    """A tablet going offline mid-operation keeps its last-known data.

    Connectivity is surfaced through binary_sensor.<tablet>_reachable, not
    by every other entity going unavailable: toggling a control while the
    tablet is briefly offline should fail with a clear error when it
    actually tries to push, not be impossible because the entity vanished.
    """
    state = hass.states.get("sensor.tablet_tablet_kitchen_battery")
    assert state is not None and state.state == "87"
    assert hass.states.get("binary_sensor.tablet_tablet_kitchen_reachable").state == "on"

    fake_client.fail_with = LocalMdmConnectionError("down")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tablet_tablet_kitchen_battery").state == "87"
    assert hass.states.get("binary_sensor.tablet_tablet_kitchen_reachable").state == "off"

    fake_client.fail_with = None
    fake_client.payload["battery"]["level"] = 50
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tablet_tablet_kitchen_battery").state == "50"
    assert hass.states.get("binary_sensor.tablet_tablet_kitchen_reachable").state == "on"


async def test_switch_stays_available_while_unreachable(hass, setup_entry, fake_client: FakeClient):
    """A control entity must not disappear just because the tablet is offline.

    It should stay available so the user can still try, and get one clear
    error for that attempt rather than a switch they can't touch at all.
    """
    fake_client.fail_with = LocalMdmConnectionError("down")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    switch = hass.states.get("switch.tablet_tablet_kitchen_camera_disabled")
    assert switch is not None
    assert switch.state != "unavailable"

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.tablet_tablet_kitchen_camera_disabled"},
            blocking=True,
        )
