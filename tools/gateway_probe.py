#!/usr/bin/env python3
"""Talk to the lock through the Tuya gateway directly, without LocalTuya (bench test B6).

Runs the same transport and profile code the integration uses, from any
laptop on the villa LAN. It prints every report the lock sends, decoded.

Install once:   pip install tinytuya==1.21.1
Find the values in LocalTuya's config entry for the gateway and the lock
(gateway: host, device ID, local key, protocol; lock: device ID, node ID).

Examples:
  # watch reports for 2 minutes (open the door, use a fingerprint, ...)
  python tools/gateway_probe.py --host 192.168.1.50 --gateway-id GWID \\
      --local-key 'KEY' --version 3.5 --device-id LOCKID --node-id NODEID

  # unlock once (key ID and 8-character key from the DP 49 capture)
  python tools/gateway_probe.py ... --unlock --key-id 1 --key 12345678

  # start a fingerprint enrolment for member 50, then press the finger
  python tools/gateway_probe.py ... --enrol fingerprint --member 50
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hivebit_locks_access")
)

from lockcore.events import Method  # noqa: E402
from lockcore.profiles import PROFILES, get_profile  # noqa: E402
from lockcore.transport.tuya_gateway import TuyaGatewayTransport  # noqa: E402


def _stamp() -> str:
    return time.strftime("%H:%M:%S")


async def main(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile)
    transport = TuyaGatewayTransport(
        host=args.host,
        gateway_id=args.gateway_id,
        local_key=args.local_key,
        protocol_version=args.version,
        device_id=args.device_id,
        node_id=args.node_id,
    )
    connected = asyncio.Event()

    def on_dp(dp: int, value: object, snapshot: bool) -> None:
        kind = "status" if snapshot else "report"
        for event in profile.decode(dp, value):
            print(f"{_stamp()}  {kind:6}  DP {dp:<3} {value!r:<40} -> {event}")

    def on_available(available: bool) -> None:
        print(f"{_stamp()}  gateway {'CONNECTED' if available else 'DISCONNECTED'}")
        if available:
            connected.set()

    transport.set_callbacks(on_dp, on_available)
    await transport.async_start()
    try:
        try:
            await asyncio.wait_for(connected.wait(), 20)
        except TimeoutError:
            print("Could not connect within 20 s. Check host, IDs, local key and version.")
            return 1

        if args.unlock:
            write = profile.encode_remote_unlock(args.key_id, args.key)
            print(f"{_stamp()}  send    DP {write.dp} {write.value}")
            await transport.async_send(write)

        if args.enrol:
            write = profile.encode_enrol(Method(args.enrol), args.member)
            print(f"{_stamp()}  send    DP {write.dp} {write.value}  (go to the lock now)")
            await transport.async_send(write)

        print(f"Listening for {args.seconds} s. Ctrl+C to stop.")
        await asyncio.sleep(args.seconds)
    finally:
        await transport.async_stop()
    return 0


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", required=True, help="gateway IP address")
    p.add_argument("--gateway-id", required=True, help="gateway Tuya device ID")
    p.add_argument("--local-key", required=True, help="gateway local key")
    p.add_argument("--version", default="3.5", choices=["3.3", "3.4", "3.5"])
    p.add_argument("--device-id", required=True, help="lock Tuya device ID")
    p.add_argument("--node-id", required=True, help="lock node ID (cid) on the gateway")
    p.add_argument("--profile", default="moes_wdl_x1_zigbee", choices=sorted(PROFILES))
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--unlock", action="store_true")
    p.add_argument("--key-id", type=int, default=1)
    p.add_argument("--key", default="")
    p.add_argument("--enrol", choices=[m.value for m in (Method.FINGERPRINT, Method.CARD, Method.PIN)])
    p.add_argument("--member", type=int, default=50)
    args = p.parse_args()
    if args.unlock and len(args.key) != 8:
        p.error("--unlock needs --key with the 8-character remote unlock key")
    return args


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main(parse())))
    except KeyboardInterrupt:
        sys.exit(130)
