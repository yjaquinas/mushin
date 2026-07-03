"""Migration runner for Mushin.

Applies not-yet-applied integer-prefixed .sql files from app/models/migrations/
in filename order. Applied migrations are tracked in a ``_migrations`` table so
the runner is safe to call on every startup — already-applied files are skipped.

Usage
-----
From the project root::

    uv run python -m app.models.migrate          # applies to DATABASE_PATH
    uv run python -m app.models.migrate path/to/db  # applies to an explicit path

Or call ``run_migrations(db_path)`` programmatically (e.g. from app startup or
tests).

Transaction notes
-----------------
``sqlite3.connect(isolation_level=None)`` disables Python's implicit
transaction management. All transaction control is explicit.

``executescript()`` is intentionally NOT used here: it commits any open
transaction unconditionally before it runs (SQLite spec). Instead we split the
SQL file on semicolons and execute each statement individually inside an
explicit BEGIN/COMMIT block, which gives us a true atomic per-migration
transaction.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS _migrations (
    filename   TEXT NOT NULL PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def run_migrations(db_path: str | Path = "./data/app.db") -> list[str]:
    """Apply all pending migrations to *db_path*.

    Returns a list of filenames that were applied this run (empty if already
    up-to-date). Raises on any SQL error — the offending migration is rolled
    back and the ``_migrations`` row is not written.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        # Ensure the tracking table exists. We use execute() (not executescript)
        # so we control the transaction ourselves.
        _exec_transaction(conn, [_BOOTSTRAP_SQL.strip()])

        applied: set[str] = {
            row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()
        }

        migration_files = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if f.name not in applied)

        newly_applied: list[str] = []
        for mf in migration_files:
            sql = mf.read_text(encoding="utf-8")
            statements = _split_statements(sql)
            # Record the migration filename as the last statement in the same tx.
            statements.append(f"INSERT INTO _migrations (filename) VALUES ('{mf.name}')")
            _exec_transaction(conn, statements)
            newly_applied.append(mf.name)

        return newly_applied
    finally:
        conn.close()


def _exec_transaction(conn: sqlite3.Connection, statements: list[str]) -> None:
    """Execute *statements* inside a single BEGIN/COMMIT block."""
    conn.execute("BEGIN")
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements, dropping blanks/comments.

    Handles semicolons inside SQL line comments (``--``) correctly by
    processing the file line-by-line and only splitting on ``;`` that
    appear outside comments.
    """
    statements: list[str] = []
    current: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()

        # Skip pure comment lines but keep them in the current block
        # so they travel with the statement they annotate.
        if stripped.startswith("--"):
            if current is not None:
                current.append(line)
            continue

        # Accumulate lines into the current statement.
        current.append(line)

        # When we hit a ``;`` on a non-comment line, the statement is complete.
        if stripped.endswith(";"):
            block = "\n".join(current).strip()
            current = []
            # Skip blocks that have no non-comment content.
            non_comment = [
                l for l in block.splitlines()
                if l.strip() and not l.strip().startswith("--")
            ]
            if non_comment:
                statements.append(block)

    # Flush any remaining lines (no trailing ``;``).
    if current:
        block = "\n".join(current).strip()
        non_comment = [
            l for l in block.splitlines()
            if l.strip() and not l.strip().startswith("--")
        ]
        if non_comment:
            statements.append(block)

    return statements
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABASE_PATH", "./data/app.db")
    applied = run_migrations(path)
    if applied:
        for name in applied:
            print(f"applied: {name}")
    else:
        print("already up-to-date")
