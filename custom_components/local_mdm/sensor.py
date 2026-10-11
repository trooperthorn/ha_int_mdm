"""Sensors: battery, versions, the last report time, and the fleet status."""

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


# Fleet status: one state per tablet that says whether it needs attention,
# so a dashboard can list every tablet without knowing its entity ids.
FLEET_ONLINE = "online"
FLEET_OFFLINE = "offline"
FLEET_NEVER_REPORTED = "never_reported"
FLEET_MISCONFIGURED = "misconfigured"
FLEET_NEEDS_ATTENTION = "needs_attention"
FLEET_STATUS_OPTIONS = [
    FLEET_ONLINE,
    FLEET_OFFLINE,
    FLEET_NEVER_REPORTED,
    FLEET_MISCONFIGURED,
    FLEET_NEEDS_ATTENTION,
]


def fleet_status(status: DeviceStatus) -> tuple[str, list[str]]:
    """The fleet state for a tablet and the reasons behind it.

    Unreachable wins: an offline tablet's other fields are only its last
    report. A tablet that is not Device Owner cannot enforce anything, so it
    is misconfigured; enforcement failures alone need attention.
    """
    if not status.is_reachable:
        state = FLEET_OFFLINE if status.reported_at else FLEET_NEVER_REPORTED
        return state, ["not_reachable"]
    reasons: list[str] = []
    if not status.is_device_owner:
        reasons.append("not_device_owner")
    if status.enforcement_failures:
        reasons.append("enforcement_failures")
    if status.pending_packages:
        reasons.append("apps_awaiting_approval")
    if "not_device_owner" in reasons:
        return FLEET_MISCONFIGURED, reasons
    if reasons:
        return FLEET_NEEDS_ATTENTION, reasons
    return FLEET_ONLINE, reasons


FLEET_STATUS_SENSOR = SensorEntityDescription(
    key="fleet_status",
    translation_key="fleet_status",
    device_class=SensorDeviceClass.ENUM,
    options=FLEET_STATUS_OPTIONS,
)


ACTION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_lock_screen",
        translation_key="last_lock_screen",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_reboot",
        translation_key="last_reboot",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_configure_wifi",
        translation_key="last_configure_wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalMdmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [LocalMdmSensor(coordinator, d) for d in SENSORS]
        + [LocalMdmActionSensor(coordinator, d) for d in ACTION_SENSORS]
        + [LocalMdmFleetStatusSensor(coordinator, FLEET_STATUS_SENSOR)]
    )


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


class LocalMdmActionSensor(LocalMdmEntity, SensorEntity):
    """Outcome of an immediate action (lock_screen, reboot, configure_wifi).

    These actions answer with a bare acknowledgement and nothing to poll
    afterwards, so the result lives on the coordinator, not the DPC status
    document; ``None`` until the action has run at least once this session.
    """

    @property
    def native_value(self) -> Any:
        action = self.coordinator.last_actions.get(self.entity_description.key)
        return action["result"] if action else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        action = self.coordinator.last_actions.get(self.entity_description.key)
        if action is None:
            return None
        return {"message": action["message"], "at": action["at"]}


class LocalMdmFleetStatusSensor(LocalMdmEntity, SensorEntity):
    """One state per tablet for fleet dashboards: online, offline, misconfigured.

    The attributes carry what a dashboard row needs without looking up other
    entity ids, so a renamed or newly paired tablet shows up correctly.
    """

    @property
    def native_value(self) -> str:
        return fleet_status(self.coordinator.data)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.data
        _state, reasons = fleet_status(status)
        return {
            "reasons": reasons,
            "tablet": self.coordinator.config_entry.title,
            "reachable": status.is_reachable,
            "device_owner": status.is_device_owner,
            "kiosk_active": status.lock_task_active,
            "battery": status.battery_level,
            "last_report": status.reported_at,
            "enforcement_failures": status.enforcement_failures,
            "pending_packages": status.pending_packages,
            "tier": status.tier,
        }
