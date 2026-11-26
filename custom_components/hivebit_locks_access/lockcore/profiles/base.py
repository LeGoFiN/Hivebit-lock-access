"""Lock profile: what a lock model can do and how its data points are encoded.

A profile is pure Python. It turns intents ("enrol a fingerprint for member
7") into data-point writes, and the lock's data-point reports into typed
events. It knows nothing about how the bytes travel: that is the transport's
job (Tuya gateway today, Z2M or a Wi-Fi lock later).

To support a new lock model, add a profile module under ``profiles/`` and
register it in ``profiles/__init__.py``. Most Tuya residential locks follow
the same data-point standard, so a new Tuya lock usually subclasses
``TuyaResidentialLockProfile`` and overrides only what differs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..events import LockReport, Method


@dataclass(frozen=True, slots=True)
class DpWrite:
    """One data-point write. ``value`` is in the transport's native form.

    Raw (byte) data points are carried as base64 strings, the way Tuya
    gateways and LocalTuya expect them; numbers and booleans as-is.
    """

    dp: int
    value: str | int | bool


@dataclass(frozen=True, slots=True)
class GuestCodeSpec:
    """A temporary password the lock enforces itself."""

    slot: int
    pin: str
    start: int  # Unix seconds
    end: int  # Unix seconds
    one_time: bool = False
    weekdays: frozenset[int] = frozenset()  # 0 = Monday ... 6 = Sunday
    daily_from: tuple[int, int] | None = None  # (hour, minute)
    daily_to: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What the dashboard may offer for this lock model."""

    enrol_methods: frozenset[Method]
    remote_unlock: bool
    guest_codes: bool
    guest_slot_first: int = 0
    guest_slot_last: int = -1
    guest_pin_length: int = 6
    remote_delete: bool = True
    door_sensor: bool = True
    battery: bool = True
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def guest_slots(self) -> range:
        """Slots HA may use for guest codes."""
        return range(self.guest_slot_first, self.guest_slot_last + 1)


class ProfileError(ValueError):
    """An intent the profile cannot encode (bad PIN, slot out of range, ...)."""


class LockProfile(ABC):
    """Base class for all lock profiles."""

    #: Stable identifier stored in config entries. Never change it once shipped.
    profile_id: str = ""
    #: Human-readable model name shown in the setup screen.
    name: str = ""
    #: Vendor product IDs (e.g. Tuya PIDs) this profile is known to fit.
    product_ids: tuple[str, ...] = ()
    #: True when the lock reports no usable bolt state, so "locked" follows the
    #: door: closed = locked (mortise locks that latch on close).
    lock_state_from_door: bool = False
    #: Seconds after an unlock with the door still closed before the lock
    #: relocks itself. Used only with ``lock_state_from_door``.
    auto_relock_s: int = 10

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Return what this lock model supports."""

    # Intents -> writes -------------------------------------------------

    @abstractmethod
    def encode_remote_unlock(self, key_id: int, key: str) -> DpWrite:
        """Return the write that unlocks the door remotely."""

    @abstractmethod
    def encode_guest_code(self, spec: GuestCodeSpec) -> DpWrite:
        """Return the write that creates (or overwrites) a guest code slot."""

    @abstractmethod
    def encode_guest_code_delete(self, slot: int) -> DpWrite:
        """Return the write that deletes a guest code slot."""

    @abstractmethod
    def encode_enrol(self, method: Method, member_id: int) -> DpWrite:
        """Return the write that puts the lock into enrolment mode."""

    @abstractmethod
    def encode_enrol_cancel(self, method: Method, member_id: int) -> DpWrite:
        """Return the write that cancels an open enrolment session."""

    @abstractmethod
    def encode_delete_credential(
        self, method: Method | None, member_id: int, lock_ref: int | None
    ) -> DpWrite:
        """Delete one credential, or every credential of a member.

        ``method`` and ``lock_ref`` both None = all of the member's credentials.
        """

    # Reports -> events -------------------------------------------------

    @abstractmethod
    def decode(self, dp: int, value: object) -> list[LockReport]:
        """Turn one data-point report into zero or more typed events."""
