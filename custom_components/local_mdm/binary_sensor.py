"""Binary sensors: what the tablet reports it is actually doing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DeviceStatus
from .const import POLICY_FLAGS
from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity


@dataclass(frozen=True, kw_only=True)
class LocalMdmBinarySensorDescription(BinarySensorEntityDescription):
    """Adds the value extractor."""

    value_fn: Callable[[DeviceStatus], bool | None]


STATUS_SENSORS: tuple[LocalMdmBinarySensorDescription, ...] = (
    LocalMdmBinarySensorDescription(
        key="device_owner",
        translation_key="device_owner",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.is_device_owner,
    ),
    LocalMdmBinarySensorDescription(
        key="kiosk_active",
        translation_key="kiosk_active",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda s: not s.lock_task_active,
    ),
    LocalMdmBinarySensorDescription(
        key="enforcement_problem",
        translation_key="enforcement_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: bool(s.enforcement_failures),
    ),
    LocalMdmBinarySensorDescription(
        key="wifi_connected",
        translation_key="wifi_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.wifi_connected,
    ),
    LocalMdmBinarySensorDescription(
        key="os_update_pending",
        translation_key="os_update_pending",
        device_class=BinarySensorDeviceClass.UPDATE,
        value_fn=lambda s: s.update_pending,
    ),
    LocalMdmBinarySensorDescription(
        key="battery_charging",
        translation_key="battery_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_charging,
    ),
    LocalMdmBinarySensorDescription(
        key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.is_reachable,
    ),
)

# One "enforced" sensor per policy flag: on only when the DPC reports the
# flag on and applied. This is the round-trip check the switch cannot give.
ENFORCED_SENSORS: tuple[LocalMdmBinarySensorDescription, ...] = tuple(
    LocalMdmBinarySensorDescription(
        key=f"{key}_enforced",
        translation_key=f"{key}_enforced",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=(lambda k: lambda s: s.is_enforced(k))(key),
    )
    for key in POLICY_FLAGS
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the status and enforcement sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        LocalMdmBinarySensor(coordinator, d) for d in (*STATUS_SENSORS, *ENFORCED_SENSORS)
    )


class LocalMdmBinarySensor(LocalMdmEntity, BinarySensorEntity):
    """A boolean fact reported by the DPC."""

    entity_description: LocalMdmBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
