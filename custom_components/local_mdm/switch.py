"""Policy switches: state is the desired policy, not the enforced state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POLICY_FLAGS
from .coordinator import LocalMdmConfigEntry, LocalMdmCoordinator
from .entity import LocalMdmEntity

SWITCHES: tuple[SwitchEntityDescription, ...] = tuple(
    SwitchEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
    )
    for key in POLICY_FLAGS
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one switch per policy flag."""
    coordinator = entry.runtime_data
    async_add_entities(LocalMdmPolicySwitch(coordinator, d) for d in SWITCHES)


class LocalMdmPolicySwitch(LocalMdmEntity, SwitchEntity):
    """One flag of the desired policy document."""

    def __init__(
        self, coordinator: LocalMdmCoordinator, description: SwitchEntityDescription
    ) -> None:
        super().__init__(coordinator, description)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.desired_policy.get(self.entity_description.key, False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        key = self.entity_description.key
        return {
            "enforcement": self.coordinator.data.enforcement.get(key, "unknown"),
            "reported_value": self.coordinator.data.policy.get(key),
            "policy_version": self.coordinator.data.policy_version,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_policy_flag(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_policy_flag(self.entity_description.key, False)
