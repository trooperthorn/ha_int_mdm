"""The acceptance check: switch to policy push to webhook to sensor, under two seconds."""

from __future__ import annotations

import time
from http import HTTPStatus

import pytest
import voluptuous as vol
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.exceptions import HomeAssistantError

from custom_components.local_mdm.const import ENFORCEMENT_FAILED

from .conftest import WEBHOOK_ID, FakeClient, LocalMdmPolicyRefusedError, status_payload

CAMERA_SWITCH = "switch.tablet_tablet_kitchen_camera_disabled"
CAMERA_ENFORCED = "binary_sensor.tablet_tablet_kitchen_camera_disabled_enforced"
PROBLEM = "binary_sensor.tablet_tablet_kitchen_enforcement_problem"
KIOSK_LOCK = "binary_sensor.tablet_tablet_kitchen_kiosk_lock"


async def _post_webhook(hass, hass_client_no_auth, payload):
    client = await hass_client_no_auth()
    response = await client.post(f"/api/webhook/{WEBHOOK_ID}", json=payload)
    await hass.async_block_till_done()
    return response


async def test_camera_policy_round_trip_under_two_seconds(
    hass, setup_entry, fake_client: FakeClient, hass_client_no_auth
):
    assert hass.states.get(CAMERA_SWITCH).state == STATE_OFF
    assert hass.states.get(CAMERA_ENFORCED).state == STATE_OFF

    started = time.monotonic()
    await hass.services.async_call("switch", "turn_on", {"entity_id": CAMERA_SWITCH}, blocking=True)
    # The DPC applies the policy and then reports through the webhook. The
    # fake client already answered the PUT, so this simulates the POST.
    reported = status_payload(
        policy={**fake_client.payload["policy"]},
        policy_version=fake_client.payload["policy_version"],
    )
    response = await _post_webhook(hass, hass_client_no_auth, reported)
    elapsed = time.monotonic() - started

    assert response.status == HTTPStatus.OK
    assert fake_client.policy_calls[-1][0]["camera_disabled"] is True
    assert hass.states.get(CAMERA_SWITCH).state == STATE_ON
    assert hass.states.get(CAMERA_ENFORCED).state == STATE_ON
    assert hass.states.get(PROBLEM).state == STATE_OFF
    assert elapsed < 2.0


async def test_switch_off_pushes_full_document(hass, setup_entry, fake_client: FakeClient):
    await hass.services.async_call("switch", "turn_on", {"entity_id": CAMERA_SWITCH}, blocking=True)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": CAMERA_SWITCH}, blocking=True
    )
    policy, version = fake_client.policy_calls[-1]
    assert policy["camera_disabled"] is False
    assert version == fake_client.policy_calls[0][1] + 1
    assert hass.states.get(CAMERA_SWITCH).state == STATE_OFF


async def test_enforcement_failure_is_visible(
    hass, setup_entry, fake_client: FakeClient, hass_client_no_auth
):
    await hass.services.async_call("switch", "turn_on", {"entity_id": CAMERA_SWITCH}, blocking=True)
    reported = status_payload(
        policy={**fake_client.payload["policy"]},
        enforcement={**fake_client.payload["enforcement"], "camera_disabled": ENFORCEMENT_FAILED},
    )
    await _post_webhook(hass, hass_client_no_auth, reported)
    assert hass.states.get(CAMERA_SWITCH).state == STATE_ON
    assert hass.states.get(CAMERA_ENFORCED).state == STATE_OFF
    assert hass.states.get(PROBLEM).state == STATE_ON
    failures = hass.states.get("sensor.tablet_tablet_kitchen_enforcement_failures")
    assert failures.state == "1"
    assert failures.attributes["keys"] == ["camera_disabled"]


async def test_kiosk_without_packages_is_refused_locally(
    hass, setup_entry, fake_client: FakeClient
):
    with pytest.raises(HomeAssistantError, match="refused before sending"):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.tablet_tablet_kitchen_kiosk_mode"},
            blocking=True,
        )
    assert fake_client.policy_calls == []


async def test_kiosk_with_packages_reports_lock(hass, setup_entry, fake_client: FakeClient):
    coordinator = setup_entry.runtime_data
    await coordinator.async_set_kiosk_packages(["org.example.dashboard"])
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.tablet_tablet_kitchen_kiosk_mode"}, blocking=True
    )
    assert hass.states.get(KIOSK_LOCK).state == STATE_OFF  # lock device class: off means locked
    assert fake_client.policy_calls[-1][0]["kiosk_packages"] == ["org.example.dashboard"]


async def test_dpc_refusal_surfaces_as_error(hass, setup_entry, fake_client: FakeClient):
    fake_client.fail_with = LocalMdmPolicyRefusedError("not device owner")
    with pytest.raises(HomeAssistantError, match="DPC refused"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": CAMERA_SWITCH}, blocking=True
        )
    assert hass.states.get(CAMERA_SWITCH).state == STATE_OFF


