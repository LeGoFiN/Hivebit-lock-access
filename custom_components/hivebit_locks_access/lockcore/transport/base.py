"""Transport: moves data-point writes to the lock and reports back.

A transport knows nothing about what the data points mean (that is the
profile's job). Today: a Tuya Zigbee gateway over the LAN. Later: Z2M over
MQTT, or a Wi-Fi lock directly. Callbacks always run on the asyncio loop
that called ``async_start``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..profiles.base import DpWrite

#: (dp, value, snapshot). snapshot=True for values read in a status poll, which
#: describe current state and must not be treated as new events.
DpCallback = Callable[[int, object, bool], None]
AvailabilityCallback = Callable[[bool], None]


class TransportError(Exception):
    """A write could not be delivered."""


class Transport(ABC):
    """Base class for transports."""

    def __init__(self) -> None:
        self._on_dp: DpCallback | None = None
        self._on_available: AvailabilityCallback | None = None
        self._available = False

    def set_callbacks(
        self, on_dp: DpCallback, on_available: AvailabilityCallback
    ) -> None:
        """Register where reports and availability changes go."""
        self._on_dp = on_dp
        self._on_available = on_available

    @property
    def available(self) -> bool:
        """Return True while the lock can be reached."""
        return self._available

    def _emit_dp(self, dp: int, value: object, snapshot: bool = False) -> None:
        if self._on_dp is not None:
            self._on_dp(dp, value, snapshot)

    def _set_available(self, available: bool) -> None:
        if available == self._available:
            return
        self._available = available
        if self._on_available is not None:
            self._on_available(available)

    @abstractmethod
    async def async_start(self) -> None:
        """Connect and start delivering reports."""

    @abstractmethod
    async def async_stop(self) -> None:
        """Disconnect."""

    @abstractmethod
    async def async_send(self, write: DpWrite) -> None:
        """Send one write. Raise TransportError if it could not be sent."""
