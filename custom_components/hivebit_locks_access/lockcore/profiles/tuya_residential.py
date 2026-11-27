"""Generic Tuya residential (Zigbee) lock profile.

Follows Tuya's standard data points for Zigbee residential locks. The byte
layouts were confirmed on the MOES WDL-X1 bench lock (Nov 2026) and match
Tuya's "Zigbee residential lock DP" reference:

    DP 1  fingerprint unlock, value = hardware ID          (report)
    DP 2  keypad PIN unlock, value = hardware ID           (report)
    DP 3  temporary password unlock, value = slot          (report)
    DP 5  card unlock, value = hardware ID                 (report)
    DP 8  door open/close event, bool (True = open)        (report)
    DP 9  alarm, enum                                      (report)
    DP 10 battery, percent                                 (report)
    DP 22 remote unlock result, bool                       (report)
    DP 24 create temporary password, raw 27 bytes          (write)
    DP 25 delete temporary password, raw 6 bytes           (write)
    DP 47 door state, enum open / closed / unknown         (report)
    DP 49 remote unlock with stored key, raw 13 bytes      (write)
    DP 54 add unlock method (enrolment), raw 7 / 9 bytes   (write / report)
    DP 55 delete unlock method, raw 8 / 9 bytes            (write / report)
    DP 57 lock motor state, bool                           (report)

A Tuya lock that moves a feature to another DP subclasses this profile and
changes the ``DP_*`` class attributes; one that encodes a payload differently
overrides only that method.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import struct

from ..events import (
    AlarmReport,
    BatteryReport,
    DeleteReport,
    DoorReport,
    EnrolReport,
    EnrolStage,
    LockReport,
    LockStateReport,
    Method,
    RawReport,
    RemoteUnlockResult,
    UnlockReport,
)
from .base import Capabilities, DpWrite, GuestCodeSpec, LockProfile, ProfileError

# Credential type byte used by DP 54 / DP 55.
_TYPE_BYTE: dict[Method, int] = {
    Method.PIN: 0x01,
    Method.CARD: 0x02,
    Method.FINGERPRINT: 0x03,
}
_BYTE_TYPE = {v: k for k, v in _TYPE_BYTE.items()}

# DP 54 stage byte.
_STAGE: dict[int, EnrolStage] = {
    0x00: EnrolStage.STARTED,
    0xFC: EnrolStage.PROGRESS,
    0xFD: EnrolStage.FAILED,
    0xFE: EnrolStage.CANCELLED,
    0xFF: EnrolStage.DONE,
}

# DP 54 failure reasons (status byte when stage = 0xFD).
ENROL_FAILURE: dict[int, str] = {
    0x00: "timeout",
    0x01: "failed",
    0x02: "duplicate",
    0x03: "no_free_id",
    0x04: "pin_not_numeric",
    0x05: "pin_length",
    0x06: "invalid_method",
    0x07: "fingerprint_enrolment_busy",
    0x08: "card_binding_busy",
    0xFE: "invalid_id",
}

# DP 55 result byte.
DELETE_RESULT: dict[int, str] = {
    0x00: "failed",
    0x01: "id_not_found",
    0x02: "cannot_delete",
    0xFF: "ok",
}

# DP 9 alarm enum, in Tuya's order.
ALARMS: tuple[str, ...] = (
    "wrong_finger",
    "wrong_password",
    "wrong_card",
    "wrong_face",
    "tongue_bad",
    "too_hot",
    "tongue_not_out",
    "test",
    "pry",
    "key_in",
    "power_off",
    "shock",
    "unclosed_time",
    "low_battery",
    "defense",
)

LOCK_ASSIGNS_ID = 0x03E7  # "let the lock choose the hardware ID"
MAX_MEMBER_ID = 0x03E7


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def raw_bytes(value: object) -> bytes | None:
    """Return the bytes of a raw data point (base64 str, hex str or bytes)."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        pass
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


