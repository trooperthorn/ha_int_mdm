"""Text entities holding the comma-separated kiosk and allowed package lists."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POLICY_ALLOWED_PACKAGES, POLICY_KIOSK_PACKAGES
from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity

TEXTS: tuple[TextEntityDescription, ...] = tuple(
    TextEntityDescription(key=key, translation_key=key, entity_category=EntityCategory.CONFIG)
    for key in (POLICY_KIOSK_PACKAGES, POLICY_ALLOWED_PACKAGES)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the package list entities."""
    async_add_entities(LocalMdmPackagesText(entry.runtime_data, d) for d in TEXTS)


class LocalMdmPackagesText(LocalMdmEntity, TextEntity):
    """A package-name list of the desired policy, separated by commas."""

    _attr_native_max = 1024
    _attr_native_min = 0

    @property
    def native_value(self) -> str:
        return ",".join(self.coordinator.desired_policy.get(self.entity_description.key, []))

    async def async_set_value(self, value: str) -> None:
        packages = [part.strip() for part in value.split(",") if part.strip()]
        await self.coordinator.async_set_policy_value(self.entity_description.key, packages)
