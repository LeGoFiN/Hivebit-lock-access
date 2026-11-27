"""End-to-end behaviour through the WebSocket API and the lock entity,
including the attack cases from the spec's threat model."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.hivebit_locks_access.const import DOMAIN, EVENT_ACCESS
from custom_components.hivebit_locks_access.lockcore.transport.fake import FakeTransport

from .conftest import UserFixture

P = f"{DOMAIN}/"


OPENED = base64.b64encode(bytes([0x00, 0x00, 0x01])).decode()  # DP 49 reply: opened


def _raw(*b: int) -> str:
    return base64.b64encode(bytes(b)).decode()


class Ws:
    """Small helper around the test websocket client."""

    def __init__(self, client: Any, entry_id: str) -> None:
        self.client = client
        self.entry_id = entry_id

    async def call(self, command: str, /, **data: Any) -> dict[str, Any]:
        await self.client.send_json_auto_id({"type": P + command, "entry_id": self.entry_id, **data})
        return await self.client.receive_json()


@pytest.fixture
async def ws(hass_ws_client, entry):
    async def connect(user: UserFixture) -> Ws:
        return Ws(await hass_ws_client(access_token=user.token), entry.entry_id)

    return connect


async def _add_son(owner: Ws, users) -> str:
    res = await owner.call("person/add", name="Son", ha_user_id=users["son"].id)
    assert res["success"], res
    return res["result"]["person_id"]


async def test_owner_seeded_and_entities_exist(hass: HomeAssistant, entry, ws, users) -> None:
    father = await ws(users["father"])
    res = await father.call("people")
    assert res["success"]
    people = res["result"]["people"]
    assert [(p["name"], p["role"]) for p in people] == [("Father", "owner")]
    assert hass.states.get("lock.front_door") is not None
    assert hass.states.get("binary_sensor.front_door_door_contact") is not None


@pytest.mark.parametrize("who", ["son", "worker", "tablet", "hivebit"])
async def test_non_owners_cannot_manage(hass: HomeAssistant, entry, ws, users, who) -> None:
    """T1/T2: any token that is not an owner's is refused on every mutation."""
    father = await ws(users["father"])
    await _add_son(father, users)
    attacker = await ws(users[who])
    for command, data in [
        ("person/add", {"name": "Friend"}),
        ("guest_code/create", {"name": "Friend", "kind": "one_time"}),
        ("enrol/start", {"person_id": "x", "method": "fingerprint"}),
        ("timeline", {}),
        ("people", {}),
        ("tablets/set", {"user_ids": [users[who].id]}),
    ]:
        res = await attacker.call(command, **data)
        assert not res["success"], (who, command)
        assert res["error"]["code"] == "unauthorized", (who, command, res)


async def test_lock_entity_unlock_roles(hass: HomeAssistant, entry, ws, users, fake: FakeTransport) -> None:
    father = await ws(users["father"])
    await _add_son(father, users)
    res = await father.call("tablets/set", user_ids=[users["tablet"].id])
    assert res["success"], res

    async def unlock(user_id: str | None) -> None:
        await hass.services.async_call(
            "lock", "unlock", {"entity_id": "lock.front_door"}, blocking=True,
            context=Context(user_id=user_id),
        )

    for who in ("father", "son", "tablet"):
        await unlock(users[who].id)
        fake.report(49, OPENED)  # the lock's reply
        await hass.async_block_till_done()
    assert [w.dp for w in fake.sent] == [49, 49, 49]

    for who in ("worker", "hivebit"):
        with pytest.raises(Unauthorized):
            await unlock(users[who].id)
    with pytest.raises(Unauthorized):  # automation / script / Node-RED
        await unlock(None)
    assert len(fake.sent) == 3

    timeline = (await father.call("timeline"))["result"]["entries"]
    texts = [e["text"] for e in timeline if e["kind"] == "unlock"]
    assert "Unlocked remotely by Father" in texts
    assert "Unlocked remotely by Son" in texts
    assert any(t.startswith("Unlocked from the wall tablet") for t in texts)