class TuyaResidentialLockProfile(LockProfile):
    """Tuya standard residential lock, reached as a Zigbee sub-device."""

    profile_id = "tuya_residential_zigbee"
    name = "Tuya residential lock (Zigbee, standard DPs)"

    DP_UNLOCK_FINGERPRINT = 1
    DP_UNLOCK_PIN = 2
    DP_UNLOCK_GUEST_CODE = 3
    DP_UNLOCK_CARD = 5
    DP_DOOR_EVENT = 8
    DP_ALARM = 9
    DP_BATTERY = 10
    DP_REMOTE_UNLOCK_RESULT = 22
    DP_GUEST_CODE_CREATE = 24
    DP_GUEST_CODE_DELETE = 25
    DP_DOOR_STATE = 47
    DP_REMOTE_UNLOCK = 49
    DP_ENROL = 54
    DP_DELETE_CREDENTIAL = 55
    DP_LOCK_STATE = 57

    GUEST_SLOT_FIRST = 901
    GUEST_SLOT_LAST = 949
    PIN_LENGTH = 6
    #: DP 57 True means the bolt is thrown. Confirm per model on the bench.
    LOCK_STATE_TRUE_MEANS_LOCKED = True

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            enrol_methods=frozenset({Method.FINGERPRINT, Method.CARD, Method.PIN}),
            remote_unlock=True,
            guest_codes=True,
            guest_slot_first=self.GUEST_SLOT_FIRST,
            guest_slot_last=self.GUEST_SLOT_LAST,
            guest_pin_length=self.PIN_LENGTH,
        )

    # Intents -> writes -------------------------------------------------

    def encode_remote_unlock(self, key_id: int, key: str) -> DpWrite:
        if not 0 <= key_id <= 0xFFFF:
            raise ProfileError("remote unlock key ID out of range")
        if len(key) != 8 or not key.isascii():
            raise ProfileError("remote unlock key must be 8 ASCII characters")
        payload = (
            bytes([0x01]) + struct.pack(">H", key_id) + key.encode("ascii") + b"\x00\x01"
        )
        return DpWrite(self.DP_REMOTE_UNLOCK, _b64(payload))

    def encode_guest_code(self, spec: GuestCodeSpec) -> DpWrite:
        if not 0 <= spec.slot <= 0xFFFF:
            raise ProfileError(f"slot out of range: {spec.slot}")
        if len(spec.pin) != self.PIN_LENGTH or not spec.pin.isdigit():
            raise ProfileError(f"PIN must be {self.PIN_LENGTH} digits")
        if not 0 <= spec.start <= 0xFFFFFFFF or not 0 <= spec.end <= 0xFFFFFFFF:
            raise ProfileError("validity times out of range")
        if spec.end <= spec.start:
            raise ProfileError("a guest code must end after it starts")
        schedule = bytes(6)
        if spec.weekdays:
            if spec.daily_from is None or spec.daily_to is None:
                raise ProfileError("a weekly schedule needs daily from/to times")
            bitmap = 0
            for day in spec.weekdays:
                if not 0 <= day <= 6:
                    raise ProfileError(f"weekday out of range: {day}")
                bitmap |= 1 << day
            (fh, fm), (th, tm) = spec.daily_from, spec.daily_to
            for hh, mm in ((fh, fm), (th, tm)):
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ProfileError("daily time out of range")
            schedule = bytes([0x02, bitmap, fh, fm, th, tm])
        payload = (
            struct.pack(">HHHII", spec.slot, 1, 0, spec.start, spec.end)
            + schedule
            + bytes([1 if spec.one_time else 0])
            + spec.pin.encode("ascii")
        )
        return DpWrite(self.DP_GUEST_CODE_CREATE, _b64(payload))

    def encode_guest_code_delete(self, slot: int) -> DpWrite:
        if not 0 <= slot <= 0xFFFF:
            raise ProfileError(f"slot out of range: {slot}")
        return DpWrite(self.DP_GUEST_CODE_DELETE, _b64(struct.pack(">HHH", slot, 1, 0)))

    # Bench, 2026-11-17/20: DP 25 delete was never confirmed to work; writing
    # the slot again with a window that ended a day ago and a throwaway PIN
    # did. Send that first, then DP 25 as well.
    def encode_guest_code_revoke(self, slot: int, now: int) -> list[DpWrite]:
        expired_end = now - 86_400
        throwaway = f"{secrets.randbelow(10**self.PIN_LENGTH):0{self.PIN_LENGTH}d}"
        overwrite = self.encode_guest_code(
            GuestCodeSpec(slot=slot, pin=throwaway, start=expired_end - 60, end=expired_end)
        )
        return [overwrite, self.encode_guest_code_delete(slot)]

    # Same bench work: codes starting a day back are what proved reliable.
    guest_start_slack_s = 86_400

    def _member(self, member_id: int) -> int:
        if not 1 <= member_id <= MAX_MEMBER_ID:
            raise ProfileError(f"member ID must be 1-{MAX_MEMBER_ID}")
        return member_id

    def _type(self, method: Method) -> int:
        try:
            return _TYPE_BYTE[method]
        except KeyError as err:
            raise ProfileError(f"cannot enrol {method} on this lock") from err

    def encode_enrol(self, method: Method, member_id: int) -> DpWrite:
        payload = bytes([self._type(method), 0x00, 0x00]) + struct.pack(
            ">HH", self._member(member_id), LOCK_ASSIGNS_ID
        )
        return DpWrite(self.DP_ENROL, _b64(payload))

    def encode_enrol_cancel(self, method: Method, member_id: int) -> DpWrite:
        payload = bytes([self._type(method), 0xFE, 0x00]) + struct.pack(
            ">HH", self._member(member_id), LOCK_ASSIGNS_ID
        )
        return DpWrite(self.DP_ENROL, _b64(payload))

    def encode_delete_credential(
        self, method: Method | None, member_id: int, lock_ref: int | None
    ) -> DpWrite:
        if (method is None) != (lock_ref is None):
            raise ProfileError("give both method and lock_ref, or neither")
        type_byte = 0x00 if method is None else self._type(method)
        hw = LOCK_ASSIGNS_ID if lock_ref is None else lock_ref
        if not 0 <= hw <= 0xFFFF:
            raise ProfileError(f"credential ID out of range: {hw}")
        one = 0x00 if lock_ref is None else 0x01
        # A credential enrolled outside HA has no member ID we know; deleting it
        # by hardware ID with member 0 is not yet confirmed on the bench.
        member = member_id if lock_ref is not None and member_id == 0 else self._member(member_id)
        payload = (
            bytes([type_byte, 0x00, 0x00])
            + struct.pack(">HH", member, hw)
            + bytes([one])
        )
        return DpWrite(self.DP_DELETE_CREDENTIAL, _b64(payload))

    # Reports -> events -------------------------------------------------

    def decode(self, dp: int, value: object) -> list[LockReport]:
        unlock_methods = {
            self.DP_UNLOCK_FINGERPRINT: Method.FINGERPRINT,
            self.DP_UNLOCK_PIN: Method.PIN,
            self.DP_UNLOCK_GUEST_CODE: Method.GUEST_CODE,
            self.DP_UNLOCK_CARD: Method.CARD,
        }
        if dp in unlock_methods:
            ref = _as_int(value)
            if ref is None:
                return [RawReport(dp, value)]
            return [UnlockReport(unlock_methods[dp], ref)]
        if dp == self.DP_DOOR_EVENT:
            return [DoorReport(is_open=bool(value))]
        if dp == self.DP_DOOR_STATE:
            state = self._enum_name(value, ("open", "closed", "unknown"))
            if state in ("open", "closed"):
                return [DoorReport(is_open=state == "open")]
            return []
        if dp == self.DP_ALARM:
            kind = self._enum_name(value, ALARMS)
            return [AlarmReport(kind or f"unknown_{value}")]
        if dp == self.DP_BATTERY:
            pct = _as_int(value)
            return [] if pct is None else [BatteryReport(max(0, min(100, pct)))]
        if dp == self.DP_REMOTE_UNLOCK_RESULT:
            return [RemoteUnlockResult(success=bool(value))]
        if dp == self.DP_REMOTE_UNLOCK:
            # reply to DP 49: [status][key ID 2B], status 0x00 = opened
            data = raw_bytes(value)
            if not data:
                return [RawReport(dp, value)]
            if len(data) > 3:
                return []  # our own command echoed back, not the lock's reply
            return [RemoteUnlockResult(success=data[0] == 0x00)]
        if dp == self.DP_LOCK_STATE:
            if self.lock_state_from_door:
                return []
            locked = bool(value) == self.LOCK_STATE_TRUE_MEANS_LOCKED
            return [LockStateReport(is_locked=locked)]
        if dp == self.DP_ENROL:
            return self._decode_enrol(dp, value)
        if dp == self.DP_DELETE_CREDENTIAL:
            return self._decode_delete(dp, value)
        return [RawReport(dp, value)]

    @staticmethod
    def _enum_name(value: object, names: tuple[str, ...]) -> str | None:
        if isinstance(value, str) and value in names:
            return value
        idx = _as_int(value)
        if idx is not None and 0 <= idx < len(names):
            return names[idx]
        return None

    def _decode_enrol(self, dp: int, value: object) -> list[LockReport]:
        data = raw_bytes(value)
        if data is None or len(data) < 9:
            return [RawReport(dp, value)]
        type_byte, stage_byte = data[0], data[1]
        member_id, lock_ref = struct.unpack(">HH", data[3:7])
        count, status = data[7], data[8]
        method = _BYTE_TYPE.get(type_byte, Method.UNKNOWN)
        stage = _STAGE.get(stage_byte)
        if stage is None:
            return [RawReport(dp, value)]
        reason = ENROL_FAILURE.get(status, f"code_{status}") if stage is EnrolStage.FAILED else None
        if stage is EnrolStage.PROGRESS:
            needed, done = 0, count
        elif stage is EnrolStage.DONE:
            needed, done = count, count
        else:
            needed, done = count, 0
        return [
            EnrolReport(
                method=method,
                stage=stage,
                member_id=member_id,
                lock_ref=lock_ref,
                presses_needed=needed,
                presses_done=done,
                reason=reason,
            )
        ]

    def _decode_delete(self, dp: int, value: object) -> list[LockReport]:
        data = raw_bytes(value)
        if data is None or len(data) < 9:
            return [RawReport(dp, value)]
        type_byte = data[0]
        member_id, lock_ref = struct.unpack(">HH", data[3:7])
        one, status = data[7], data[8]
        method = None if type_byte == 0x00 else _BYTE_TYPE.get(type_byte, Method.UNKNOWN)
        result = DELETE_RESULT.get(status, f"code_{status}")
        return [
            DeleteReport(
                method=method,
                member_id=member_id,
                lock_ref=lock_ref if one == 0x01 else None,
                success=status == 0xFF,
                reason=None if status == 0xFF else result,
            )
        ]
