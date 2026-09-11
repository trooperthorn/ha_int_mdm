"""The Local MDM integration: a local control plane for an Android DPC."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from aiohttp.web import Request, Response
from homeassistant.components import webhook
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import LocalMdmAuthError, LocalMdmClient, LocalMdmConnectionError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import LocalMdmConfigEntry, LocalMdmCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions once per Home Assistant run."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LocalMdmConfigEntry) -> bool:
    """Set up one tablet from a config entry."""
    client = LocalMdmClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )
    coordinator = LocalMdmCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass,
        DOMAIN,
        f"Local MDM {coordinator.data.device_id}",
        webhook_id,
        _make_webhook_handler(coordinator),
        local_only=True,
        allowed_methods=["POST"],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    # The DPC learns where to report from us, so a changed HA address heals
    # on the next reload; an unreachable webhook is a warning, not a failure.
    try:
        url = webhook.async_generate_url(hass, webhook_id, allow_external=False, allow_ip=True)
        await client.async_set_webhook(url)
    except LocalMdmAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except LocalMdmConnectionError as err:
        raise ConfigEntryNotReady(f"Could not register the webhook with the DPC: {err}") from err

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LocalMdmConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _make_webhook_handler(
    coordinator: LocalMdmCoordinator,
) -> Callable[[HomeAssistant, str, Request], Awaitable[Response]]:
    async def _handle(hass: HomeAssistant, webhook_id: str, request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            return Response(status=HTTPStatus.BAD_REQUEST, text="expected a JSON object")
        if not isinstance(payload, dict):
            return Response(status=HTTPStatus.BAD_REQUEST, text="expected a JSON object")
        accepted = _dispatch(coordinator, payload)
        if not accepted:
            return Response(status=HTTPStatus.UNPROCESSABLE_ENTITY, text="report rejected")
        return Response(status=HTTPStatus.OK, text="ok")

    return _handle


@callback
def _dispatch(coordinator: LocalMdmCoordinator, payload: dict) -> bool:
    return coordinator.async_handle_push(payload)
