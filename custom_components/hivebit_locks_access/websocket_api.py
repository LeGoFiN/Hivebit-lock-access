"""WebSocket API for the dashboard card.

Every command takes the lock's ``entry_id`` and is checked against the
caller's HA user (``connection.user``) by the manager. There are no HA
services for these actions, so automations, scripts and AI assistants have
nothing to call; a long-lived token only carries its own user's role.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized

from .const import DOMAIN
from .lockcore.events import Method
from .manager import AccessError, AccessManager
from .models import GuestKind
from .policy import Caller

P = f"{DOMAIN}/"
Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], AccessManager],
    Awaitable[Any],
]


def _manager(hass: HomeAssistant, entry_id: str) -> AccessManager:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise AccessError("Unknown lock.")
    return entry.runtime_data


def _guarded(func: Handler) -> Callable[..., Awaitable[None]]:
    @wraps(func)
    async def wrapper(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        try:
            manager = _manager(hass, msg["entry_id"])
            result = await func(hass, connection, msg, manager)
        except Unauthorized:
            connection.send_error(msg["id"], "unauthorized", "Only an authorized person can do this.")
            return
        except AccessError as err:
            connection.send_error(msg["id"], "refused", str(err))
            return
        connection.send_result(msg["id"], result)

    return wrapper


ENTRY = {vol.Required("entry_id"): str}


@websocket_api.websocket_command({vol.Required("type"): P + "locks"})
@websocket_api.async_response
async def ws_locks(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Locks this user has a role on, with their role and what the lock can do."""
    out = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        manager: AccessManager = entry.runtime_data
        caller = manager.policy.caller(connection.user.id)
        if caller is Caller.NONE:
            continue
        person = manager.policy.person_for(connection.user.id)
        out.append(
            {
                **manager.state_dict(),
                "role": caller,
                "me": person.name if person else connection.user.name,
                "capabilities": manager.capabilities_dict(),
            }
        )
    connection.send_result(msg["id"], {"locks": out})


@websocket_api.websocket_command({vol.Required("type"): P + "subscribe", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_subscribe(hass, connection, msg, manager: AccessManager):
    """Live updates. Everyone with a role gets door state; owners get the rest."""
    user_id = connection.user.id
    manager.policy.require_member(user_id)
    msg_id = msg["id"]

    @callback
    def forward(topic: str, payload: dict[str, Any]) -> None:
        caller = manager.policy.caller(user_id)  # re-checked on every push
        if caller is Caller.NONE:
            return
        if topic != "state" and caller is not Caller.OWNER:
            return
        connection.send_message(websocket_api.event_message(msg_id, {"topic": topic, "data": payload}))

    connection.subscriptions[msg_id] = manager.async_add_listener(forward)
    return manager.state_dict()


@websocket_api.websocket_command({vol.Required("type"): P + "unlock", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_unlock(hass, connection, msg, manager: AccessManager):
    await manager.async_unlock(connection.user.id)
    return {"ok": True}


@websocket_api.websocket_command({vol.Required("type"): P + "people", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_people(hass, connection, msg, manager: AccessManager):
    manager.policy.require_owner(connection.user.id)
    return {**manager.people_dict(), **manager.session_dict()}


@websocket_api.websocket_command({vol.Required("type"): P + "ha_users", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_ha_users(hass, connection, msg, manager: AccessManager):
    """HA accounts an owner may link to a person or mark as a tablet."""
    manager.policy.require_owner(connection.user.id)
    linked = {p.ha_user_id for p in manager.store.active_persons() if p.ha_user_id}
    users = []
    for user in await hass.auth.async_get_users():
        if user.system_generated or not user.is_active:
            continue
        users.append(
            {
                "id": user.id,
                "name": user.name,
                "is_admin": user.is_admin,
                "linked": user.id in linked,
                "tablet": user.id in manager.store.tablet_user_ids,
            }
        )
    return {"users": sorted(users, key=lambda u: (u["name"] or "").lower())}


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "person/add",
        **ENTRY,
        vol.Required("name"): str,
        vol.Optional("ha_user_id"): vol.Any(str, None),
        vol.Optional("owner", default=False): bool,
        vol.Optional("expires_at"): vol.Any(vol.Coerce(float), None),
        vol.Optional("notify_on_arrival", default=False): bool,
    }
)
@websocket_api.async_response
@_guarded
async def ws_person_add(hass, connection, msg, manager: AccessManager):
    person = await manager.async_add_person(
        connection.user.id,
        name=msg["name"],
        ha_user_id=msg.get("ha_user_id"),
        owner=msg["owner"],
        expires_at=msg.get("expires_at"),
        notify_on_arrival=msg["notify_on_arrival"],
    )
    return {"person_id": person.id}


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "person/update",
        **ENTRY,
        vol.Required("person_id"): str,
        vol.Optional("name"): str,
        vol.Optional("ha_user_id"): vol.Any(str, None),
        vol.Optional("owner"): bool,
        vol.Optional("expires_at"): vol.Any(vol.Coerce(float), None),
        vol.Optional("notify_on_arrival"): bool,
    }
)
@websocket_api.async_response
@_guarded
async def ws_person_update(hass, connection, msg, manager: AccessManager):
    changes = {
        k: msg[k]
        for k in ("name", "ha_user_id", "owner", "expires_at", "notify_on_arrival")
        if k in msg
    }
    await manager.async_update_person(connection.user.id, msg["person_id"], **changes)
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): P + "person/remove", **ENTRY, vol.Required("person_id"): str}
)
@websocket_api.async_response
@_guarded
async def ws_person_remove(hass, connection, msg, manager: AccessManager):
    await manager.async_remove_person(connection.user.id, msg["person_id"])
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): P + "tablets/set", **ENTRY, vol.Required("user_ids"): [str]}
)
@websocket_api.async_response
@_guarded
async def ws_tablets_set(hass, connection, msg, manager: AccessManager):
    await manager.async_set_tablets(connection.user.id, msg["user_ids"])
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "enrol/start",
        **ENTRY,
        vol.Required("person_id"): str,
        vol.Required("method"): vol.In([Method.FINGERPRINT, Method.CARD, Method.PIN]),
    }
)
@websocket_api.async_response
@_guarded
async def ws_enrol_start(hass, connection, msg, manager: AccessManager):
    await manager.async_start_enrol(connection.user.id, msg["person_id"], Method(msg["method"]))
    return manager.session_dict()


