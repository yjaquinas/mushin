"""SQLite connection management for Mushin.

One connection per request via the connect() context manager. Raw SQL only — no
ORM. Pragmas (WAL, foreign keys, synchronous, temp_store) are set on every
connection. See the sqlite-conventions skill for the full pattern.

Public API
----------
connect()         -- context manager for the configured DB_PATH (used by app code)
connect_to(path)  -- context manager for an explicit path (used by tests and migrate.py)
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/app.db")


def _configure(conn: sqlite3.Connection) -> None:
    """Apply mandatory pragmas.

    WAL is durable at the file level, but foreign_keys and busy_timeout are
    per-connection and must be re-applied on every open.
    """
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")


@contextmanager
def connect_to(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Per-request connection to an explicit DB path.

    Commits on clean exit, rolls back on any exception, always closes.
    ``isolation_level=None`` disables Python's implicit transaction management
    so that we control BEGIN/COMMIT/ROLLBACK ourselves (or rely on SQLite's
    autocommit for single statements outside an explicit transaction).
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
    _configure(conn)
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            # No active transaction to roll back — that is fine.
            pass
        raise
    finally:
        conn.close()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Per-request connection to the configured DATABASE_PATH."""
    with connect_to(DATABASE_PATH) as conn:
        yield conn
