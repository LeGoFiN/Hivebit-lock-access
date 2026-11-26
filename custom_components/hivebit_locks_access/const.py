"""Constants for HIVEBIT Locks Access."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hivebit_locks_access"
#: Keep in step with manifest.json and the card's CARD_VERSION.
VERSION: Final = "0.2.0"

CONF_PROFILE: Final = "profile"
CONF_GATEWAY_ID: Final = "gateway_id"
CONF_LOCAL_KEY: Final = "local_key"
CONF_PROTOCOL_VERSION: Final = "protocol_version"
CONF_DEVICE_ID: Final = "device_id"
CONF_NODE_ID: Final = "node_id"
CONF_UNLOCK_KEY_ID: Final = "unlock_key_id"
CONF_UNLOCK_KEY: Final = "unlock_key"
CONF_OWNER_USER_ID: Final = "owner_user_id"

PROTOCOL_VERSIONS: Final = ("3.3", "3.4", "3.5")

STORAGE_VERSION: Final = 1

#: Our lock member IDs start here so they never collide with members the
#: Tuya app created during commissioning (those start at 1).
MEMBER_ID_FIRST: Final = 100

ENROL_TIMEOUT_S: Final = 120
RETENTION_DAYS: Final = 90
ONE_TIME_DEFAULT_HOURS: Final = 24

#: Fired on the HA bus for every timeline entry. Non-admin users cannot
#: subscribe to custom events, so names in it do not leak to family accounts.
EVENT_ACCESS: Final = f"{DOMAIN}_event"
#: Fired when an unknown credential is used while the house is away.
EVENT_SECURITY: Final = f"{DOMAIN}_security_event"
