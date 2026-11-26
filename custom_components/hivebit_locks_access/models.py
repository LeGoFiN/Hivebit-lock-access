"""Records kept by the integration: people, their credentials, guest codes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .lockcore.events import Method


class Role(StrEnum):
    """What a person may do."""

    OWNER = "owner"  # authorized person: manages access (needs an HA account)
    FAMILY = "family"  # HA account: may unlock from the app and the tablet
    HOUSEHOLD = "household"  # no HA account: fingerprint / card / PIN only


class CredentialStatus(StrEnum):
    """Lifecycle of a credential on the lock."""

    ACTIVE = "active"
    UNKNOWN = "unknown"  # seen on the lock, not enrolled through HA, not named yet
    REMOVING = "removing"  # delete sent, waiting for the lock to confirm
    RETIRED = "retired"  # deleted; its ID is never reused for a name


class CredentialSource(StrEnum):
    """Who put the credential on the lock."""

    DASHBOARD = "dashboard"
    LOCK_MENU = "lock_menu"  # admin menu on the lock, or the Tuya app


class GuestKind(StrEnum):
    """Guest code types."""

    ONE_TIME = "one_time"
    WINDOW = "window"
    WEEKLY = "weekly"


class GuestState(StrEnum):
    """Guest code lifecycle."""

    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(slots=True)
class Person:
    """Someone who can get in."""

    id: str
    name: str
    member_id: int
    role: Role
    ha_user_id: str | None = None
    expires_at: float | None = None
    notify_on_arrival: bool = False
    active: bool = True
    created_at: float = 0.0
    created_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Person:
        data = dict(data)
        data["role"] = Role(data["role"])
        return cls(**data)


@dataclass(slots=True)
class Credential:
    """A fingerprint, card or permanent PIN stored on the lock."""

    id: str
    method: Method
    lock_ref: int
    person_id: str | None
    source: CredentialSource
    status: CredentialStatus
    first_seen: float
    last_seen: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Credential:
        data = dict(data)
        data["method"] = Method(data["method"])
        data["source"] = CredentialSource(data["source"])
        data["status"] = CredentialStatus(data["status"])
        return cls(**data)


@dataclass(slots=True)
class GuestCode:
    """A temporary code for guests and services, written into a lock slot."""

    slot: int
    name: str
    pin: str
    kind: GuestKind
    start: float
    end: float
    weekdays: list[int] = field(default_factory=list)
    daily_from: list[int] | None = None  # [hour, minute]
    daily_to: list[int] | None = None
    state: GuestState = GuestState.ACTIVE
    created_at: float = 0.0
    created_by: str | None = None
    used_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuestCode:
        data = dict(data)
        data["kind"] = GuestKind(data["kind"])
        data["state"] = GuestState(data["state"])
        return cls(**data)