@websocket_api.websocket_command({vol.Required("type"): P + "enrol/cancel", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_enrol_cancel(hass, connection, msg, manager: AccessManager):
    await manager.async_cancel_enrol(connection.user.id)
    return manager.session_dict()


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "credential/assign",
        **ENTRY,
        vol.Required("credential_id"): str,
        vol.Required("person_id"): str,
    }
)
@websocket_api.async_response
@_guarded
async def ws_credential_assign(hass, connection, msg, manager: AccessManager):
    await manager.async_assign_credential(connection.user.id, msg["credential_id"], msg["person_id"])
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): P + "credential/remove", **ENTRY, vol.Required("credential_id"): str}
)
@websocket_api.async_response
@_guarded
async def ws_credential_remove(hass, connection, msg, manager: AccessManager):
    await manager.async_remove_credential(connection.user.id, msg["credential_id"])
    return {"ok": True}


@websocket_api.websocket_command({vol.Required("type"): P + "guest_codes", **ENTRY})
@websocket_api.async_response
@_guarded
async def ws_guest_codes(hass, connection, msg, manager: AccessManager):
    manager.policy.require_owner(connection.user.id)
    return manager.guest_codes_dict()


_HHMM = vol.All([vol.Coerce(int)], vol.Length(min=2, max=2))


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "guest_code/create",
        **ENTRY,
        vol.Required("name"): str,
        vol.Required("kind"): vol.In([k.value for k in GuestKind]),
        vol.Optional("start"): vol.Any(vol.Coerce(float), None),
        vol.Optional("end"): vol.Any(vol.Coerce(float), None),
        vol.Optional("weekdays"): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
        vol.Optional("daily_from"): _HHMM,
        vol.Optional("daily_to"): _HHMM,
    }
)
@websocket_api.async_response
@_guarded
async def ws_guest_code_create(hass, connection, msg, manager: AccessManager):
    code = await manager.async_create_guest_code(
        connection.user.id,
        name=msg["name"],
        kind=GuestKind(msg["kind"]),
        start=msg.get("start"),
        end=msg.get("end"),
        weekdays=msg.get("weekdays"),
        daily_from=msg.get("daily_from"),
        daily_to=msg.get("daily_to"),
    )
    return code.as_dict()


@websocket_api.websocket_command(
    {vol.Required("type"): P + "guest_code/revoke", **ENTRY, vol.Required("slot"): int}
)
@websocket_api.async_response
@_guarded
async def ws_guest_code_revoke(hass, connection, msg, manager: AccessManager):
    await manager.async_revoke_guest_code(connection.user.id, msg["slot"])
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): P + "timeline",
        **ENTRY,
        vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=200)),
        vol.Optional("before_seq"): int,
    }
)
@websocket_api.async_response
@_guarded
async def ws_timeline(hass, connection, msg, manager: AccessManager):
    entries = await manager.async_timeline(
        connection.user.id, limit=msg["limit"], before_seq=msg.get("before_seq")
    )
    return {"entries": entries}


COMMANDS = (
    ws_locks,
    ws_subscribe,
    ws_unlock,
    ws_people,
    ws_ha_users,
    ws_person_add,
    ws_person_update,
    ws_person_remove,
    ws_tablets_set,
    ws_enrol_start,
    ws_enrol_cancel,
    ws_credential_assign,
    ws_credential_remove,
    ws_guest_codes,
    ws_guest_code_create,
    ws_guest_code_revoke,
    ws_timeline,
)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all commands (once per HA run)."""
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
