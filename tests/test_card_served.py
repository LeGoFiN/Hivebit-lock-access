"""The integration serves its card file."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


async def test_card_is_served(hass: HomeAssistant, entry, hass_client) -> None:
    assert await async_setup_component(hass, "http", {})
    await hass.async_block_till_done()
    client = await hass_client()
    resp = await client.get("/hivebit_locks_access/hivebit-access-card.js")
    assert resp.status == 200
    assert "hivebit-access-card" in await resp.text()
