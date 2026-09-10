"""Config, reauth, and options flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.local_mdm.const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DOMAIN,
)

from .conftest import DEVICE_ID, TOKEN, FakeClient, LocalMdmAuthError, LocalMdmConnectionError

USER_INPUT = {CONF_HOST: " 192.0.2.10 ", CONF_PORT: 8484, CONF_TOKEN: TOKEN}


async def test_user_flow_creates_entry(hass, fake_client: FakeClient):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Tablet {DEVICE_ID}"
    assert result["data"][CONF_HOST] == "192.0.2.10"
    assert result["data"][CONF_PORT] == 8484
    assert result["data"][CONF_DEVICE_ID] == DEVICE_ID
    assert len(result["data"][CONF_WEBHOOK_ID]) == 64
    assert result["options"] == {CONF_SCAN_INTERVAL: 60}
    assert result["result"].unique_id == DEVICE_ID


async def test_user_flow_cannot_connect(hass, fake_client: FakeClient):
    fake_client.fail_with = LocalMdmConnectionError("down")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(hass, fake_client: FakeClient):
    fake_client.fail_with = LocalMdmAuthError("nope")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_device_aborts(hass, setup_entry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(hass, setup_entry, fake_client: FakeClient):
    result = await setup_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "new-token"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_entry.data[CONF_TOKEN] == "new-token"


async def test_reauth_wrong_device_aborts(hass, setup_entry, fake_client: FakeClient):
    fake_client.payload["device_id"] = "some-other-tablet"
    result = await setup_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "new-token"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_options_flow_reloads_with_new_interval(hass, setup_entry):
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 120}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options == {CONF_SCAN_INTERVAL: 120}
    assert setup_entry.runtime_data.update_interval.total_seconds() == 120
