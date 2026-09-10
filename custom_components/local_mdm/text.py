"""Text entity holding the comma-separated kiosk package list."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POLICY_KIOSK_PACKAGES
from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity

KIOSK_PACKAGES = TextEntityDescription(
    key=POLICY_KIOSK_PACKAGES,
    translation_key=POLICY_KIOSK_PACKAGES,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the kiosk package list entity."""
    async_add_entities([LocalMdmKioskPackagesText(entry.runtime_data, KIOSK_PACKAGES)])


class LocalMdmKioskPackagesText(LocalMdmEntity, TextEntity):
    """Package names allowed in kiosk mode, separated by commas."""

    _attr_native_max = 1024
    _attr_native_min = 0

    @property
    def native_value(self) -> str:
        return ",".join(self.coordinator.desired_policy.get(POLICY_KIOSK_PACKAGES, []))

    async def async_set_value(self, value: str) -> None:
        packages = [part.strip() for part in value.split(",") if part.strip()]
        await self.coordinator.async_set_kiosk_packages(packages)
