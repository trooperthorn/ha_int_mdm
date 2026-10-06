"""UniFi-driven pairing, following a moved tablet, and the offline-start fixes."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_mdm.const import (
    CONF_DEVICE_ID,
    CONF_MAC,
    CONF_SUGGESTED_AREA,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.local_mdm.unifi import async_clients

from .conftest import DEVICE_ID, TOKEN, FakeClient, LocalMdmConnectionError

KITCHEN_MAC = "66:ec:07:4b:94:8a"
KITCHEN_IP = "192.168.30.97"


def add_unifi_client(
    hass: HomeAssistant,
    *,
    mac: str,
    name: str,
    ip: str | None,
    host_name: str = "android-host",
) -> str:
    """Register a UniFi client tracker the way the UniFi integration does."""
    unifi_entry = next(iter(hass.config_entries.async_entries("unifi")), None)
    if unifi_entry is None:
        unifi_entry = MockConfigEntry(domain="unifi", title="Default")
        unifi_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=unifi_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=name,
    )
    entity = er.async_get(hass).async_get_or_create(
        "device_tracker",
        "unifi",
        f"default-{mac}",
        config_entry=unifi_entry,
        device_id=device.id,
    )
    attributes = {"mac": mac, "host_name": host_name, "source_type": "router"}
    if ip:
        attributes["ip"] = ip
    hass.states.async_set(entity.entity_id, "home" if ip else "not_home", attributes)
    return entity.entity_id


def test_names_follow_the_room_tab_scheme(hass: HomeAssistant) -> None:
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip=KITCHEN_IP)
    add_unifi_client(hass, mac="aa:aa:aa:aa:aa:01", name="Master-Bedroom-Tab", ip="192.168.30.98")
    add_unifi_client(hass, mac="aa:aa:aa:aa:aa:02", name="SEAN-s-Tab-A11", ip="192.168.30.99")
    by_mac = {client.mac: client for client in async_clients(hass)}
    assert by_mac[KITCHEN_MAC].name == "Kitchen-Tab"
    assert by_mac[KITCHEN_MAC].room == "Kitchen"
    assert by_mac["aa:aa:aa:aa:aa:01"].room == "Master Bedroom"
    assert not by_mac["aa:aa:aa:aa:aa:02"].is_tablet


async def test_user_step_offers_unifi_when_a_tablet_is_connected(hass, fake_client: FakeClient):
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip=KITCHEN_IP)
    ar.async_get(hass).async_create("Kitchen")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["unifi", "manual"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "unifi"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "unifi"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tablet": KITCHEN_MAC, CONF_TOKEN: f" {TOKEN} ", CONF_PORT: 8484}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen-Tab"
    data = result["data"]
    assert data[CONF_HOST] == KITCHEN_IP
    assert data[CONF_MAC] == KITCHEN_MAC
    assert data[CONF_TOKEN] == TOKEN
    assert data[CONF_DEVICE_ID] == DEVICE_ID
    assert data[CONF_SUGGESTED_AREA] == "Kitchen"

    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, DEVICE_ID), entry.entry_id)
    assert device is not None
    assert device.name == "Kitchen-Tab"
    assert device.area_id == ar.async_get(hass).async_get_area_by_name("Kitchen").id
    assert (dr.CONNECTION_NETWORK_MAC, KITCHEN_MAC) in device.connections


async def test_unifi_pick_does_not_create_an_area(hass, fake_client: FakeClient):
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Garage-Tab", ip=KITCHEN_IP)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "unifi"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tablet": KITCHEN_MAC, CONF_TOKEN: TOKEN, CONF_PORT: 8484}
    )
    await hass.async_block_till_done()
    assert CONF_SUGGESTED_AREA not in result["data"]
    assert ar.async_get(hass).async_get_area_by_name("Garage") is None


async def test_unifi_pick_reports_a_bad_token(hass, fake_client: FakeClient):
    from .conftest import LocalMdmAuthError

    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip=KITCHEN_IP)
    fake_client.fail_with = LocalMdmAuthError("bad")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "unifi"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tablet": KITCHEN_MAC, CONF_TOKEN: "wrong", CONF_PORT: 8484}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.parametrize(
    ("name", "ip"),
    [("SEAN-s-Tab-A11", KITCHEN_IP), ("Kitchen-Tab", None)],
    ids=["not-room-tab", "not-connected"],
)
async def test_unifi_is_not_offered_without_a_usable_client(
    hass, fake_client: FakeClient, name: str, ip: str | None
):
    add_unifi_client(hass, mac=KITCHEN_MAC, name=name, ip=ip)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_paired_tablet_is_not_offered_again(hass, setup_entry, fake_client: FakeClient):
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip=KITCHEN_IP)
    hass.config_entries.async_update_entry(
        setup_entry, data={**setup_entry.data, CONF_MAC: KITCHEN_MAC}
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_manual_entry_from_the_menu_records_the_unifi_mac(hass, fake_client: FakeClient):
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip=KITCHEN_IP)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: KITCHEN_IP, CONF_PORT: 8484, CONF_TOKEN: TOKEN}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Tablet {DEVICE_ID}"
    assert result["data"][CONF_MAC] == KITCHEN_MAC


async def test_moved_tablet_is_followed_through_unifi(hass, setup_entry, fake_client: FakeClient):
    coordinator = setup_entry.runtime_data
    hass.config_entries.async_update_entry(
        setup_entry, data={**setup_entry.data, CONF_MAC: KITCHEN_MAC}
    )
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip="192.0.2.20")
    fake_client.down_hosts.add("192.0.2.10")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.is_reachable
    assert setup_entry.data[CONF_HOST] == "192.0.2.20"
    assert coordinator.client.host == "192.0.2.20"


async def test_a_different_device_at_the_unifi_address_is_not_followed(
    hass, setup_entry, fake_client: FakeClient
):
    coordinator = setup_entry.runtime_data
    hass.config_entries.async_update_entry(
        setup_entry, data={**setup_entry.data, CONF_MAC: KITCHEN_MAC}
    )
    add_unifi_client(hass, mac=KITCHEN_MAC, name="Kitchen-Tab", ip="192.0.2.20")
    fake_client.down_hosts.add("192.0.2.10")
    fake_client.payload["device_id"] = "someone-else"

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.data.is_reachable
    assert setup_entry.data[CONF_HOST] == "192.0.2.10"


async def test_offline_start_does_not_push_defaults_over_the_tablet(
    hass, config_entry, fake_client: FakeClient
):
    """A tablet offline while Home Assistant starts keeps its policy when it returns."""
    fake_client.fail_with = LocalMdmConnectionError("asleep")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    assert not coordinator.policy_known

    fake_client.payload["policy"]["camera_disabled"] = True
    fake_client.fail_with = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.policy_known
    assert coordinator.desired_policy["camera_disabled"] is True
    assert fake_client.policy_calls == []


async def test_offline_start_adopts_policy_from_the_first_webhook_report(
    hass, config_entry, fake_client: FakeClient
):
    fake_client.fail_with = LocalMdmConnectionError("asleep")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data

    payload = dict(fake_client.payload)
    payload["policy"] = {**payload["policy"], "camera_disabled": True}
    assert coordinator.async_handle_push(payload)
    await hass.async_block_till_done()

    assert coordinator.desired_policy["camera_disabled"] is True
    assert fake_client.policy_calls == []


async def test_switch_refuses_while_the_policy_is_unknown(
    hass, config_entry, fake_client: FakeClient
):
    fake_client.fail_with = LocalMdmConnectionError("asleep")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError, match="policy is unknown"):
        await config_entry.runtime_data.async_set_policy_flag("camera_disabled", True)
    assert fake_client.policy_calls == []


async def test_webhook_is_resent_when_the_tablet_answers(
    hass, config_entry, fake_client: FakeClient
):
    """An unreachable tablet at setup gets the webhook URL on its first answer."""
    fake_client.fail_with = LocalMdmConnectionError("asleep")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert fake_client.webhook_url is None

    fake_client.fail_with = None
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert fake_client.webhook_url is not None
    assert fake_client.webhook_url.endswith(f"/api/webhook/{config_entry.data['webhook_id']}")
