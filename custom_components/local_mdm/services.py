"""Integration-level actions."""

from __future__ import annotations

import probatio
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN
from .coordinator import LocalMdmCoordinator

SERVICE_INSTALL_PACKAGE = "install_package"
ATTR_DEVICE_ID = "device_id"
ATTR_URL = "url"
ATTR_SHA256 = "sha256"

INSTALL_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_URL): probatio.All(cv.url, probatio.Match(r"^https?://")),
        probatio.Optional(ATTR_SHA256): probatio.All(
            cv.string,
            probatio.Lower,
            probatio.Match(r"^(sha256:)?[0-9a-f]{64}$"),
            lambda value: value.removeprefix("sha256:"),
        ),
    }
)


def _coordinator_for_device(hass: HomeAssistant, device_id: str) -> LocalMdmCoordinator:
    device, entry = dr.async_get_device_and_config_entry_for_domain(hass, device_id, domain=DOMAIN)
    if device is None:
        raise ServiceValidationError(f"Device {device_id} does not exist")
    if entry is not None and hasattr(entry, "runtime_data"):
        return entry.runtime_data
    raise ServiceValidationError(f"Device {device_id} is not a loaded Local MDM tablet")


async def _install_package(call: ServiceCall) -> None:
    coordinator = _coordinator_for_device(call.hass, call.data[ATTR_DEVICE_ID])
    await coordinator.async_install_package(call.data[ATTR_URL], call.data.get(ATTR_SHA256))


SERVICE_CONFIGURE_WIFI = "configure_wifi"
ATTR_SSID = "ssid"
ATTR_PASSWORD = "password"
ATTR_HIDDEN = "hidden"

WIFI_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_SSID): probatio.All(cv.string, probatio.Length(min=1, max=32)),
        probatio.Optional(ATTR_PASSWORD): probatio.All(cv.string, probatio.Length(min=8, max=63)),
        probatio.Optional(ATTR_HIDDEN, default=False): cv.boolean,
    }
)


async def _configure_wifi(call: ServiceCall) -> None:
    coordinator = _coordinator_for_device(call.hass, call.data[ATTR_DEVICE_ID])
    await coordinator.async_configure_wifi(
        call.data[ATTR_SSID], call.data.get(ATTR_PASSWORD), call.data[ATTR_HIDDEN]
    )


SERVICE_APPLY_POLICY = "apply_policy"
ATTR_POLICY = "policy"

APPLY_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_POLICY): dict,
    }
)


async def _apply_policy(call: ServiceCall) -> None:
    """Push a whole policy document, the way a security profile is applied.

    Keys left out fall back to their least restrictive value, so a profile is
    complete by construction; the guard in policy.py still runs first.
    """
    coordinator = _coordinator_for_device(call.hass, call.data[ATTR_DEVICE_ID])
    await coordinator.async_apply_policy(dict(call.data[ATTR_POLICY]))


SERVICE_APPROVE_PACKAGE = "approve_package"
ATTR_PACKAGE = "package"

APPROVE_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_PACKAGE): probatio.All(
            cv.string, probatio.Match(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
        ),
    }
)


async def _approve_package(call: ServiceCall) -> None:
    """Post-install approval: add a held package to allowed_packages."""
    coordinator = _coordinator_for_device(call.hass, call.data[ATTR_DEVICE_ID])
    await coordinator.async_approve_package(call.data[ATTR_PACKAGE])


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions once."""
    hass.services.async_register(DOMAIN, SERVICE_INSTALL_PACKAGE, _install_package, INSTALL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CONFIGURE_WIFI, _configure_wifi, WIFI_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPLY_POLICY, _apply_policy, APPLY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPROVE_PACKAGE, _approve_package, APPROVE_SCHEMA)
