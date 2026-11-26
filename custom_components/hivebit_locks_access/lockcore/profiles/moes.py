"""MOES WDL-X1, Zigbee variant (Tuya PID bfejtdig).

Uses the Tuya standard data points unchanged. Bench notes (Nov 2026):

* Fingerprint enrolment takes 4 presses; the lock reports the count itself.
* New credentials always take the next hardware ID; deleted IDs are not reused.
* Temporary-password times are read as unsigned (end dates up to 2099 work).
* Tuya app slots count down from 999; HA uses 901-949.
* The lock does not buffer unlock reports while the gateway is down.
"""

from __future__ import annotations

from .tuya_residential import TuyaResidentialLockProfile


class MoesWdlX1ZigbeeProfile(TuyaResidentialLockProfile):
    """MOES WDL-X1 full-panel mortise lock, Zigbee module."""

    profile_id = "moes_wdl_x1_zigbee"
    name = "MOES WDL-X1 (Zigbee)"
    product_ids = ("bfejtdig",)
