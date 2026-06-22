"""Guest-account retention purge for Mushin.

Anonymous guest accounts (``user.auth_provider = 'guest'``) are personal data
like logged-in accounts, but they are also the cheapest
accounts to create — a device cookie is enough. Left unchecked they accumulate
forever. This module enforces two retention windows:

- **Zero-entry guests** older than ``zero_entry_days`` (default 7): a guest
  that was created and never logged a single entry. ``created_at`` is the
  reference timestamp.
- **Inactive guests** older than ``inactive_days`` (default 30): a guest whose
  ``last_active_at`` has not been touched recently, regardless of whether they
  ever logged entries.

Either condition is sufficient to purge. A guest is purged by deleting its
``user`` row; ``ON DELETE CASCADE`` (declared from ``user`` in migration 0001)
removes every dependent row (category, activity, field_def, tag, entry,
entry_tag, entry_value, match) — no separate cleanup needed.

Owner model
-----------
This is a maintenance job, not a request-path accessor. It deliberately scans
*across* users (there is no single ``owner_id`` to scope to — the whole point
is finding accounts to remove) and therefore does NOT use the
``app.services._db`` owner-scoped helpers. Keep this separation: nothing here
should be reachable from a request handler, and nothing in the owner-scoped
accessors should need to see other users' rows.

Public API
----------
``purge_guests(conn, *, now, zero_entry_days=7, inactive_days=30, dry_run=False)``
    Returns the set of user ids that were (or would be, in dry-run) purged.
    ``now`` is injectable so tests don't depend on the wall clock.

Thin CLI: ``uv run python -m app.services.guest_reaper [--dry-run]``.
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

    Two independent conditions, OR'd together:

    1. Zero-entry guest: ``created_at`` older than ``zero_entry_days`` AND no
       rows in ``entry`` for that owner.
    2. Inactive guest: ``last_active_at`` older than ``inactive_days`` (NULL
       counts as "never active", i.e. always stale once ``created_at`` clears
       the same threshold via condition 1, or immediately if ``last_active_at``
       IS NULL and ``created_at`` is old enough under this clause too).

    A fresh guest (created moments ago, ``last_active_at`` NULL) matches
    neither: condition 1 requires ``created_at`` to be old, and condition 2
    requires ``last_active_at`` (or, if NULL, ``created_at``) to be old.
    """
    zero_entry_cutoff = _iso(now - timedelta(days=zero_entry_days))
    inactive_cutoff = _iso(now - timedelta(days=inactive_days))

    return conn.execute(
        """
        SELECT id, auth_provider, created_at, last_active_at
        FROM user
        WHERE auth_provider = 'guest'
          AND (
              -- Condition 1: zero-entry guest past the short grace window.
              (
                  created_at < ?
                  AND NOT EXISTS (SELECT 1 FROM entry WHERE entry.owner_id = user.id)
              )
              OR
              -- Condition 2: inactive past the long window. Fall back to
              -- created_at when last_active_at was never set.
              COALESCE(last_active_at, created_at) < ?
          )
        """,
        (zero_entry_cutoff, inactive_cutoff),
    ).fetchall()


def purge_guests(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    zero_entry_days: int = DEFAULT_ZERO_ENTRY_DAYS,
    inactive_days: int = DEFAULT_INACTIVE_DAYS,
    dry_run: bool = False,
) -> set[int]:
    """Purge (or, in dry-run, identify) stale guest accounts.

    Returns the set of ``user.id`` values that were purged (or would be,
    under ``dry_run``). Real accounts (``google``, ``email``) are
    never matched — the query is hard-filtered to ``auth_provider = 'guest'``.

    Deletion relies on ``ON DELETE CASCADE`` from ``user`` (migration 0001) to
    remove all dependent rows in one statement per user.

    Transaction handling follows the project convention (see ``stats.py`` /
    ``entries.py``): this function always issues ``BEGIN`` first — even for a
    dry run or an empty result — and leaves the final ``COMMIT``/``ROLLBACK``
    to the caller's ``db.connect()``/``db.connect_to()`` context manager
    (which commits on clean exit, rolls back on exception). With
    ``isolation_level=None``, a bare ``COMMIT`` with no open transaction
    raises ``OperationalError``, so ``BEGIN`` must always run.
    """
    conn.execute("BEGIN")

    candidates = _find_purge_candidates(
        conn,
        now=now,
        zero_entry_days=zero_entry_days,
        inactive_days=inactive_days,
    )
    purge_ids = {row["id"] for row in candidates}

    if dry_run:
        for row in candidates:
            log.info(
                "guest_reaper.would_purge",
                user_id=row["id"],
                created_at=row["created_at"],
                last_active_at=row["last_active_at"],
            )
        return purge_ids

    for user_id in purge_ids:
        conn.execute("DELETE FROM user WHERE id = ?", (user_id,))
        log.info("guest_reaper.purged", user_id=user_id)

    return purge_ids


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