async def test_enrol_fingerprint_names_entries(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    son_id = await _add_son(father, users)
    res = await father.call("enrol/start", person_id=son_id, method="fingerprint")
    assert res["success"], res
    member = res["result"]["session"]["member_id"]
    assert fake.sent[-1].dp == 54

    hi, lo = member >> 8, member & 0xFF
    fake.report(54, _raw(3, 0x00, 0, hi, lo, 0, 15, 4, 0))
    for n in range(1, 5):
        fake.report(54, _raw(3, 0xFC, 0, hi, lo, 0, 15, n, 0))
    fake.report(54, _raw(3, 0xFF, 0, hi, lo, 0, 15, 4, 0))
    await hass.async_block_till_done()

    people = (await father.call("people"))["result"]
    son = next(p for p in people["people"] if p["id"] == son_id)
    assert [(c["method"], c["lock_ref"], c["status"]) for c in son["credentials"]] == [
        ("fingerprint", 15, "active")
    ]
    assert people["session"]["state"] == "done"

    fake.report(1, 15)
    await hass.async_block_till_done()
    timeline = (await father.call("timeline"))["result"]["entries"]
    assert timeline[0]["text"] == "Son opened with fingerprint"


async def test_unknown_credential_alert_and_retroactive_name(hass: HomeAssistant, entry, ws, users, fake) -> None:
    """T3: a fingerprint enrolled at the lock's menu is flagged, then named."""
    events = []
    hass.bus.async_listen(EVENT_ACCESS, lambda e: events.append(e.data))
    father = await ws(users["father"])
    son_id = await _add_son(father, users)

    fake.report(1, 21)
    await hass.async_block_till_done()
    assert events[-1]["alert"] == "urgent"
    assert events[-1]["text"] == "Unknown fingerprint #21 opened the door"

    unknown = (await father.call("people"))["result"]["unknown"]
    assert [(u["method"], u["lock_ref"]) for u in unknown] == [("fingerprint", 21)]
    res = await father.call("credential/assign", credential_id=unknown[0]["id"], person_id=son_id)
    assert res["success"], res

    timeline = (await father.call("timeline"))["result"]["entries"]
    first_use = next(e for e in timeline if e["kind"] == "unlock")
    assert first_use["text"] == "Son opened with fingerprint"  # renamed in history


async def test_snapshot_values_are_not_events(hass: HomeAssistant, entry, ws, users, fake) -> None:
    fake.report(1, 11, snapshot=True)
    fake.report(47, "closed", snapshot=True)
    fake.report(10, 88, snapshot=True)
    await hass.async_block_till_done()
    father = await ws(users["father"])
    timeline = (await father.call("timeline"))["result"]["entries"]
    assert not [e for e in timeline if e["kind"] == "unlock"]
    assert hass.states.get("sensor.front_door_battery").state == "88"


async def test_remove_person_deletes_on_lock_and_retires_ids(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    son_id = await _add_son(father, users)
    await father.call("enrol/start", person_id=son_id, method="card")
    member = fake.sent[-1]
    m = base64.b64decode(member.value)[3:5]
    fake.report(54, _raw(2, 0xFF, 0, m[0], m[1], 0, 7, 1, 0))
    await hass.async_block_till_done()

    res = await father.call("person/remove", person_id=son_id)
    assert res["success"], res
    sent = base64.b64decode(fake.sent[-1].value)
    assert fake.sent[-1].dp == 55 and sent[0] == 0x00 and sent[7] == 0x00  # all of member

    fake.report(55, _raw(0, 0, 0, m[0], m[1], 0x03, 0xE7, 0x00, 0xFF))
    await hass.async_block_till_done()

    # The removed card is used again (e.g. before a delete reached the lock)
    events = []
    hass.bus.async_listen(EVENT_ACCESS, lambda e: events.append(e.data))
    fake.report(5, 7)
    await hass.async_block_till_done()
    assert events[-1]["alert"] == "urgent"
    assert "Unknown card #7" in events[-1]["text"]


async def test_guest_code_one_time_flow(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    res = await father.call("guest_code/create", name="Plumber", kind="one_time")
    assert res["success"], res
    code = res["result"]
    assert code["slot"] == 901 and len(code["pin"]) == 6
    raw = base64.b64decode(fake.sent[-1].value)
    assert fake.sent[-1].dp == 24 and raw[20] == 1 and raw[21:].decode() == code["pin"]

    fake.report(3, 901)
    await hass.async_block_till_done()
    assert fake.sent[-1].dp == 25  # slot freed after use
    timeline = (await father.call("timeline"))["result"]["entries"]
    assert any(e["text"] == "Guest 'Plumber' used code" for e in timeline)
    assert (await father.call("guest_codes"))["result"]["guest_codes"] == []


async def test_guest_code_weekly_and_revoke(hass: HomeAssistant, entry, ws, users, fake) -> None:
    import time

    father = await ws(users["father"])
    res = await father.call(
        "guest_code/create", name="Cleaner", kind="weekly", end=time.time() + 30 * 86400,
        weekdays=[0, 3], daily_from=[9, 0], daily_to=[12, 0],
    )
    assert res["success"], res
    raw = base64.b64decode(fake.sent[-1].value)
    assert raw[14:20] == bytes([2, 0b1001, 9, 0, 12, 0])
    res = await father.call("guest_code/revoke", slot=res["result"]["slot"])
    assert res["success"]
    assert fake.sent[-1].dp == 25


async def test_last_owner_cannot_be_removed(hass: HomeAssistant, entry, ws, users) -> None:
    father = await ws(users["father"])
    me = (await father.call("people"))["result"]["people"][0]
    res = await father.call("person/update", person_id=me["id"], owner=False)
    assert not res["success"] and res["error"]["code"] == "refused"


async def test_co_owner_has_equal_rights(hass: HomeAssistant, entry, ws, users) -> None:
    father = await ws(users["father"])
    res = await father.call("person/add", name="Mother", ha_user_id=users["son"].id, owner=True)
    assert res["success"], res
    mother = await ws(users["son"])
    res = await mother.call("guest_code/create", name="Driver", kind="one_time")
    assert res["success"], res


async def test_unknown_user_sees_no_locks(hass: HomeAssistant, entry, hass_ws_client, users) -> None:
    client = await hass_ws_client(access_token=users["worker"].token)
    await client.send_json_auto_id({"type": P + "locks"})
    res = await client.receive_json()
    assert res["result"]["locks"] == []


async def test_lock_offline_refuses_writes(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    fake.set_available(False)
    await hass.async_block_till_done()
    res = await father.call("guest_code/create", name="Plumber", kind="one_time")
    assert not res["success"] and "offline" in res["error"]["message"]
    assert hass.states.get("lock.front_door").state == "unavailable"
    res = await father.call("unlock")
    assert not res["success"] and "offline" in res["error"]["message"]
    assert fake.sent == []


async def test_enrolment_outside_dashboard_is_flagged(hass: HomeAssistant, entry, ws, users, fake) -> None:
    """Enrolled through the Tuya app/cloud while the gateway is online (T6)."""
    events = []
    hass.bus.async_listen(EVENT_ACCESS, lambda e: events.append(e.data))
    fake.report(54, _raw(3, 0xFF, 0, 0, 2, 0, 30, 4, 0))
    await hass.async_block_till_done()
    assert events[-1]["alert"] == "urgent"
    assert events[-1]["text"] == "Fingerprint #30 was added outside the dashboard"
    father = await ws(users["father"])
    unknown = (await father.call("people"))["result"]["unknown"]
    assert [(u["method"], u["lock_ref"]) for u in unknown] == [("fingerprint", 30)]


async def test_enrol_failure_reported(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    son_id = await _add_son(father, users)
    res = await father.call("enrol/start", person_id=son_id, method="pin")
    member = res["result"]["session"]["member_id"]
    fake.report(54, _raw(1, 0xFD, 0, member >> 8, member & 0xFF, 0, 12, 2, 0x02))
    await hass.async_block_till_done()
    session = (await father.call("people"))["result"]["session"]
    assert session["state"] == "failed" and session["reason"] == "duplicate"
    # a second session can start after a failure
    res = await father.call("enrol/start", person_id=son_id, method="pin")
    assert res["success"], res


async def test_only_one_enrolment_at_a_time(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await ws(users["father"])
    son_id = await _add_son(father, users)
    assert (await father.call("enrol/start", person_id=son_id, method="fingerprint"))["success"]
    res = await father.call("enrol/start", person_id=son_id, method="card")
    assert not res["success"] and res["error"]["code"] == "refused"
    res = await father.call("enrol/cancel")
    assert res["success"] and res["result"]["session"]["state"] == "cancelled"
    assert base64.b64decode(fake.sent[-1].value)[1] == 0xFE


async def test_lock_state_follows_door(hass: HomeAssistant, entry, ws, users, fake) -> None:
    """MOES: DP 57 is meaningless; closed door = locked, unlock = briefly unlocked."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    fake.report(57, True, snapshot=True)
    fake.report(47, "closed", snapshot=True)
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"

    fake.report(1, 11)  # fingerprint opens the bolt, door still closed
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocked"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"  # relocked by itself

    fake.report(1, 11)
    fake.report(47, "open")
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocked"
    fake.report(57, True)  # ignored
    fake.report(47, "closed")
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"


async def _remote_unlock_setup(hass: HomeAssistant, ws, users, fake):
    fake.report(47, "closed", snapshot=True)
    await hass.async_block_till_done()
    return await ws(users["father"])


async def _unlock_entries(father) -> list[dict[str, Any]]:
    timeline = (await father.call("timeline"))["result"]["entries"]
    return [e for e in timeline if e["kind"].startswith("unlock")]


async def test_remote_unlock_waits_for_the_lock(hass: HomeAssistant, entry, ws, users, fake) -> None:
    """Sent is not open: the entity shows unlocking until the lock confirms,
    and the relock timer starts from the confirmation."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    father = await _remote_unlock_setup(hass, ws, users, fake)
    res = await father.call("unlock")
    assert res["success"], res
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocking"
    assert await _unlock_entries(father) == []  # nothing logged yet

    # our own command echoed back by the gateway is not a reply
    fake.report(49, fake.sent[-1].value)
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocking"

    # the lock is slow: 8 s later it opens. The old code had relocked by now.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=8))
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocking"
    fake.report(49, OPENED)
    fake.report(22, True)  # a second confirmation DP for the same unlock
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocked"
    assert [e["text"] for e in await _unlock_entries(father)] == ["Unlocked remotely by Father"]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=14))
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"


async def test_remote_unlock_door_opens_before_reply(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await _remote_unlock_setup(hass, ws, users, fake)
    assert (await father.call("unlock"))["success"]
    fake.report(47, "open")
    fake.report(49, OPENED)  # the reply arrives after the door opened
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocked"
    assert [e["text"] for e in await _unlock_entries(father)] == ["Unlocked remotely by Father"]


async def test_remote_unlock_not_confirmed(hass: HomeAssistant, entry, ws, users, fake) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    father = await _remote_unlock_setup(hass, ws, users, fake)
    assert (await father.call("unlock"))["success"]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=21))
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"
    assert [e["text"] for e in await _unlock_entries(father)] == [
        "Remote unlock by Father was not confirmed by the lock"
    ]


async def test_remote_unlock_refused(hass: HomeAssistant, entry, ws, users, fake) -> None:
    father = await _remote_unlock_setup(hass, ws, users, fake)
    assert (await father.call("unlock"))["success"]
    fake.report(49, base64.b64encode(bytes([0x01, 0x00, 0x01])).decode())
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "locked"
    assert [e["text"] for e in await _unlock_entries(father)] == ["Remote unlock by Father refused by the lock"]


async def test_remote_unlock_from_outside_is_urgent(hass: HomeAssistant, entry, ws, users, fake) -> None:
    """T6: the door opened remotely but nobody asked from here."""
    events = []
    hass.bus.async_listen(EVENT_ACCESS, lambda e: events.append(e.data))
    father = await _remote_unlock_setup(hass, ws, users, fake)
    fake.report(49, OPENED)
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_door").state == "unlocked"
    entries = await _unlock_entries(father)
    assert [e["text"] for e in entries] == ["Unlocked remotely from outside HIVEBIT (Tuya app or cloud)"]
    assert events[-1]["alert"] == "urgent"
