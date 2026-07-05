"""Guest-account retention purge for Mushin.

Simple username/password auth only — no guest accounts.
This module is kept as a stub so import paths don't break.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta

import structlog

from app.models import db

log = structlog.get_logger()

DEFAULT_ZERO_ENTRY_DAYS = 7
DEFAULT_INACTIVE_DAYS = 30


def _iso(dt: datetime) -> str:
    """Render a datetime as the same ISO 8601 string format SQLite stores."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _find_purge_candidates(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    zero_entry_days: int,
    inactive_days: int,
) -> list[sqlite3.Row]:
    """Return guest user rows matching either retention condition.

    No guest accounts exist anymore (simple username/password only),
    so this always returns an empty list.
    """
    return []


def purge_guests(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    zero_entry_days: int = DEFAULT_ZERO_ENTRY_DAYS,
    inactive_days: int = DEFAULT_INACTIVE_DAYS,
    dry_run: bool = False,
) -> set[int]:
    """No-op: no guest accounts exist. Returns empty set."""
    conn.execute("BEGIN")
    return set()


def _run_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Purge stale anonymous guest accounts (retention)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be purged without deleting anything.",
    )
    parser.add_argument(
        "--zero-entry-days",
        type=int,
        default=DEFAULT_ZERO_ENTRY_DAYS,
        help=f"Purge zero-entry guests older than this many days (default {DEFAULT_ZERO_ENTRY_DAYS}).",
    )
    parser.add_argument(
        "--inactive-days",
        type=int,
        default=DEFAULT_INACTIVE_DAYS,
        help=f"Purge inactive guests older than this many days (default {DEFAULT_INACTIVE_DAYS}).",
    )
    args = parser.parse_args()

    now = datetime.now()
    with db.connect() as conn:
        purged = purge_guests(
            conn,
            now=now,
            zero_entry_days=args.zero_entry_days,
            inactive_days=args.inactive_days,
            dry_run=args.dry_run,
        )

    verb = "Would purge" if args.dry_run else "Purged"
    log.info(
        "guest_reaper.run_complete",
        dry_run=args.dry_run,
        count=len(purged),
        user_ids=sorted(purged),
    )
    print(f"{verb} {len(purged)} guest account(s).")


if __name__ == "__main__":
    _run_cli()
