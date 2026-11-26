"""HIVEBIT Locks Access: owner-controlled access for smart locks in Home Assistant."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import transport_factory
from .const import (
    CONF_OWNER_USER_ID,
    CONF_PROFILE,
    CONF_UNLOCK_KEY,
    CONF_UNLOCK_KEY_ID,
    DOMAIN,
)
from .eventlog import EventLog
from .lockcore.profiles import get_profile
from .manager import AccessManager
from .models import Person, Role
from .store import AccessStore
from .websocket_api import async_register

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.LOCK, Platform.BINARY_SENSOR, Platform.SENSOR]

type AccessConfigEntry = ConfigEntry[AccessManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AccessConfigEntry) -> bool:
    store = AccessStore(hass, entry.entry_id)
    await store.async_load()
    if not store.persons:
        await _seed_owner(hass, store, entry.data[CONF_OWNER_USER_ID])

    log = EventLog(Path(hass.config.path(DOMAIN, f"events_{entry.entry_id}.db")))
    await hass.async_add_executor_job(log.open)

    manager = AccessManager(
        hass,
        entry_id=entry.entry_id,
        name=entry.data.get(CONF_NAME, entry.title),
        profile=get_profile(entry.data[CONF_PROFILE]),
        transport=transport_factory.build_transport(dict(entry.data)),
        store=store,
        log=log,
        unlock_key_id=int(entry.data.get(CONF_UNLOCK_KEY_ID, 1)),
        unlock_key=entry.data.get(CONF_UNLOCK_KEY, ""),
    )
    entry.runtime_data = manager
    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AccessConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        manager = entry.runtime_data
        await manager.async_stop()
        await hass.async_add_executor_job(manager.log.close)
    return unloaded


async def _seed_owner(hass: HomeAssistant, store: AccessStore, user_id: str) -> None:
    user = await hass.auth.async_get_user(user_id)
    person = Person(
        id=uuid.uuid4().hex,
        name=(user.name if user and user.name else "Owner"),
        member_id=store.allocate_member_id(),
        role=Role.OWNER,
        ha_user_id=user_id,
        created_at=time.time(),
        created_by="setup",
    )
    store.persons[person.id] = person
    await store.async_save()
