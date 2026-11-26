"""Registry of supported lock models.

To add a lock model: write a profile module in this package and add its class
to ``_PROFILES``. The profile ID is stored in config entries, so never rename
one that has shipped.
"""

from __future__ import annotations

from .base import Capabilities, DpWrite, GuestCodeSpec, LockProfile, ProfileError
from .moes import MoesWdlX1ZigbeeProfile
from .tuya_residential import TuyaResidentialLockProfile

_PROFILES: tuple[type[LockProfile], ...] = (
    MoesWdlX1ZigbeeProfile,
    TuyaResidentialLockProfile,
)

PROFILES: dict[str, type[LockProfile]] = {p.profile_id: p for p in _PROFILES}


def get_profile(profile_id: str) -> LockProfile:
    """Return a profile instance by ID."""
    try:
        return PROFILES[profile_id]()
    except KeyError as err:
        raise KeyError(f"unknown lock profile: {profile_id}") from err


__all__ = [
    "PROFILES",
    "Capabilities",
    "DpWrite",
    "GuestCodeSpec",
    "LockProfile",
    "ProfileError",
    "get_profile",
]
