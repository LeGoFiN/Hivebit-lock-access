"""Shared fixtures: a loaded lock on a fake transport, plus users with tokens."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser

from custom_components.hivebit_locks_access.const import DOMAIN
from custom_components.hivebit_locks_access.lockcore.transport.fake import FakeTransport

CLIENT_ID = "https://hivebit.test/app"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@dataclass
class UserFixture:
    user: MockUser
    token: str

    @property
    def id(self) -> str:
        return self.user.id


async def make_user(hass: HomeAssistant, name: str, *, admin: bool = False) -> UserFixture:
    group = await hass.auth.async_get_group(GROUP_ID_ADMIN if admin else GROUP_ID_USER)
    user = MockUser(name=name, groups=[group]).add_to_hass(hass)
    refresh = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
    return UserFixture(user, hass.auth.async_create_access_token(refresh))


@pytest.fixture
async def users(hass: HomeAssistant, local_auth) -> dict[str, UserFixture]:
    return {
        "father": await make_user(hass, "Father"),
        "son": await make_user(hass, "Son"),
        "worker": await make_user(hass, "Worker"),
        "tablet": await make_user(hass, "Hallway tablet"),
        "hivebit": await make_user(hass, "HIVEBIT", admin=True),
    }


@pytest.fixture
def fake() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
async def entry(
    hass: HomeAssistant, users: dict[str, UserFixture], fake: FakeTransport
) -> AsyncGenerator[MockConfigEntry]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front door",
        unique_id="gw_node",
        data={
            "name": "Front door",
            "profile": "moes_wdl_x1_zigbee",
            "host": "192.0.2.10",
            "gateway_id": "gw",
            "local_key": "k",
            "protocol_version": "3.5",
            "device_id": "lock",
            "node_id": "node",
            "unlock_key_id": 1,
            "unlock_key": "97155270",
            "owner_user_id": users["father"].id,
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.hivebit_locks_access.transport_factory.build_transport",
        return_value=fake,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