async def test_webhook_rejects_other_device_and_garbage(hass, setup_entry, hass_client_no_auth):
    response = await _post_webhook(hass, hass_client_no_auth, status_payload(device_id="intruder"))
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY

    client = await hass_client_no_auth()
    response = await client.post(f"/api/webhook/{WEBHOOK_ID}", data=b"not json")
    assert response.status == HTTPStatus.BAD_REQUEST
    response = await client.post(f"/api/webhook/{WEBHOOK_ID}", json=[1, 2])
    assert response.status == HTTPStatus.BAD_REQUEST

    response = await _post_webhook(
        hass, hass_client_no_auth, {"device_id": "tablet-kitchen", "policy_version": "x"}
    )
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_lock_screen_button(hass, setup_entry, fake_client: FakeClient):
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.tablet_tablet_kitchen_lock_screen"}, blocking=True
    )
    assert fake_client.lock_calls == 1


async def test_diagnostics_redact_secrets(hass, setup_entry, hass_client):
    from pytest_homeassistant_custom_component.components.diagnostics import (
        get_diagnostics_for_config_entry,
    )

    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup_entry)
    assert diag["entry_data"]["token"] == "**REDACTED**"
    assert diag["entry_data"]["webhook_id"] == "**REDACTED**"
    assert diag["status"]["device_id"] == "tablet-kitchen"
    assert "raw" not in diag["status"]


async def test_kiosk_packages_text_entity(hass, setup_entry, fake_client: FakeClient):
    entity_id = "text.tablet_tablet_kitchen_kiosk_packages"
    assert hass.states.get(entity_id).state == ""
    await hass.services.async_call(
        "text", "set_value", {"entity_id": entity_id, "value": " b.app, a.app ,"}, blocking=True
    )
    assert hass.states.get(entity_id).state == "a.app,b.app"
    assert fake_client.policy_calls[-1][0]["kiosk_packages"] == ["a.app", "b.app"]


async def test_os_and_app_version_entities(
    hass, setup_entry, fake_client: FakeClient, hass_client_no_auth
):
    prefix = "sensor.tablet_tablet_kitchen"
    assert hass.states.get(f"{prefix}_android_version").state == "15"
    assert hass.states.get(f"{prefix}_security_patch").state == "2024-09-05"
    assert hass.states.get(f"{prefix}_kiosk_app_version").state == "2026.6.5"
    assert (
        hass.states.get("binary_sensor.tablet_tablet_kitchen_os_update_pending").state == STATE_OFF
    )

    reported = status_payload(
        system_update={"policy": 1, "pending": True, "received_at": "2026-09-10T13:00:00+00:00"},
        last_install={"state": "installed", "package": "io.homeassistant.companion.android"},
    )
    await _post_webhook(hass, hass_client_no_auth, reported)
    assert (
        hass.states.get("binary_sensor.tablet_tablet_kitchen_os_update_pending").state == STATE_ON
    )
    last = hass.states.get(f"{prefix}_last_install")
    assert last.state == "installed"
    assert last.attributes["package"] == "io.homeassistant.companion.android"


async def test_new_policy_flags_have_switches(hass, setup_entry, fake_client: FakeClient):
    for key in ("automatic_os_updates", "stay_awake_on_power"):
        entity_id = f"switch.tablet_tablet_kitchen_{key}"
        assert hass.states.get(entity_id).state == STATE_OFF
        await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
        assert hass.states.get(entity_id).state == STATE_ON
    assert fake_client.policy_calls[-1][0]["auto_os_updates"] is True
    assert fake_client.policy_calls[-1][0]["stay_awake_on_power"] is True


async def test_install_package_action(hass, setup_entry, fake_client: FakeClient):
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_device_by_identifier(
        ("local_mdm", "tablet-kitchen"), setup_entry.entry_id
    )
    await hass.services.async_call(
        "local_mdm",
        "install_package",
        {
            "device_id": device.id,
            "url": "https://github.com/home-assistant/android/releases/download/2026.6.5/app-full-release.apk",
            "sha256": "sha256:" + "C" * 64,
        },
        blocking=True,
    )
    assert fake_client.install_calls == [
        (
            "https://github.com/home-assistant/android/releases/download/2026.6.5/app-full-release.apk",
            "c" * 64,
        )
    ]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "local_mdm",
            "install_package",
            {"device_id": "not-a-device", "url": "https://example.invalid/a.apk"},
            blocking=True,
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            "local_mdm",
            "install_package",
            {"device_id": device.id, "url": "ftp://example.invalid/a.apk"},
            blocking=True,
        )
