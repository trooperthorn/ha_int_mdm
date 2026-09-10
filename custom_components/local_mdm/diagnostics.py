"""Diagnostics with the token and webhook id redacted."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN, CONF_WEBHOOK_ID
from .coordinator import LocalMdmConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_WEBHOOK_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LocalMdmConfigEntry
) -> dict[str, Any]:
    """Return the entry, the desired policy, and the last report."""
    coordinator = entry.runtime_data
    status = asdict(coordinator.data)
    status.pop("raw", None)
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "desired_policy": coordinator.desired_policy,
        "last_update_success": coordinator.last_update_success,
        "status": status,
    }
