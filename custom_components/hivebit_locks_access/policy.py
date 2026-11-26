"""Who may do what. Every check runs server-side on the caller's HA user ID.

Rules (spec section 3):
* Only owners (authorized persons) manage people, credentials and guest codes,
  and read the timeline.
* Owners, family members with an HA account, and wall-tablet accounts may unlock.
* Calls with no user (automations, scripts, Node-RED) are refused.
* HA admin rights grant nothing here: HIVEBIT support is an HA admin but not a
  person in this registry, so it cannot use these commands. (An admin can
  still bypass the integration entirely; that is the accepted residual risk.)
"""

from __future__ import annotations

import time
from enum import StrEnum

from homeassistant.exceptions import Unauthorized

from .models import Person, Role
from .store import AccessStore


class Caller(StrEnum):
    """How a user relates to this lock."""

    OWNER = "owner"
    FAMILY = "family"
    TABLET = "tablet"
    NONE = "none"


class AccessPolicy:
    """Role checks against the registry."""

    def __init__(self, store: AccessStore) -> None:
        self._store = store

    def person_for(self, user_id: str | None) -> Person | None:
        person = self._store.person_by_user(user_id)
        if person is None:
            return None
        if person.expires_at is not None and person.expires_at <= time.time():
            return None
        return person

    def caller(self, user_id: str | None) -> Caller:
        if not user_id:
            return Caller.NONE
        person = self.person_for(user_id)
        if person is not None:
            if person.role is Role.OWNER:
                return Caller.OWNER
            if person.role is Role.FAMILY:
                return Caller.FAMILY
        if user_id in self._store.tablet_user_ids:
            return Caller.TABLET
        return Caller.NONE

    def require_owner(self, user_id: str | None) -> Person:
        if self.caller(user_id) is not Caller.OWNER:
            raise Unauthorized()
        person = self.person_for(user_id)
        assert person is not None
        return person

    def require_unlock(self, user_id: str | None) -> Caller:
        caller = self.caller(user_id)
        if caller is Caller.NONE:
            raise Unauthorized()
        return caller

    def require_member(self, user_id: str | None) -> Caller:
        """Anyone who may see door status (same set as unlock)."""
        return self.require_unlock(user_id)
