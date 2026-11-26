"""Lock entity. Unlock is checked against the caller's role inside the entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AccessEntity
from .manager import AccessManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: AccessManager = entry.runtime_data
    async_add_entities([AccessLock(manager)])


class AccessLock(AccessEntity, LockEntity):
    """The door. Anyone may read it; only allowed users can open it."""

    _attr_name = None
    _attr_translation_key = "door_lock"

    def __init__(self, manager: AccessManager) -> None:
        super().__init__(manager, "lock")

    @property
    def is_locked(self) -> bool | None:
        return self.manager.locked

    async def async_unlock(self, **kwargs: Any) -> None:
        # HA sets the service call's context on the entity before calling us,
        # so the caller's user ID is here. No user (automation, script,
        # Node-RED) or a user without a role is refused by the manager.
        user_id = self._context.user_id if self._context else None
        await self.manager.async_unlock(user_id)

    async def async_lock(self, **kwargs: Any) -> None:
        raise HomeAssistantError("This lock locks itself when the door closes.")
