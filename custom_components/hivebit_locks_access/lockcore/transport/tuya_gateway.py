"""Transport for a Tuya Zigbee sub-device behind a Tuya gateway, over the LAN.

Uses tinytuya (protocol 3.3 / 3.4 / 3.5). One worker thread owns the socket:
it sends queued writes, reads every report the gateway pushes for the lock
(including the same value twice in a row), sends heartbeats, and reconnects
with back-off when the gateway goes away. Reports and availability changes
are handed back to the asyncio loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
import time
from typing import Any

from ..profiles.base import DpWrite
from .base import Transport, TransportError

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10.0  # seconds
SOCKET_TIMEOUT = 1.0  # seconds; bounds how long a write can wait in the queue
SEND_TIMEOUT = 8.0  # seconds
BACKOFF_MAX = 60.0  # seconds


class TuyaGatewayTransport(Transport):
    """Reach one lock as a sub-device of a Tuya Zigbee gateway."""

    def __init__(
        self,
        *,
        host: str,
        gateway_id: str,
        local_key: str,
        protocol_version: str,
        device_id: str,
        node_id: str,
    ) -> None:
        super().__init__()
        self._host = host
        self._gateway_id = gateway_id
        self._local_key = local_key
        self._version = float(protocol_version)
        self._device_id = device_id
        self._node_id = node_id
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._outbox: queue.Queue[tuple[DpWrite, concurrent.futures.Future[None]]] = (
            queue.Queue()
        )

    # asyncio side -----------------------------------------------------

    async def async_start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"tuya-gw-{self._host}", daemon=True
        )
        self._thread.start()

    async def async_stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            await asyncio.get_running_loop().run_in_executor(
                None, self._thread.join, 5
            )
            self._thread = None
        self._set_available(False)

    async def async_send(self, write: DpWrite) -> None:
        if not self._available:
            raise TransportError("lock gateway is not reachable")
        fut: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._outbox.put((write, fut))
        try:
            await asyncio.wait_for(asyncio.wrap_future(fut), SEND_TIMEOUT)
        except TimeoutError as err:
            raise TransportError("timed out sending to the lock gateway") from err
        except Exception as err:  # noqa: BLE001 - surfaced as TransportError
            raise TransportError(f"send failed: {err}") from err

    def _call_soon(self, func: Any, *args: Any) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(func, *args)

    # worker thread ----------------------------------------------------

    def _run(self) -> None:
        import tinytuya  # imported here so the profile code never needs it

        backoff = 2.0
        while not self._stop.is_set():
            gateway = None
            try:
                gateway = tinytuya.Device(
                    self._gateway_id,
                    self._host,
                    self._local_key,
                    persist=True,
                    version=self._version,
                )
                gateway.set_socketTimeout(SOCKET_TIMEOUT)
                lock = tinytuya.Device(
                    self._device_id, cid=self._node_id, parent=gateway
                )
                status = lock.status()
                _LOGGER.debug("<- status %s", status)
                self._check(status)
                self._call_soon(self._set_available, True)
                backoff = 2.0
                self._dispatch(status, snapshot=True)
                self._serve(gateway, lock)
            except Exception as err:  # noqa: BLE001 - any failure means reconnect
                _LOGGER.debug("Tuya gateway %s: %s", self._host, err)
            finally:
                self._call_soon(self._set_available, False)
                self._fail_pending("connection lost")
                if gateway is not None:
                    try:
                        gateway.close()
                    except Exception:  # noqa: BLE001
                        pass
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, BACKOFF_MAX)

    def _serve(self, gateway: Any, lock: Any) -> None:
        last_heartbeat = time.monotonic()
        while not self._stop.is_set():
            # 1. send what is queued
            while True:
                try:
                    write, fut = self._outbox.get_nowait()
                except queue.Empty:
                    break
                _LOGGER.debug("-> lock DP %s = %s", write.dp, write.value)
                try:
                    lock.set_value(write.dp, write.value, nowait=True)
                    fut.set_result(None)
                except Exception as err:  # noqa: BLE001
                    fut.set_exception(err)
                    raise
            # 2. read whatever the gateway pushes
            msg = gateway.receive()
            if msg is not None:
                _LOGGER.debug("<- gateway %s", msg)
                self._check(msg)
                self._dispatch(msg, snapshot=False)
            # 3. keep the session alive
            if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL:
                gateway.heartbeat(nowait=True)
                last_heartbeat = time.monotonic()

    @staticmethod
    def _check(msg: Any) -> None:
        if isinstance(msg, dict) and ("Err" in msg or "Error" in msg):
            raise TransportError(str(msg.get("Error") or msg.get("Err")))

    def _dispatch(self, msg: Any, *, snapshot: bool) -> None:
        if not isinstance(msg, dict):
            return
        data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
        cid = msg.get("cid") or data.get("cid")
        if cid is not None and str(cid) != str(self._node_id):
            return  # another sub-device on the same gateway
        dps = msg.get("dps") or data.get("dps")
        if not isinstance(dps, dict):
            return
        for key, value in dps.items():
            try:
                dp = int(key)
            except (TypeError, ValueError):
                continue
            self._call_soon(self._emit_dp, dp, value, snapshot)

    def _fail_pending(self, reason: str) -> None:
        while True:
            try:
                _, fut = self._outbox.get_nowait()
            except queue.Empty:
                return
            if not fut.done():
                fut.set_exception(TransportError(reason))
