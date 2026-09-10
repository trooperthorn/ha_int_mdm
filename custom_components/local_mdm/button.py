"""Buttons: immediate actions that are not policy."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity

LOCK_SCREEN = ButtonEntityDescription(key="lock_screen", translation_key="lock_screen")
REFRESH = ButtonEntityDescription(
    key="refresh",
    device_class=ButtonDeviceClass.UPDATE,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the action buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            LocalMdmLockScreenButton(coordinator, LOCK_SCREEN),
            LocalMdmRefreshButton(coordinator, REFRESH),
        ]
    )


class LocalMdmLockScreenButton(LocalMdmEntity, ButtonEntity):
    """Lock the screen now."""

    async def async_press(self) -> None:
        await self.coordinator.async_lock_screen()


class LocalMdmRefreshButton(LocalMdmEntity, ButtonEntity):
    """Poll the DPC now instead of waiting for the next interval."""

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
