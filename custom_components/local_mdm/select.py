"""Select entity for the app mode: open launcher or allowlist."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import APP_MODE_OPEN, APP_MODES, POLICY_APP_MODE
from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity

APP_MODE = SelectEntityDescription(
    key=POLICY_APP_MODE,
    translation_key=POLICY_APP_MODE,
    entity_category=EntityCategory.CONFIG,
    options=list(APP_MODES),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the app mode select."""
    async_add_entities([LocalMdmAppModeSelect(entry.runtime_data, APP_MODE)])


class LocalMdmAppModeSelect(LocalMdmEntity, SelectEntity):
    """Desired app mode; the enforcement attribute shows what the DPC did with it."""

    @property
    def current_option(self) -> str:
        return str(self.coordinator.desired_policy.get(POLICY_APP_MODE, APP_MODE_OPEN))

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {
            "enforcement": self.coordinator.data.enforcement.get(POLICY_APP_MODE, "unknown"),
            "reported_value": self.coordinator.data.policy.get(POLICY_APP_MODE),
        }

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_policy_value(POLICY_APP_MODE, option)
