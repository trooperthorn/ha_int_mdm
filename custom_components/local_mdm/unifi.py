"""Read the UniFi Network integration's client trackers.

Each tablet is a UniFi client with a fixed IP and an alias of the form
``Room-Tab`` (docs/onboarding.md, "Address plan"). The tracker entity carries
that alias, the MAC the tablet uses on Wi-Fi, and, while it is connected, its
IP. Setup offers those clients so nobody types an address, and the coordinator
uses them to follow a tablet whose address changed. Nothing here writes to
UniFi or to its entities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

UNIFI_DOMAIN = "unifi"

# "Kitchen-Tab", "Master-Bedroom-Tab", "Office_Tab", "Den Tab".
TABLET_NAME = re.compile(r"^(?P<room>.+?)[-_ ]tab$", re.IGNORECASE)


@dataclass(frozen=True)
class UnifiClient:
    """One UniFi client tracker as Local MDM sees it."""

    entity_id: str
    mac: str
    ip: str | None
    name: str | None
    room: str | None

    @property
    def is_tablet(self) -> bool:
        """True when the client carries a Room-Tab name."""
        return self.name is not None


def _mac(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    mac = value.strip().lower()
    return mac if len(mac) == 17 else None


def _tablet_name(candidates: list[Any]) -> tuple[str, str] | None:
    """Return (name, room) for the first candidate that follows Room-Tab."""
    for value in candidates:
        if not isinstance(value, str):
            continue
        name = value.strip()
        if match := TABLET_NAME.match(name):
            room = re.sub(r"[-_]+", " ", match["room"]).strip()
            if room:
                return name, room
    return None


def async_clients(hass: HomeAssistant) -> list[UnifiClient]:
    """Every UniFi client tracker with a usable MAC."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    clients: list[UnifiClient] = []
    for state in hass.states.async_all("device_tracker"):
        entry = ent_reg.async_get(state.entity_id)
        if entry is None or entry.platform != UNIFI_DOMAIN:
            continue
        mac = _mac(state.attributes.get("mac"))
        if mac is None:
            continue
        ip = state.attributes.get("ip")
        # The UniFi alias becomes the tracker's device name; the DHCP host
        # name is the fallback for a client that has no alias yet.
        names: list[Any] = []
        if entry.device_id and (device := dev_reg.async_get(entry.device_id)):
            names += [device.name_by_user, device.name]
        names += [entry.name, entry.original_name, state.attributes.get("host_name")]
        found = _tablet_name(names)
        clients.append(
            UnifiClient(
                entity_id=state.entity_id,
                mac=mac,
                ip=ip if isinstance(ip, str) and ip else None,
                name=found[0] if found else None,
                room=found[1] if found else None,
            )
        )
    return clients


def async_tablet_candidates(hass: HomeAssistant, exclude_macs: set[str]) -> list[UnifiClient]:
    """Connected Room-Tab clients not already paired, sorted by name."""
    return sorted(
        (
            client
            for client in async_clients(hass)
            if client.is_tablet and client.ip and client.mac not in exclude_macs
        ),
        key=lambda client: (client.name or "").lower(),
    )


def async_ip_for_macs(hass: HomeAssistant, macs: set[str]) -> str | None:
    """The IP UniFi currently reports for any of ``macs``, if connected."""
    for client in async_clients(hass):
        if client.mac in macs and client.ip:
            return client.ip
    return None


def async_mac_for_ip(hass: HomeAssistant, ip: str) -> str | None:
    """The MAC of the connected UniFi client holding ``ip``."""
    for client in async_clients(hass):
        if client.ip == ip:
            return client.mac
    return None
