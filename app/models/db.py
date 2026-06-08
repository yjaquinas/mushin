"""SQLite connection management for Mushin.

One connection per request via the connect() context manager. Raw SQL only — no
ORM. Pragmas (WAL, foreign keys) are set on every connection. See the
sqlite-conventions skill for the full pattern.
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/app.db")


def _connect_raw() -> sqlite3.Connection:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Per-request connection. Commits on success, rolls back on exception."""
    conn = _connect_raw()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
