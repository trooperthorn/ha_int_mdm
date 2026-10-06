"""Config flow: pick the tablet from UniFi (or enter its address) plus its token.

With the UniFi Network integration loaded, every connected client named
Room-Tab (docs/onboarding.md, "Address plan") is offered, so the address,
the MAC, the entry title and the area come from UniFi and only the token
shown on the tablet is typed. Manual entry stays available.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import LocalMdmAuthError, LocalMdmClient, LocalMdmConnectionError
from .const import (
    CONF_DEVICE_ID,
    CONF_MAC,
    CONF_SCAN_INTERVAL,
    CONF_SUGGESTED_AREA,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .unifi import UnifiClient, async_mac_for_ip, async_tablet_candidates

CONF_TABLET = "tablet"

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        )
    }
)


async def _probe(hass: HomeAssistant, host: str, port: int, token: str) -> str:
    """Return the device id or raise the client's own exceptions."""
    client = LocalMdmClient(async_get_clientsession(hass), host, port, token)
    status = await client.async_get_status()
    return status.device_id


def _paired_macs(hass: HomeAssistant) -> set[str]:
    """MACs of tablets that already have an entry, so UniFi does not offer them."""
    dev_reg = dr.async_get(hass)
    macs: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False):
        if mac := entry.data.get(CONF_MAC):
            macs.add(mac)
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            macs.update(
                value for kind, value in device.connections if kind == dr.CONNECTION_NETWORK_MAC
            )
    return macs


def _suggested_area(hass: HomeAssistant, room: str | None) -> str | None:
    """The existing area named like the Room part; never creates an area."""
    if not room:
        return None
    area = ar.async_get(hass).async_get_area_by_name(room)
    return area.name if area else None


class LocalMdmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup and reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._candidates: dict[str, UnifiClient] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            self._candidates = {
                client.mac: client
                for client in async_tablet_candidates(self.hass, _paired_macs(self.hass))
            }
            if self._candidates:
                return self.async_show_menu(step_id="user", menu_options=["unifi", "manual"])
        return await self._async_manual("user", user_input)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_manual("manual", user_input)

    async def _async_manual(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            result = await self._async_pair(
                host,
                int(user_input[CONF_PORT]),
                user_input[CONF_TOKEN].strip(),
                errors,
                mac=async_mac_for_ip(self.hass, host),
            )
            if result is not None:
                return result
        return self.async_show_form(step_id=step_id, data_schema=USER_SCHEMA, errors=errors)

    async def async_step_unifi(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._candidates:
            return self.async_abort(reason="no_unifi_tablets")
        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._candidates.get(user_input[CONF_TABLET])
            if client is None or client.ip is None:
                errors["base"] = "cannot_connect"
            else:
                result = await self._async_pair(
                    client.ip,
                    int(user_input[CONF_PORT]),
                    user_input[CONF_TOKEN].strip(),
                    errors,
                    mac=client.mac,
                    title=client.name,
                    area=_suggested_area(self.hass, client.room),
                )
                if result is not None:
                    return result
        options = [
            SelectOptionDict(value=client.mac, label=f"{client.name} ({client.ip})")
            for client in self._candidates.values()
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_TABLET): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
                    NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="unifi", data_schema=schema, errors=errors)

    async def _async_pair(
        self,
        host: str,
        port: int,
        token: str,
        errors: dict[str, str],
        *,
        mac: str | None = None,
        title: str | None = None,
        area: str | None = None,
    ) -> ConfigFlowResult | None:
        """Probe the tablet and create the entry; None, with errors set, redraws the form."""
        try:
            device_id = await _probe(self.hass, host, port, token)
        except LocalMdmAuthError:
            errors["base"] = "invalid_auth"
            return None
        except LocalMdmConnectionError:
            errors["base"] = "cannot_connect"
            return None
        updates: dict[str, Any] = {CONF_HOST: host, CONF_PORT: port}
        if mac:
            updates[CONF_MAC] = mac
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates=updates)
        data: dict[str, Any] = {
            **updates,
            CONF_TOKEN: token,
            CONF_DEVICE_ID: device_id,
            CONF_WEBHOOK_ID: webhook.async_generate_id(),
        }
        if area:
            data[CONF_SUGGESTED_AREA] = area
        return self.async_create_entry(
            title=title or f"Tablet {device_id}",
            data=data,
            options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                device_id = await _probe(
                    self.hass, entry.data[CONF_HOST], entry.data[CONF_PORT], token
                )
            except LocalMdmAuthError:
                errors["base"] = "invalid_auth"
            except LocalMdmConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if device_id != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> LocalMdmOptionsFlow:
        return LocalMdmOptionsFlow()


class LocalMdmOptionsFlow(OptionsFlowWithReload):
    """Polling interval; the entry reloads on save."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
