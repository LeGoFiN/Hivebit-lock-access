"""Door contact."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AccessEntity
from .manager import AccessManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: AccessManager = entry.runtime_data
    if manager.profile.capabilities.door_sensor:
        async_add_entities([DoorSensor(manager)])


class DoorSensor(AccessEntity, BinarySensorEntity):
    """Door open / closed."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_translation_key = "door"

    def __init__(self, manager: AccessManager) -> None:
        super().__init__(manager, "door")

    @property
    def is_on(self) -> bool | None:
        return self.manager.door_open
