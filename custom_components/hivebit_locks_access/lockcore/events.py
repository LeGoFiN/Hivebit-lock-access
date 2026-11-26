"""Events a lock profile decodes from the lock's data points.

Pure Python: no Home Assistant imports, so the gateway probe script and the
tests can use it directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Method(StrEnum):
    """How the door was opened, or what kind of credential is meant."""

    FINGERPRINT = "fingerprint"
    CARD = "card"
    PIN = "pin"  # permanent keypad PIN, enrolled at the keypad
    GUEST_CODE = "guest_code"  # temporary password slot written by HA
    APP = "app"  # remote unlock from a phone
    TABLET = "tablet"  # remote unlock from a wall tablet
    KEY = "key"  # mechanical key
    UNKNOWN = "unknown"


class EnrolStage(StrEnum):
    """Stage of an enrolment session, as the lock reports it."""

    STARTED = "started"
    PROGRESS = "progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class UnlockReport:
    """The lock opened with a local credential and reported its ID."""

    method: Method
    lock_ref: int


@dataclass(frozen=True, slots=True)
class RemoteUnlockResult:
    """The lock answered a remote unlock command."""

    success: bool


@dataclass(frozen=True, slots=True)
class DoorReport:
    """Door contact changed."""

    is_open: bool


@dataclass(frozen=True, slots=True)
class LockStateReport:
    """Bolt state changed (True = locked)."""

    is_locked: bool


@dataclass(frozen=True, slots=True)
class AlarmReport:
    """The lock raised an alarm (wrong finger, pry, key inserted, ...)."""

    kind: str


@dataclass(frozen=True, slots=True)
class BatteryReport:
    """Battery level in percent."""

    percent: int


@dataclass(frozen=True, slots=True)
class EnrolReport:
    """Progress of an enrolment session started by HA (or by someone else)."""

    method: Method
    stage: EnrolStage
    member_id: int
    lock_ref: int
    presses_needed: int
    presses_done: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteReport:
    """Result of deleting a credential or all of a member's credentials."""

    method: Method | None  # None = every method of the member
    member_id: int
    lock_ref: int | None  # None = all of the member's credentials
    success: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RawReport:
    """A data point the profile does not interpret; kept for diagnostics."""

    dp: int
    value: object


LockReport = (
    UnlockReport
    | RemoteUnlockResult
    | DoorReport
    | LockStateReport
    | AlarmReport
    | BatteryReport
    | EnrolReport
    | DeleteReport
    | RawReport
)
