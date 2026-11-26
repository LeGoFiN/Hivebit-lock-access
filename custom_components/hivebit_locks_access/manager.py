"""The access manager: one per lock. All rules and all lock traffic go through here."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import ENROL_TIMEOUT_S, EVENT_ACCESS, ONE_TIME_DEFAULT_HOURS, RETENTION_DAYS
from .eventlog import EventLog
from .lockcore.events import (
    AlarmReport,
    BatteryReport,
    DeleteReport,
    DoorReport,
    EnrolReport,
    EnrolStage,
    LockReport,
    LockStateReport,
    Method,
    RemoteUnlockResult,
    UnlockReport,
)
from .lockcore.profiles import GuestCodeSpec, LockProfile, ProfileError
from .lockcore.transport import Transport, TransportError
from .models import (
    Credential,
    CredentialSource,
    CredentialStatus,
    GuestCode,
    GuestKind,
    GuestState,
    Person,
    Role,
)
from .policy import AccessPolicy, Caller
from .store import AccessStore

_LOGGER = logging.getLogger(__name__)

SYSTEM = "system"

ALARM_TEXT = {
    "wrong_finger": "Wrong fingerprint",
    "wrong_password": "Wrong PIN",
    "wrong_card": "Unknown card",
    "pry": "Forced entry alarm",
    "key_in": "Mechanical key used",
    "low_battery": "Lock battery low",
    "unclosed_time": "Door left open",
    "tongue_bad": "Bolt fault",
    "tongue_not_out": "Bolt did not extend",
    "shock": "Shock detected",
    "power_off": "Lock power off",
    "defense": "Lock in defence mode",
}
URGENT_ALARMS = {"pry", "shock", "defense"}

METHOD_WORD = {
    Method.FINGERPRINT: "fingerprint",
    Method.CARD: "card",
    Method.PIN: "PIN",
}


class AccessError(HomeAssistantError):
    """A request was refused for a reason the user should see."""


@dataclass(slots=True)
class EnrolSession:
    """One enrolment at the lock, started from the dashboard."""

    id: str
    person_id: str
    method: Method
    member_id: int
    started_by: str
    started_at: float
    state: str = "waiting"  # waiting / enrolling / done / failed / cancelled
    presses_needed: int = 0
    presses_done: int = 0
    lock_ref: int | None = None
    reason: str | None = None
    credential_id: str | None = None

    @property
    def open(self) -> bool:
        return self.state in ("waiting", "enrolling")


class AccessManager:
    """Owns the transport, the registry and the event log for one lock."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        name: str,
        profile: LockProfile,
        transport: Transport,
        store: AccessStore,
        log: EventLog,
        unlock_key_id: int,
        unlock_key: str,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self.profile = profile
        self.transport = transport
        self.store = store
        self.log = log
        self.policy = AccessPolicy(store)
        self._unlock_key_id = unlock_key_id
        self._unlock_key = unlock_key

        self.door_open: bool | None = None
        self.locked: bool | None = None
        self.battery: int | None = None
        self.session: EnrolSession | None = None

        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._guest_timers: dict[int, CALLBACK_TYPE] = {}
        self._person_timers: dict[str, CALLBACK_TYPE] = {}
        self._session_timer: CALLBACK_TYPE | None = None
        self._handle_lock = asyncio.Lock()
        self._was_available = False
        self._stopping = False

    # Lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        self.transport.set_callbacks(self._on_dp, self._on_available)
        now = time.time()
        for code in self.store.active_guest_codes():
            if code.end <= now:
                await self._expire_guest(code.slot)
            else:
                self._schedule_guest(code)
        for person in self.store.active_persons():
            self._schedule_person(person)
        self._unsubs.append(
            async_track_time_interval(self.hass, self._purge, timedelta(hours=6))
        )
        await self._purge()
        await self.transport.async_start()

    async def async_stop(self) -> None:
        self._stopping = True
        self.transport.set_callbacks(lambda *_: None, lambda _: None)
        for unsub in [*self._unsubs, *self._guest_timers.values(), *self._person_timers.values()]:
            unsub()
        self._unsubs.clear()
        self._guest_timers.clear()
        self._person_timers.clear()
        if self._session_timer:
            self._session_timer()
            self._session_timer = None
        await self.transport.async_stop()

    @property
    def available(self) -> bool:
        return self.transport.available

    # Listeners (entities, WebSocket subscriptions) ----------------------

    @callback
    def async_add_listener(
        self, listener: Callable[[str, dict[str, Any]], None]
    ) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self, topic: str, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(topic, payload)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("access listener failed")

    # Transport callbacks ----------------------------------------------

    @callback
    def _on_available(self, available: bool) -> None:
        self.hass.async_create_task(self._async_on_available(available))

    async def _async_on_available(self, available: bool) -> None:
        if self._stopping:
            return
        async with self._handle_lock:
            if available and not self._was_available:
                self._was_available = True
                await self._record("online", {})
                await self._retry_pending_removals()
            elif not available and self._was_available:
                self._was_available = False
                await self._record("offline", {}, alert="normal")
            self._notify("state", self.state_dict())

    @callback
    def _on_dp(self, dp: int, value: object, snapshot: bool) -> None:
        reports = self.profile.decode(dp, value)
        if reports:
            self.hass.async_create_task(self._async_handle(reports, snapshot))

    async def _async_handle(self, reports: list[LockReport], snapshot: bool) -> None:
        if self._stopping:
            return
        async with self._handle_lock:
            for report in reports:
                try:
                    await self._handle(report, snapshot)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("failed to handle %s", report)

    async def _handle(self, report: LockReport, snapshot: bool) -> None:
        if isinstance(report, DoorReport):
            previous = self.door_open
            self.door_open = report.is_open
            if not snapshot and previous is not None and previous != report.is_open:
                await self._record("door", {"open": report.is_open})
            self._notify("state", self.state_dict())
        elif isinstance(report, LockStateReport):
            self.locked = report.is_locked
            self._notify("state", self.state_dict())
        elif isinstance(report, BatteryReport):
            self.battery = report.percent
            self._notify("state", self.state_dict())
        elif snapshot:
            return  # a status poll's last-unlock IDs are not new events
        elif isinstance(report, UnlockReport):
            if report.method is Method.GUEST_CODE:
                await self._guest_used(report.lock_ref)
            else:
                await self._credential_used(report.method, report.lock_ref)
        elif isinstance(report, AlarmReport):
            alert = "urgent" if report.kind in URGENT_ALARMS else "normal"
            await self._record("alarm", {"alarm": report.kind}, alert=alert)
        elif isinstance(report, RemoteUnlockResult):
            if not report.success:
                await self._record("unlock_failed", {}, alert="normal")
        elif isinstance(report, EnrolReport):
            await self._enrol_report(report)
        elif isinstance(report, DeleteReport):
            await self._delete_report(report)

    # Lock writes -------------------------------------------------------

    async def _send(self, write_factory: Callable[[], Any]) -> None:
        try:
            write = write_factory()
        except ProfileError as err:
            raise AccessError(str(err)) from err
        try:
            await self.transport.async_send(write)
        except TransportError as err:
            raise AccessError("The lock is offline. Try again when it is back.") from err

    # Unlock ------------------------------------------------------------

    async def async_unlock(self, user_id: str | None) -> None:
        caller = self.policy.require_unlock(user_id)
        if not self.profile.capabilities.remote_unlock or len(self._unlock_key) != 8:
            raise AccessError("Remote unlock is not set up for this lock.")
        await self._send(
            lambda: self.profile.encode_remote_unlock(self._unlock_key_id, self._unlock_key)
        )
        method = Method.TABLET if caller is Caller.TABLET else Method.APP
        person = self.policy.person_for(user_id)
        async with self._handle_lock:
            await self._record(
                "unlock",
                {
                    "method": method,
                    "actor_user_id": user_id,
                    "actor_name": await self._user_name(user_id),
                },
                person_id=person.id if person else None,
            )

    async def _user_name(self, user_id: str | None) -> str:
        person = self.store.person_by_user(user_id)
        if person:
            return person.name
        if user_id:
            user = await self.hass.auth.async_get_user(user_id)
            if user and user.name:
                return user.name
        return "Unknown user"

    # Local credential used --------------------------------------------

    async def _credential_used(self, method: Method, lock_ref: int) -> None:
        now = time.time()
        cred = self.store.find_credential(method, lock_ref)
        alert: str | None = None
        if cred is None or cred.status is CredentialStatus.RETIRED:
            cred = Credential(
                id=uuid.uuid4().hex,
                method=method,
                lock_ref=lock_ref,
                person_id=None,
                source=CredentialSource.LOCK_MENU,
                status=CredentialStatus.UNKNOWN,
                first_seen=now,
            )
            self.store.credentials[cred.id] = cred
            alert = "urgent"
        elif cred.status in (CredentialStatus.UNKNOWN, CredentialStatus.REMOVING):
            alert = "urgent"  # not named yet, or used after its removal was ordered
        else:
            person = self.store.persons.get(cred.person_id or "")
            if person and person.notify_on_arrival:
                alert = "normal"
        cred.last_seen = now
        await self.store.async_save()
        await self._record(
            "unlock",
            {"method": method, "lock_ref": lock_ref, "credential_id": cred.id},
            alert=alert,
            person_id=cred.person_id,
        )
        if alert == "urgent":
            self._notify("people", self.people_dict())

    async def _guest_used(self, slot: int) -> None:
        code = self.store.guest_codes.get(slot)
        if code is None or code.state is not GuestState.ACTIVE:
            await self._record(
                "unlock", {"method": Method.GUEST_CODE, "slot": slot, "guest": None}, alert="urgent"
            )
            return
        await self._record(
            "unlock",
            {"method": Method.GUEST_CODE, "slot": slot, "guest": code.name},
            alert="normal",
        )
        if code.kind is GuestKind.ONE_TIME:
            code.state = GuestState.USED
            code.used_at = time.time()
            self._cancel_guest_timer(slot)
            await self.store.async_save()
            try:  # the lock already refuses it; deleting frees the slot cleanly
                await self._send(lambda: self.profile.encode_guest_code_delete(slot))
            except AccessError:
                pass
            self._notify("guest_codes", self.guest_codes_dict())

    # People ------------------------------------------------------------

    async def async_add_person(
        self,
        user_id: str | None,
        *,
        name: str,
        ha_user_id: str | None = None,
        owner: bool = False,
        expires_at: float | None = None,
        notify_on_arrival: bool = False,
    ) -> Person:
        actor = self.policy.require_owner(user_id)
        name = self._clean_name(name)
        if ha_user_id:
            await self._check_linkable(ha_user_id)
            role = Role.OWNER if owner else Role.FAMILY
        else:
            if owner:
                raise AccessError("An authorized person needs a Home Assistant account.")
            role = Role.HOUSEHOLD
        if expires_at is not None and expires_at <= time.time():
            raise AccessError("The expiry date is in the past.")
        person = Person(
            id=uuid.uuid4().hex,
            name=name,
            member_id=self.store.allocate_member_id(),
            role=role,
            ha_user_id=ha_user_id,
            expires_at=expires_at,
            notify_on_arrival=notify_on_arrival,
            created_at=time.time(),
            created_by=actor.id,
        )
        self.store.persons[person.id] = person
        await self.store.async_save()
        self._schedule_person(person)
        await self._admin(actor, "person_added", f"{actor.name} added {person.name}", person.id)
        self._notify("people", self.people_dict())
        return person

    async def async_update_person(
        self, user_id: str | None, person_id: str, **changes: Any
    ) -> Person:
        actor = self.policy.require_owner(user_id)
        person = self._person(person_id)
        texts: list[str] = []
        if "name" in changes and changes["name"] is not None:
            old = person.name
            person.name = self._clean_name(changes["name"])
            if old != person.name:
                texts.append(f"renamed {old} to {person.name}")
        if "ha_user_id" in changes:
            new_user = changes["ha_user_id"]
            if new_user != person.ha_user_id:
                if new_user:
                    await self._check_linkable(new_user, ignore_person=person.id)
                elif person.role is Role.OWNER:
                    self._guard_last_owner(person)
                    person.role = Role.HOUSEHOLD
                person.ha_user_id = new_user or None
                texts.append(
                    f"linked {person.name} to an app account" if new_user else f"unlinked {person.name}'s app account"
                )
        if "owner" in changes and changes["owner"] is not None:
            want_owner = bool(changes["owner"])
            if want_owner and not person.ha_user_id:
                raise AccessError("An authorized person needs a Home Assistant account.")
            if not want_owner and person.role is Role.OWNER:
                self._guard_last_owner(person)
            new_role = Role.OWNER if want_owner else (Role.FAMILY if person.ha_user_id else Role.HOUSEHOLD)
            if new_role != person.role:
                texts.append(f"made {person.name} {'an owner' if want_owner else 'a non-owner'}")
                person.role = new_role
        elif person.role is not Role.OWNER:
            person.role = Role.FAMILY if person.ha_user_id else Role.HOUSEHOLD
        if "expires_at" in changes:
            expires_at = changes["expires_at"]
            if expires_at is not None and expires_at <= time.time():
                raise AccessError("The expiry date is in the past.")
            person.expires_at = expires_at
            self._schedule_person(person)
            texts.append(f"set {person.name}'s expiry")
        if "notify_on_arrival" in changes and changes["notify_on_arrival"] is not None:
            person.notify_on_arrival = bool(changes["notify_on_arrival"])
        await self.store.async_save()
        if texts:
            await self._admin(actor, "person_updated", f"{actor.name} " + "; ".join(texts), person.id)
        self._notify("people", self.people_dict())
        return person

    async def async_remove_person(self, user_id: str | None, person_id: str) -> None:
        actor = self.policy.require_owner(user_id)
        person = self._person(person_id)
        if person.role is Role.OWNER:
            self._guard_last_owner(person)
        if actor.id == person.id:
            raise AccessError("You cannot remove yourself. Ask the other owner.")
        await self._remove_person(person, actor_name=actor.name, actor_id=actor.id)

    async def _remove_person(self, person: Person, *, actor_name: str, actor_id: str) -> None:
        person.active = False
        person.ha_user_id = None
        if timer := self._person_timers.pop(person.id, None):
            timer()
        pending = [
            c
            for c in self.store.credentials_of(person.id)
            if c.status in (CredentialStatus.ACTIVE, CredentialStatus.UNKNOWN)
        ]
        for cred in pending:
            cred.status = CredentialStatus.REMOVING
        await self.store.async_save()
        await self._record(
            "admin",
            {"action": "person_removed", "text": f"{actor_name} removed {person.name}", "actor_id": actor_id},
            person_id=person.id,
            alert="normal" if person.role is Role.OWNER else None,
        )
        if pending:
            try:
                await self._send(
                    lambda: self.profile.encode_delete_credential(None, person.member_id, None)
                )
            except AccessError:
                _LOGGER.info("lock offline; removal of %s will be retried", person.name)
        self._notify("people", self.people_dict())

    def _person(self, person_id: str) -> Person:
        person = self.store.persons.get(person_id)
        if person is None or not person.active:
            raise AccessError("That person does not exist.")
        return person

    @staticmethod
    def _clean_name(name: str) -> str:
        name = " ".join((name or "").split())
        if not 1 <= len(name) <= 40:
            raise AccessError("Names must be 1-40 characters.")
        return name

    def _guard_last_owner(self, person: Person) -> None:
        if [p.id for p in self.store.owners()] == [person.id]:
            raise AccessError("There must always be at least one authorized person.")

    async def _check_linkable(self, ha_user_id: str, ignore_person: str | None = None) -> None:
        user = await self.hass.auth.async_get_user(ha_user_id)
        if user is None or user.system_generated or not user.is_active:
            raise AccessError("That Home Assistant account cannot be linked.")
        other = self.store.person_by_user(ha_user_id)
        if other is not None and other.id != ignore_person:
            raise AccessError(f"That account is already linked to {other.name}.")
        if ha_user_id in self.store.tablet_user_ids:
            raise AccessError("That account is a wall-tablet account.")

    def _schedule_person(self, person: Person) -> None:
        if timer := self._person_timers.pop(person.id, None):
            timer()
        if person.expires_at is None or not person.active:
            return

        @callback
        def _expire(_now: Any) -> None:
            self._person_timers.pop(person.id, None)
            self.hass.async_create_task(self._expire_person(person.id))

        self._person_timers[person.id] = async_track_point_in_utc_time(
            self.hass, _expire, dt_util.utc_from_timestamp(person.expires_at)
        )

    async def _expire_person(self, person_id: str) -> None:
        person = self.store.persons.get(person_id)
        if person is None or not person.active:
            return
        async with self._handle_lock:
            if person.role is Role.OWNER and len(self.store.owners()) == 1:
                return  # never lock the house out of management
            await self._remove_person(person, actor_name="Expiry", actor_id=SYSTEM)

    # Tablets -----------------------------------------------------------

    async def async_set_tablets(self, user_id: str | None, tablet_user_ids: list[str]) -> None:
        actor = self.policy.require_owner(user_id)
        clean: set[str] = set()
        for uid in tablet_user_ids:
            user = await self.hass.auth.async_get_user(uid)
            if user is None or user.system_generated:
                raise AccessError("Unknown Home Assistant account.")
            if self.store.person_by_user(uid):
                raise AccessError(f"{user.name} is linked to a person, not a tablet.")
            clean.add(uid)
        self.store.tablet_user_ids = clean
        await self.store.async_save()
        await self._admin(actor, "tablets_set", f"{actor.name} updated the wall tablets", None)

    # Enrolment ---------------------------------------------------------

    async def async_start_enrol(self, user_id: str | None, person_id: str, method: Method) -> EnrolSession:
        actor = self.policy.require_owner(user_id)
        person = self._person(person_id)
        if method not in self.profile.capabilities.enrol_methods:
            raise AccessError(f"This lock cannot enrol a {METHOD_WORD.get(method, method)}.")
        if self.session is not None and self.session.open:
            raise AccessError("An enrolment is already in progress at the lock.")
        session = EnrolSession(
            id=uuid.uuid4().hex,
            person_id=person.id,
            method=method,
            member_id=person.member_id,
            started_by=actor.id,
            started_at=time.time(),
        )
        await self._send(lambda: self.profile.encode_enrol(method, person.member_id))
        self.session = session
        self._arm_session_timeout()
        self._notify("enrol", self.session_dict())
        return session

    async def async_cancel_enrol(self, user_id: str | None) -> None:
        self.policy.require_owner(user_id)
        session = self.session
        if session is None or not session.open:
            return
        try:
            await self._send(lambda: self.profile.encode_enrol_cancel(session.method, session.member_id))
        finally:
            session.state = "cancelled"
            self._disarm_session_timeout()
            self._notify("enrol", self.session_dict())

    def _arm_session_timeout(self) -> None:
        self._disarm_session_timeout()

        @callback
        def _timeout(_now: Any) -> None:
            self._session_timer = None
            self.hass.async_create_task(self._session_timed_out())

        self._session_timer = async_track_point_in_utc_time(
            self.hass, _timeout, dt_util.utcnow() + timedelta(seconds=ENROL_TIMEOUT_S)
        )

    def _disarm_session_timeout(self) -> None:
        if self._session_timer:
            self._session_timer()
            self._session_timer = None

    async def _session_timed_out(self) -> None:
        session = self.session
        if session is None or not session.open:
            return
        session.state = "failed"
        session.reason = "timeout"
        try:
            await self._send(lambda: self.profile.encode_enrol_cancel(session.method, session.member_id))
        except AccessError:
            pass
        self._notify("enrol", self.session_dict())

    async def _enrol_report(self, report: EnrolReport) -> None:
        session = self.session
        ours = (
            session is not None
            and session.open
            and report.member_id == session.member_id
            and report.method is session.method
        )
        if not ours:
            if report.stage is EnrolStage.DONE:
                # enrolled by the Tuya app / cloud, not by this integration
                cred = self.store.find_credential(report.method, report.lock_ref)
                if cred is None or cred.status is CredentialStatus.RETIRED:
                    cred = Credential(
                        id=uuid.uuid4().hex,
                        method=report.method,
                        lock_ref=report.lock_ref,
                        person_id=None,
                        source=CredentialSource.LOCK_MENU,
                        status=CredentialStatus.UNKNOWN,
                        first_seen=time.time(),
                    )
                    self.store.credentials[cred.id] = cred
                    await self.store.async_save()
                await self._record(
                    "enrol_outside",
                    {"method": report.method, "lock_ref": report.lock_ref, "credential_id": cred.id},
                    alert="urgent",
                )
                self._notify("people", self.people_dict())
            return

        assert session is not None
        if report.stage is EnrolStage.STARTED:
            session.state = "enrolling"
            session.presses_needed = report.presses_needed
            session.lock_ref = report.lock_ref
        elif report.stage is EnrolStage.PROGRESS:
            session.state = "enrolling"
            session.presses_done = report.presses_done
        elif report.stage is EnrolStage.DONE:
            await self._enrol_done(session, report)
        elif report.stage is EnrolStage.FAILED:
            session.state = "failed"
            session.reason = report.reason
            self._disarm_session_timeout()
        elif report.stage is EnrolStage.CANCELLED:
            session.state = "cancelled"
            self._disarm_session_timeout()
        self._notify("enrol", self.session_dict())

    async def _enrol_done(self, session: EnrolSession, report: EnrolReport) -> None:
        self._disarm_session_timeout()
        now = time.time()
        cred = self.store.find_credential(report.method, report.lock_ref)
        if cred is None or cred.status is CredentialStatus.RETIRED:
            cred = Credential(
                id=uuid.uuid4().hex,
                method=report.method,
                lock_ref=report.lock_ref,
                person_id=session.person_id,
                source=CredentialSource.DASHBOARD,
                status=CredentialStatus.ACTIVE,
                first_seen=now,
            )
            self.store.credentials[cred.id] = cred
        else:
            cred.person_id = session.person_id
            cred.status = CredentialStatus.ACTIVE
            cred.source = CredentialSource.DASHBOARD
        session.state = "done"
        session.presses_done = report.presses_needed or session.presses_done
        session.lock_ref = report.lock_ref
        session.credential_id = cred.id
        await self.store.async_save()
        person = self.store.persons.get(session.person_id)
        actor = self.store.persons.get(session.started_by)
        word = METHOD_WORD.get(report.method, str(report.method))
        await self._record(
            "admin",
            {
                "action": "credential_enrolled",
                "text": f"{actor.name if actor else 'An owner'} added {word} #{report.lock_ref} for {person.name if person else 'someone'}",
                "actor_id": session.started_by,
                "credential_id": cred.id,
            },
            person_id=session.person_id,
        )
        self._notify("people", self.people_dict())

    # Credentials -------------------------------------------------------

    async def async_assign_credential(self, user_id: str | None, credential_id: str, person_id: str) -> None:
        actor = self.policy.require_owner(user_id)
        cred = self._credential(credential_id)
        person = self._person(person_id)
        if cred.status is CredentialStatus.RETIRED:
            raise AccessError("That credential has been deleted.")
        cred.person_id = person.id
        if cred.status is CredentialStatus.UNKNOWN:
            cred.status = CredentialStatus.ACTIVE
        await self.store.async_save()
        word = METHOD_WORD.get(cred.method, str(cred.method))
        await self._admin(actor, "credential_named", f"{actor.name} named {word} #{cred.lock_ref} as {person.name}", person.id)
        self._notify("people", self.people_dict())

    async def async_remove_credential(self, user_id: str | None, credential_id: str) -> None:
        actor = self.policy.require_owner(user_id)
        cred = self._credential(credential_id)
        if cred.status is CredentialStatus.RETIRED:
            return
        person = self.store.persons.get(cred.person_id or "")
        member_id = person.member_id if person else 0
        cred.status = CredentialStatus.REMOVING
        await self.store.async_save()
        word = METHOD_WORD.get(cred.method, str(cred.method))
        await self._admin(
            actor,
            "credential_removed",
            f"{actor.name} removed {word} #{cred.lock_ref}" + (f" from {person.name}" if person else ""),
            person.id if person else None,
        )
        self._notify("people", self.people_dict())
        await self._send(lambda: self.profile.encode_delete_credential(cred.method, member_id, cred.lock_ref))

    def _credential(self, credential_id: str) -> Credential:
        cred = self.store.credentials.get(credential_id)
        if cred is None:
            raise AccessError("That credential does not exist.")
        return cred

    async def _delete_report(self, report: DeleteReport) -> None:
        done = report.success or report.reason == "id_not_found"
        if report.lock_ref is None:
            targets = [
                c
                for p in self.store.persons.values()
                if p.member_id == report.member_id
                for c in self.store.credentials_of(p.id)
                if c.status is CredentialStatus.REMOVING
            ]
        else:
            cred = self.store.find_credential(report.method, report.lock_ref) if report.method else None
            targets = [cred] if cred and cred.status is CredentialStatus.REMOVING else []
        if not targets:
            return
        if done:
            for cred in targets:
                cred.status = CredentialStatus.RETIRED
            await self.store.async_save()
            await self._record("deleted", {"credential_ids": [c.id for c in targets]})
        else:
            await self._record("delete_failed", {"reason": report.reason}, alert="normal")
        self._notify("people", self.people_dict())

    async def _retry_pending_removals(self) -> None:
        for person in self.store.persons.values():
            removing = [c for c in self.store.credentials_of(person.id) if c.status is CredentialStatus.REMOVING]
            if not removing:
                continue
            try:
                if not person.active:
                    await self._send(
                        lambda p=person: self.profile.encode_delete_credential(None, p.member_id, None)
                    )
                else:
                    for cred in removing:
                        await self._send(
                            lambda c=cred, p=person: self.profile.encode_delete_credential(c.method, p.member_id, c.lock_ref)
                        )
            except AccessError:
                return
        for cred in self.store.credentials.values():
            if cred.status is CredentialStatus.REMOVING and cred.person_id is None:
                try:
                    await self._send(lambda c=cred: self.profile.encode_delete_credential(c.method, 0, c.lock_ref))
                except AccessError:
                    return

    # Guest codes -------------------------------------------------------

    async def async_create_guest_code(
        self,
        user_id: str | None,
        *,
        name: str,
        kind: GuestKind,
        start: float | None = None,
        end: float | None = None,
        weekdays: list[int] | None = None,
        daily_from: list[int] | None = None,
        daily_to: list[int] | None = None,
    ) -> GuestCode:
        actor = self.policy.require_owner(user_id)
        caps = self.profile.capabilities
        if not caps.guest_codes:
            raise AccessError("This lock does not support guest codes.")
        name = self._clean_name(name)
        now = time.time()
        start = now if start is None else start
        if end is None:
            if kind is not GuestKind.ONE_TIME:
                raise AccessError("Choose when the code ends.")
            end = start + ONE_TIME_DEFAULT_HOURS * 3600
        if end <= max(start, now):
            raise AccessError("The code must end in the future and after it starts.")
        weekdays = sorted(set(weekdays or []))
        if kind is GuestKind.WEEKLY and (not weekdays or daily_from is None or daily_to is None):
            raise AccessError("A weekly code needs days and hours.")
        used = {g.slot for g in self.store.active_guest_codes()}
        slot = next((s for s in caps.guest_slots if s not in used), None)
        if slot is None:
            raise AccessError(f"All {len(caps.guest_slots)} guest code slots are in use.")
        pin = self._new_pin(caps.guest_pin_length)
        spec = GuestCodeSpec(
            slot=slot,
            pin=pin,
            # Lock clocks can lag; never start later than now.
            start=int(min(start, now)) if kind is not GuestKind.WINDOW else int(start),
            end=int(end),
            one_time=kind is GuestKind.ONE_TIME,
            weekdays=frozenset(weekdays) if kind is GuestKind.WEEKLY else frozenset(),
            daily_from=tuple(daily_from) if kind is GuestKind.WEEKLY and daily_from else None,  # type: ignore[arg-type]
            daily_to=tuple(daily_to) if kind is GuestKind.WEEKLY and daily_to else None,  # type: ignore[arg-type]
        )
        await self._send(lambda: self.profile.encode_guest_code(spec))
        code = GuestCode(
            slot=slot,
            name=name,
            pin=pin,
            kind=kind,
            start=start,
            end=end,
            weekdays=weekdays if kind is GuestKind.WEEKLY else [],
            daily_from=list(daily_from) if kind is GuestKind.WEEKLY and daily_from else None,
            daily_to=list(daily_to) if kind is GuestKind.WEEKLY and daily_to else None,
            created_at=now,
            created_by=actor.id,
        )
        self.store.guest_codes[slot] = code
        await self.store.async_save()
        self._schedule_guest(code)
        await self._admin(actor, "guest_code_created", f"{actor.name} created a guest code for {name}", None)
        self._notify("guest_codes", self.guest_codes_dict())
        return code

    async def async_revoke_guest_code(self, user_id: str | None, slot: int) -> None:
        actor = self.policy.require_owner(user_id)
        code = self.store.guest_codes.get(slot)
        if code is None or code.state is not GuestState.ACTIVE:
            raise AccessError("That guest code is not active.")
        await self._send(lambda: self.profile.encode_guest_code_delete(slot))
        code.state = GuestState.REVOKED
        self._cancel_guest_timer(slot)
        await self.store.async_save()
        await self._admin(actor, "guest_code_revoked", f"{actor.name} revoked the guest code for {code.name}", None)
        self._notify("guest_codes", self.guest_codes_dict())

    def _new_pin(self, length: int) -> str:
        taken = {g.pin for g in self.store.active_guest_codes()}
        while True:
            pin = f"{secrets.randbelow(10**length):0{length}d}"
            if pin in taken or len(set(pin)) == 1:
                continue
            if pin in "01234567890123456789" or pin in "98765432109876543210":
                continue
            return pin

    def _schedule_guest(self, code: GuestCode) -> None:
        self._cancel_guest_timer(code.slot)

        @callback
        def _expire(_now: Any) -> None:
            self._guest_timers.pop(code.slot, None)
            self.hass.async_create_task(self._expire_guest(code.slot))

        self._guest_timers[code.slot] = async_track_point_in_utc_time(
            self.hass, _expire, dt_util.utc_from_timestamp(code.end)
        )

    def _cancel_guest_timer(self, slot: int) -> None:
        if timer := self._guest_timers.pop(slot, None):
            timer()

    async def _expire_guest(self, slot: int) -> None:
        code = self.store.guest_codes.get(slot)
        if code is None or code.state is not GuestState.ACTIVE:
            return
        code.state = GuestState.EXPIRED
        await self.store.async_save()
        # The lock enforces the end time itself; deleting is a backup in case
        # its clock is wrong.
        try:
            await self._send(lambda: self.profile.encode_guest_code_delete(slot))
        except AccessError:
            pass
        await self._record("guest_expired", {"slot": slot, "guest": code.name})
        self._notify("guest_codes", self.guest_codes_dict())

    # Event log ---------------------------------------------------------

    async def _admin(self, actor: Person, action: str, text: str, person_id: str | None) -> None:
        await self._record(
            "admin", {"action": action, "text": text, "actor_id": actor.id}, person_id=person_id
        )

    async def _record(
        self,
        kind: str,
        data: dict[str, Any],
        *,
        alert: str | None = None,
        person_id: str | None = None,
    ) -> dict[str, Any]:
        data = {k: (str(v) if isinstance(v, Method) else v) for k, v in data.items()}
        if person_id:
            data["person_id"] = person_id
        entry = await self.hass.async_add_executor_job(self.log.append, kind, data)
        rendered = self.render(entry)
        rendered["alert"] = alert
        self.hass.bus.async_fire(
            EVENT_ACCESS,
            {"entry_id": self.entry_id, "lock": self.name, **rendered},
        )
        self._notify("timeline", rendered)
        return entry

    async def _purge(self, _now: Any = None) -> None:
        cutoff = time.time() - RETENTION_DAYS * 86400
        await self.hass.async_add_executor_job(self.log.purge_older_than, cutoff)

    async def async_timeline(
        self, user_id: str | None, *, limit: int = 50, before_seq: int | None = None
    ) -> list[dict[str, Any]]:
        self.policy.require_owner(user_id)
        rows = await self.hass.async_add_executor_job(
            lambda: self.log.query(limit=limit, before_seq=before_seq)
        )
        return [self.render(r) for r in rows]

    def render(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Turn a log row into a timeline line, with today's names."""
        kind, data = entry["kind"], entry["data"]
        person = self.store.persons.get(data.get("person_id") or "")
        text = ""
        unknown = False
        if kind == "unlock":
            method = data.get("method")
            if method in (Method.APP, Method.TABLET):
                who = person.name if person else data.get("actor_name", "someone")
                text = f"Unlocked from the wall tablet ({who})" if method == Method.TABLET else f"Unlocked remotely by {who}"
            elif method == Method.GUEST_CODE:
                guest = data.get("guest")
                text = f"Guest '{guest}' used code" if guest else f"Unknown code (slot {data.get('slot')}) opened the door"
                unknown = guest is None
            else:
                cred = self.store.credentials.get(data.get("credential_id") or "")
                owner = self.store.persons.get(cred.person_id) if cred and cred.person_id else None
                word = METHOD_WORD.get(Method(method), method) if method in Method._value2member_map_ else method
                if owner:
                    text = f"{owner.name} opened with {word}"
                    person = owner
                else:
                    text = f"Unknown {word} #{data.get('lock_ref')} opened the door"
                    unknown = cred is not None and cred.status is CredentialStatus.UNKNOWN
        elif kind == "door":
            text = "Door opened" if data.get("open") else "Door closed"
        elif kind == "alarm":
            text = ALARM_TEXT.get(data.get("alarm", ""), f"Lock alarm: {data.get('alarm')}")
        elif kind in ("admin",):
            text = data.get("text", "")
        elif kind == "enrol_outside":
            word = METHOD_WORD.get(Method(data["method"]), data["method"])
            text = f"{word.capitalize()} #{data.get('lock_ref')} was added outside the dashboard"
            cred = self.store.credentials.get(data.get("credential_id") or "")
            unknown = cred is not None and cred.status is CredentialStatus.UNKNOWN
        elif kind == "guest_expired":
            text = f"Guest code for {data.get('guest')} expired"
        elif kind == "deleted":
            text = "The lock confirmed a deletion"
        elif kind == "delete_failed":
            text = f"The lock refused a deletion ({data.get('reason')})"
        elif kind == "unlock_failed":
            text = "Remote unlock failed"
        elif kind == "offline":
            text = "Lock offline"
        elif kind == "online":
            text = "Lock online"
        elif kind == "purge":
            text = f"Removed {data.get('removed')} entries older than {RETENTION_DAYS} days"
        return {
            "seq": entry["seq"],
            "ts": entry["ts"],
            "kind": kind,
            "method": data.get("method"),
            "text": text,
            "person_id": person.id if person else None,
            "person": person.name if person else None,
            "credential_id": data.get("credential_id"),
            "needs_name": unknown,
        }

    # Views -------------------------------------------------------------

    def state_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "name": self.name,
            "available": self.available,
            "door_open": self.door_open,
            "locked": self.locked,
            "battery": self.battery,
        }

    def capabilities_dict(self) -> dict[str, Any]:
        caps = self.profile.capabilities
        return {
            "profile": self.profile.profile_id,
            "model": self.profile.name,
            "enrol_methods": sorted(caps.enrol_methods),
            "remote_unlock": caps.remote_unlock and len(self._unlock_key) == 8,
            "guest_codes": caps.guest_codes,
            "guest_slots": len(caps.guest_slots),
        }

    def people_dict(self) -> dict[str, Any]:
        people = []
        for person in sorted(self.store.active_persons(), key=lambda p: (p.role != Role.OWNER, p.name.lower())):
            people.append(
                {
                    "id": person.id,
                    "name": person.name,
                    "role": person.role,
                    "has_app": person.ha_user_id is not None,
                    "ha_user_id": person.ha_user_id,
                    "expires_at": person.expires_at,
                    "notify_on_arrival": person.notify_on_arrival,
                    "credentials": [
                        self._cred_view(c)
                        for c in self.store.credentials_of(person.id)
                        if c.status is not CredentialStatus.RETIRED
                    ],
                }
            )
        return {
            "people": people,
            "unknown": [self._cred_view(c) for c in self.store.unknown_credentials()],
            "tablet_user_ids": sorted(self.store.tablet_user_ids),
        }

    @staticmethod
    def _cred_view(cred: Credential) -> dict[str, Any]:
        return {
            "id": cred.id,
            "method": cred.method,
            "lock_ref": cred.lock_ref,
            "status": cred.status,
            "source": cred.source,
            "last_seen": cred.last_seen,
        }

    def guest_codes_dict(self) -> dict[str, Any]:
        codes = sorted(self.store.active_guest_codes(), key=lambda g: g.end)
        return {"guest_codes": [g.as_dict() for g in codes]}

    def session_dict(self) -> dict[str, Any]:
        if self.session is None:
            return {"session": None}
        data = asdict(self.session)
        person = self.store.persons.get(self.session.person_id)
        data["person"] = person.name if person else None
        return {"session": data}
