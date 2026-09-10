"""Sensors: battery, versions, and the last report time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfRatio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import DeviceStatus
from .coordinator import LocalMdmConfigEntry
from .entity import LocalMdmEntity


@dataclass(frozen=True, kw_only=True)
class LocalMdmSensorDescription(SensorEntityDescription):
    """Adds the value extractor."""

    value_fn: Callable[[DeviceStatus], Any]


def _reported_at(status: DeviceStatus) -> datetime | None:
    if not status.reported_at:
        return None
    return dt_util.parse_datetime(status.reported_at)


SENSORS: tuple[LocalMdmSensorDescription, ...] = (
    LocalMdmSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_level,
    ),
    LocalMdmSensorDescription(
        key="policy_version",
        translation_key="policy_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.policy_version,
    ),
    LocalMdmSensorDescription(
        key="dpc_version",
        translation_key="dpc_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.dpc_version,
    ),
    LocalMdmSensorDescription(
        key="enforcement_failures",
        translation_key="enforcement_failures",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: len(s.enforcement_failures),
    ),
    LocalMdmSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_reported_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(LocalMdmSensor(coordinator, d) for d in SENSORS)


class LocalMdmSensor(LocalMdmEntity, SensorEntity):
    """A value reported by the DPC."""

    entity_description: LocalMdmSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "enforcement_failures":
            return None
        return {"keys": self.coordinator.data.enforcement_failures}
