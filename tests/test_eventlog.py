"""Hash-chained event log."""

from __future__ import annotations

from pathlib import Path

from custom_components.hivebit_locks_access.eventlog import EventLog


def _log(tmp_path: Path) -> EventLog:
    log = EventLog(tmp_path / "events.db")
    log.open()
    return log


def test_chain_verifies_and_detects_edits(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for i in range(5):
        log.append("unlock", {"n": i})
    assert log.verify() == (True, None)

    log.db.execute("UPDATE events SET data = ? WHERE seq = 3", ('{"n":99}',))
    log.db.commit()
    assert log.verify() == (False, 3)


def test_deleted_middle_row_is_detected(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for i in range(5):
        log.append("unlock", {"n": i})
    log.db.execute("DELETE FROM events WHERE seq = 2")
    log.db.commit()
    assert log.verify() == (False, 3)


def test_purge_keeps_chain_valid_and_logs_itself(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.append("unlock", {"n": 0}, ts=100.0)
    log.append("unlock", {"n": 1}, ts=200.0)
    log.append("unlock", {"n": 2}, ts=300.0)
    assert log.purge_older_than(250.0) == 2
    assert log.verify() == (True, None)
    newest = log.query(limit=1)[0]
    assert newest["kind"] == "purge" and newest["data"]["removed"] == 2
