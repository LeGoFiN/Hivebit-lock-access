"""Append-only, hash-chained event log in its own SQLite file.

Each row stores the hash of the row before it, so an edited or deleted row
breaks the chain and ``verify`` reports where. The only removal is the
retention purge, which logs itself with the first surviving hash.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

GENESIS = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
"""


def _digest(prev_hash: str, seq: int, ts: float, kind: str, data: str) -> str:
    body = json.dumps([prev_hash, seq, ts, kind, data], separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


class EventLog:
    """Blocking implementation; call through the executor from async code."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            raise RuntimeError("event log is not open")
        return self._db

    def append(self, kind: str, data: dict[str, Any], ts: float | None = None) -> dict[str, Any]:
        with self._lock:
            row = self.db.execute(
                "SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq = (row[0] + 1) if row else 1
            prev_hash = row[1] if row else GENESIS
            ts = time.time() if ts is None else ts
            payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = _digest(prev_hash, seq, ts, kind, payload)
            self.db.execute(
                "INSERT INTO events (seq, ts, kind, data, prev_hash, hash) VALUES (?,?,?,?,?,?)",
                (seq, ts, kind, payload, prev_hash, digest),
            )
            self.db.commit()
            return {"seq": seq, "ts": ts, "kind": kind, "data": data}

    def query(
        self,
        *,
        limit: int = 100,
        before_seq: int | None = None,
        kinds: list[str] | None = None,
        since_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT seq, ts, kind, data FROM events WHERE 1=1"
        args: list[Any] = []
        if before_seq is not None:
            sql += " AND seq < ?"
            args.append(before_seq)
        if since_ts is not None:
            sql += " AND ts >= ?"
            args.append(since_ts)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args.extend(kinds)
        sql += " ORDER BY seq DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
        return [
            {"seq": seq, "ts": ts, "kind": kind, "data": json.loads(data)}
            for seq, ts, kind, data in rows
        ]

    def purge_older_than(self, cutoff_ts: float) -> int:
        with self._lock:
            cur = self.db.execute("DELETE FROM events WHERE ts < ?", (cutoff_ts,))
            removed = cur.rowcount
            self.db.commit()
            first = self.db.execute(
                "SELECT seq, hash FROM events ORDER BY seq ASC LIMIT 1"
            ).fetchone()
        if removed:
            self.append(
                "purge",
                {
                    "removed": removed,
                    "cutoff": cutoff_ts,
                    "first_seq": first[0] if first else None,
                    "first_hash": first[1] if first else None,
                },
            )
        return removed

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, first bad seq). Starts from the oldest surviving row."""
        with self._lock:
            rows = self.db.execute(
                "SELECT seq, ts, kind, data, prev_hash, hash FROM events ORDER BY seq ASC"
            ).fetchall()
        expected_prev: str | None = None
        for seq, ts, kind, data, prev_hash, digest in rows:
            if expected_prev is not None and prev_hash != expected_prev:
                return False, seq
            if _digest(prev_hash, seq, ts, kind, data) != digest:
                return False, seq
            expected_prev = digest
        return True, None
