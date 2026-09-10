"""Base entity for the Local MDM integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LocalMdmCoordinator


class LocalMdmEntity(CoordinatorEntity[LocalMdmCoordinator]):
    """Ties an entity to the tablet device and sets the unique id scheme."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LocalMdmCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.data.device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"Tablet {device_id}",
            sw_version=coordinator.data.dpc_version,
        )
