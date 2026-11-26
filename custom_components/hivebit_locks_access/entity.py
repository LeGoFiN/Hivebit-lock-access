"""Shared entity base."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import AccessManager


class AccessEntity(Entity):
    """Entity bound to one lock's manager. Read-only state only."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AccessManager, key: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry_id)},
            name=manager.name,
            manufacturer="HIVEBIT",
            model=manager.profile.name,
        )

    @property
    def available(self) -> bool:
        return self.manager.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.manager.async_add_listener(self._on_update))

    def _on_update(self, topic: str, _payload: dict[str, Any]) -> None:
        if topic == "state":
            self.async_write_ha_state()
