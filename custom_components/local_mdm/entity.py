"""Base entity for the Local MDM integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, CONF_SUGGESTED_AREA, DOMAIN, MANUFACTURER, MODEL
from .coordinator import LocalMdmCoordinator


class LocalMdmEntity(CoordinatorEntity[LocalMdmCoordinator]):
    """Ties an entity to the tablet device and sets the unique id scheme."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LocalMdmCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.data.device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        # The Wi-Fi MAC in use links this device to the same tablet in other
        # integrations (UniFi Network clients, anything keyed by MAC); a tablet
        # paired from UniFi carries the client's MAC from the start.
        mac = coordinator.data.wifi_mac or coordinator.config_entry.data.get(CONF_MAC)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer=MANUFACTURER,
            model=MODEL,
            # The entry title: the UniFi alias (Kitchen-Tab) for a tablet
            # picked from UniFi, "Tablet <id>" for one entered by hand.
            name=coordinator.config_entry.title,
            sw_version=coordinator.data.dpc_version,
        )
        if area := coordinator.config_entry.data.get(CONF_SUGGESTED_AREA):
            self._attr_device_info["suggested_area"] = area
