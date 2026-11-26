"""In-memory transport for tests and demos."""

from __future__ import annotations

from ..profiles.base import DpWrite
from .base import Transport, TransportError


class FakeTransport(Transport):
    """Records writes; tests inject reports with ``report``."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[DpWrite] = []
        self.fail_sends = False
        self.started = False

    async def async_start(self) -> None:
        self.started = True
        self._set_available(True)

    async def async_stop(self) -> None:
        self.started = False
        self._set_available(False)

    async def async_send(self, write: DpWrite) -> None:
        if self.fail_sends or not self._available:
            raise TransportError("fake transport: send failed")
        self.sent.append(write)

    def report(self, dp: int, value: object, snapshot: bool = False) -> None:
        """Simulate the lock reporting a data point."""
        self._emit_dp(dp, value, snapshot)

    def set_available(self, available: bool) -> None:
        """Simulate the gateway going away or coming back."""
        self._set_available(available)
