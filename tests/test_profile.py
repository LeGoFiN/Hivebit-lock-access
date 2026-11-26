"""Profile encode/decode against values captured on the bench lock."""

from __future__ import annotations

import pytest

from custom_components.hivebit_locks_access.lockcore.events import (
    AlarmReport,
    BatteryReport,
    DeleteReport,
    DoorReport,
    EnrolReport,
    EnrolStage,
    Method,
    UnlockReport,
)
from custom_components.hivebit_locks_access.lockcore.profiles import (
    PROFILES,
    GuestCodeSpec,
    ProfileError,
    get_profile,
)

P = get_profile("moes_wdl_x1_zigbee")


def test_registry_has_moes_and_generic() -> None:
    assert {"moes_wdl_x1_zigbee", "tuya_residential_zigbee"} <= set(PROFILES)


def test_guest_code_one_time_matches_cloud_capture() -> None:
    # Captured 2026-11-19: slot 999, one-time, PIN 109790.
    w = P.encode_guest_code(
        GuestCodeSpec(slot=999, pin="109790", start=0x6AFF5069, end=0x6B00A1E9, one_time=True)
    )
    assert w.dp == 24
    assert w.value == "A+cAAQAAav9QaWsAoekAAAAAAAABMTA5Nzkw"


def test_guest_code_reusable_matches_cloud_capture() -> None:
    w = P.encode_guest_code(
        GuestCodeSpec(slot=997, pin="123698", start=0x6AFCC081, end=0x6AFCCE91)
    )
    assert w.value == "A+UAAQAAavzAgWr8zpEAAAAAAAAAMTIzNjk4"


def test_guest_code_weekly_schedule_bytes() -> None:
    # Tue/Thu/Sat/Sun 13:00-14:00 -> 02 6A 0D 00 0E 00 (captured)
    w = P.encode_guest_code(
        GuestCodeSpec(
            slot=998,
            pin="147896",
            start=1,
            end=2,
            weekdays=frozenset({1, 3, 5, 6}),
            daily_from=(13, 0),
            daily_to=(14, 0),
        )
    )
    import base64

    raw = base64.b64decode(w.value)
    assert raw[14:20] == bytes([0x02, 0x6A, 0x0D, 0x00, 0x0E, 0x00])


def test_guest_code_rejects_bad_pin() -> None:
    with pytest.raises(ProfileError):
        P.encode_guest_code(GuestCodeSpec(slot=901, pin="12ab56", start=1, end=2))


def test_guest_delete_matches_app_capture() -> None:
    assert P.encode_guest_code_delete(999).value == "A+cAAQAA"
    assert P.encode_guest_code_delete(998).value == "A+YAAQAA"


def test_enrol_and_delete_match_bench_payloads() -> None:
    assert P.encode_enrol(Method.FINGERPRINT, 2).value == "AwAAAAID5w=="
    assert P.encode_enrol(Method.CARD, 2).value == "AgAAAAID5w=="
    assert P.encode_enrol(Method.PIN, 2).value == "AQAAAAID5w=="
    assert P.encode_enrol_cancel(Method.FINGERPRINT, 2).value == "A/4AAAID5w=="
    assert P.encode_delete_credential(Method.FINGERPRINT, 2, 14).value == "AwAAAAIADgE="
    assert P.encode_delete_credential(None, 2, None).value == "AAAAAAID5wA="


def test_enrol_reports_from_tuya_log() -> None:
    start = P.decode(54, "AwAAAAIADgQA")[0]
    assert start == EnrolReport(Method.FINGERPRINT, EnrolStage.STARTED, 2, 14, 4, 0)
    progress = P.decode(54, "A/wAAAIADgIA")[0]
    assert progress.stage is EnrolStage.PROGRESS and progress.presses_done == 2
    done = P.decode(54, "A/8AAAIADgQA")[0]
    assert done.stage is EnrolStage.DONE and done.lock_ref == 14


def test_enrol_failure_reason() -> None:
    # password enrolment that failed with status 0x01 (Nov 17 capture shape)
    import base64

    raw = bytes([0x01, 0xFD, 0x01, 0x00, 0x01, 0x00, 0x0C, 0x02, 0x01])
    rep = P.decode(54, base64.b64encode(raw).decode())[0]
    assert rep.stage is EnrolStage.FAILED and rep.reason == "failed"


def test_delete_report() -> None:
    import base64

    raw = bytes([0x03, 0x00, 0x00, 0x00, 0x02, 0x00, 0x0E, 0x01, 0xFF])
    rep = P.decode(55, base64.b64encode(raw).decode())[0]
    assert rep == DeleteReport(Method.FINGERPRINT, 2, 14, True, None)


def test_unlock_door_alarm_battery() -> None:
    assert P.decode(1, 14) == [UnlockReport(Method.FINGERPRINT, 14)]
    assert P.decode(3, 902) == [UnlockReport(Method.GUEST_CODE, 902)]
    assert P.decode(5, "7") == [UnlockReport(Method.CARD, 7)]
    assert P.decode(47, "closed") == [DoorReport(is_open=False)]
    assert P.decode(9, "pry") == [AlarmReport("pry")]
    assert P.decode(9, 9) == [AlarmReport("key_in")]
    assert P.decode(10, 100) == [BatteryReport(100)]


def test_remote_unlock_payload_shape() -> None:
    import base64

    raw = base64.b64decode(P.encode_remote_unlock(1, "97155270").value)
    assert len(raw) == 13
    assert raw[0] == 0x01 and raw[1:3] == b"\x00\x01" and raw[3:11] == b"97155270"
    assert raw[11:] == b"\x00\x01"
