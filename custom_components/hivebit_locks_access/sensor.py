"""Battery level. (No "last event" sensor: entity states are readable by every
HA user, and the timeline is for owners only.)"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AccessEntity
from .manager import AccessManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: AccessManager = entry.runtime_data
    if manager.profile.capabilities.battery:
        async_add_entities([BatterySensor(manager)])


class BatterySensor(AccessEntity, SensorEntity):
    """Lock battery."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: AccessManager) -> None:
        super().__init__(manager, "battery")

    @property
    def native_value(self) -> int | None:
        return self.manager.battery
