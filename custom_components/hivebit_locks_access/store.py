"""Persistent registry of people, credentials, guest codes and tablets."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MEMBER_ID_FIRST, STORAGE_VERSION
from .lockcore.events import Method
from .models import Credential, CredentialStatus, GuestCode, GuestState, Person, Role


class AccessStore:
    """Registry for one lock. Saved to ``.storage``, readable by HA admins only."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.persons: dict[str, Person] = {}
        self.credentials: dict[str, Credential] = {}
        self.guest_codes: dict[int, GuestCode] = {}
        self.tablet_user_ids: set[str] = set()
        self.next_member_id: int = MEMBER_ID_FIRST

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.persons = {
            p["id"]: Person.from_dict(p) for p in data.get("persons", [])
        }
        self.credentials = {
            c["id"]: Credential.from_dict(c) for c in data.get("credentials", [])
        }
        self.guest_codes = {
            g["slot"]: GuestCode.from_dict(g) for g in data.get("guest_codes", [])
        }
        self.tablet_user_ids = set(data.get("tablet_user_ids", []))
        self.next_member_id = data.get("next_member_id", MEMBER_ID_FIRST)

    async def async_save(self) -> None:
        await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {
            "persons": [p.as_dict() for p in self.persons.values()],
            "credentials": [c.as_dict() for c in self.credentials.values()],
            "guest_codes": [g.as_dict() for g in self.guest_codes.values()],
            "tablet_user_ids": sorted(self.tablet_user_ids),
            "next_member_id": self.next_member_id,
        }

    # Lookups ----------------------------------------------------------

    def active_persons(self) -> list[Person]:
        return [p for p in self.persons.values() if p.active]

    def person_by_user(self, user_id: str | None) -> Person | None:
        if user_id is None:
            return None
        for person in self.persons.values():
            if person.active and person.ha_user_id == user_id:
                return person
        return None

    def owners(self) -> list[Person]:
        return [
            p
            for p in self.persons.values()
            if p.active and p.role is Role.OWNER and p.ha_user_id
        ]

    def find_credential(self, method: Method, lock_ref: int) -> Credential | None:
        """Return the newest record for this lock ID, whatever its status."""
        matches = [
            c
            for c in self.credentials.values()
            if c.method is method and c.lock_ref == lock_ref
        ]
        if not matches:
            return None
        return max(matches, key=lambda c: c.first_seen)

    def credentials_of(self, person_id: str) -> list[Credential]:
        return [c for c in self.credentials.values() if c.person_id == person_id]

    def active_guest_codes(self) -> list[GuestCode]:
        return [g for g in self.guest_codes.values() if g.state is GuestState.ACTIVE]

    def allocate_member_id(self) -> int:
        member_id = self.next_member_id
        self.next_member_id += 1
        return member_id

    def unknown_credentials(self) -> list[Credential]:
        return [
            c for c in self.credentials.values() if c.status is CredentialStatus.UNKNOWN
        ]
