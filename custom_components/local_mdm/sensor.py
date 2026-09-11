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
    LocalMdmSensorDescription(
        key="os_version",
        translation_key="os_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.os_release,
    ),
    LocalMdmSensorDescription(
        key="security_patch",
        translation_key="security_patch",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.security_patch,
    ),
    LocalMdmSensorDescription(
        key="kiosk_app_version",
        translation_key="kiosk_app_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: next(iter(s.installed.values()), None),
    ),
    LocalMdmSensorDescription(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.wifi_ssid,
    ),
    LocalMdmSensorDescription(
        key="management_tier",
        translation_key="management_tier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.tier,
    ),
    LocalMdmSensorDescription(
        key="tier_limited",
        translation_key="tier_limited",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: len(s.tier_limited),
    ),
    LocalMdmSensorDescription(
        key="pending_packages",
        translation_key="pending_packages",
        value_fn=lambda s: len(s.pending_packages),
    ),
    LocalMdmSensorDescription(
        key="last_install",
        translation_key="last_install",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (s.last_install or {}).get("state"),
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
        status = self.coordinator.data
        match self.entity_description.key:
            case "enforcement_failures":
                return {"keys": status.enforcement_failures}
            case "tier_limited":
                return {
                    "keys": status.tier_limited,
                    "detail": {k: status.enforcement[k] for k in status.tier_limited},
                }
            case "os_version":
                return {"build": status.os_build, "update_received_at": status.update_received_at}
            case "kiosk_app_version":
                return {"installed": status.installed}
            case "last_install":
                return dict(status.last_install or {})
            case "pending_packages":
                return {"packages": status.pending_packages, "unsuspendable": status.unsuspendable}
        return None
