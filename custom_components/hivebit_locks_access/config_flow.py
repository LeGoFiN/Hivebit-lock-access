"""Setup screen. Config entries can only be created by HA admins (HIVEBIT at
commissioning); the first authorized person is chosen here."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LOCAL_KEY,
    CONF_NODE_ID,
    CONF_OWNER_USER_ID,
    CONF_PROFILE,
    CONF_PROTOCOL_VERSION,
    CONF_UNLOCK_KEY,
    CONF_UNLOCK_KEY_ID,
    DOMAIN,
    PROTOCOL_VERSIONS,
)
from .lockcore.profiles import PROFILES
from .transport_factory import build_transport

CONNECT_TIMEOUT = 20


async def async_validate_connection(data: dict[str, Any]) -> bool:
    """Try to reach the lock through the gateway. Patched out in tests."""
    transport = build_transport(data)
    connected = asyncio.Event()
    transport.set_callbacks(lambda *_: None, lambda ok: connected.set() if ok else None)
    await transport.async_start()
    try:
        await asyncio.wait_for(connected.wait(), CONNECT_TIMEOUT)
        return True
    except TimeoutError:
        return False
    finally:
        await transport.async_stop()


class AccessConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a lock."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input.get(CONF_UNLOCK_KEY, "")
            if key and len(key) != 8:
                errors[CONF_UNLOCK_KEY] = "unlock_key_length"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_GATEWAY_ID]}_{user_input[CONF_NODE_ID]}"
                )
                self._abort_if_unique_id_configured()
                if await async_validate_connection(user_input):
                    return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
                errors["base"] = "cannot_connect"

        users = [
            SelectOptionDict(value=u.id, label=u.name or u.id)
            for u in await self.hass.auth.async_get_users()
            if not u.system_generated and u.is_active
        ]
        profiles = [SelectOptionDict(value=pid, label=cls.name) for pid, cls in PROFILES.items()]
        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Front door")): str,
                vol.Required(CONF_PROFILE, default=defaults.get(CONF_PROFILE, "moes_wdl_x1_zigbee")): SelectSelector(
                    SelectSelectorConfig(options=profiles, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_GATEWAY_ID, default=defaults.get(CONF_GATEWAY_ID, "")): str,
                vol.Required(CONF_LOCAL_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Required(CONF_PROTOCOL_VERSION, default=defaults.get(CONF_PROTOCOL_VERSION, "3.5")): SelectSelector(
                    SelectSelectorConfig(options=list(PROTOCOL_VERSIONS), mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, "")): str,
                vol.Required(CONF_NODE_ID, default=defaults.get(CONF_NODE_ID, "")): str,
                vol.Optional(CONF_UNLOCK_KEY_ID, default=defaults.get(CONF_UNLOCK_KEY_ID, 1)): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=65535)
                ),
                vol.Optional(CONF_UNLOCK_KEY, default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_OWNER_USER_ID): SelectSelector(
                    SelectSelectorConfig(options=users, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
