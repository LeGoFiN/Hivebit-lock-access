"""Build the transport a config entry asks for.

Only the Tuya gateway transport exists today. A Z2M or Wi-Fi transport is
added here, selected by a new config key, without touching the profiles.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST

from .const import (
    CONF_DEVICE_ID,
    CONF_GATEWAY_ID,
    CONF_LOCAL_KEY,
    CONF_NODE_ID,
    CONF_PROTOCOL_VERSION,
)
from .lockcore.transport import Transport
from .lockcore.transport.tuya_gateway import TuyaGatewayTransport


def build_transport(data: dict[str, Any]) -> Transport:
    """Return a transport for this entry's data."""
    return TuyaGatewayTransport(
        host=data[CONF_HOST],
        gateway_id=data[CONF_GATEWAY_ID],
        local_key=data[CONF_LOCAL_KEY],
        protocol_version=data[CONF_PROTOCOL_VERSION],
        device_id=data[CONF_DEVICE_ID],
        node_id=data[CONF_NODE_ID],
    )
