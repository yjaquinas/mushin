"""Tests for the guest-account retention purge (Task 11).

Each test gets a fresh tmp_path-scoped SQLite DB with migration 0001 applied,
so the cascade behaviour exercised here matches the real schema.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.models.migrate import run_migrations
from app.services.guest_reaper import purge_guests

NOW = datetime(2026, 6, 10, 12, 0, 0)


def fresh_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _insert_user(
    conn: sqlite3.Connection,
    *,
    auth_provider: str,
    created_at: datetime,
    last_active_at: datetime | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, created_at, last_active_at) VALUES (?, ?, ?)",
        (
            auth_provider,
            _iso(created_at),
            _iso(last_active_at) if last_active_at else None,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _seed_owned_rows(conn: sqlite3.Connection, owner_id: int, *, with_entry: bool) -> None:
    """Insert a category/sub_tally and, optionally, an entry/match for owner_id."""
    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Cat', 0)",
        (owner_id,),
    )
    category_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)
           VALUES (?, ?, 'Sub', 'running', 0)""",
        (owner_id, category_id),
    )
    sub_tally_id = cur.lastrowid

    if with_entry:
        cur = conn.execute(
            "INSERT INTO entry (owner_id, sub_tally_id, occurred_at) VALUES (?, ?, ?)",
            (owner_id, sub_tally_id, _iso(NOW)),
        )
        entry_id = cur.lastrowid
        conn.execute(
            """INSERT INTO match (entry_id, owner_id, opponent, score, result, sort_order)
               VALUES (?, ?, 'Opp', '1-0', 'win', 0)""",
            (entry_id, owner_id),
        )

    conn.commit()


# ---------------------------------------------------------------------------
# Zero-entry guest, older than the grace window
# ---------------------------------------------------------------------------


def test_zero_entry_guest_past_grace_period_is_purged(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=8)
        guest_id = _insert_user(conn, auth_provider="guest", created_at=old_created)
        _seed_owned_rows(conn, guest_id, with_entry=False)

        purged = purge_guests(conn, now=NOW)

        assert guest_id in purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is None
    finally:
        conn.close()


def test_zero_entry_guest_within_grace_period_is_not_purged(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        recent_created = NOW - timedelta(days=2)
        guest_id = _insert_user(conn, auth_provider="guest", created_at=recent_created)
        _seed_owned_rows(conn, guest_id, with_entry=False)

        purged = purge_guests(conn, now=NOW)

        assert guest_id not in purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Guest with entries, but inactive past the long window
# ---------------------------------------------------------------------------


def test_guest_with_entries_inactive_past_30d_is_purged(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=60)
        old_active = NOW - timedelta(days=31)
        guest_id = _insert_user(
            conn, auth_provider="guest", created_at=old_created, last_active_at=old_active
        )
        _seed_owned_rows(conn, guest_id, with_entry=True)

        purged = purge_guests(conn, now=NOW)

        assert guest_id in purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is None
    finally:
        conn.close()


def test_active_guest_with_entries_is_not_purged(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=60)
        recent_active = NOW - timedelta(days=1)
        guest_id = _insert_user(
            conn, auth_provider="guest", created_at=old_created, last_active_at=recent_active
        )
        _seed_owned_rows(conn, guest_id, with_entry=True)

        purged = purge_guests(conn, now=NOW)

        assert guest_id not in purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Real accounts are never touched
# ---------------------------------------------------------------------------


def test_real_account_never_purged_even_if_old_and_inactive(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=365)
        old_active = NOW - timedelta(days=365)
        for provider in ("kakao", "google", "email"):
            user_id = _insert_user(
                conn,
                auth_provider=provider,
                created_at=old_created,
                last_active_at=old_active,
            )
            _seed_owned_rows(conn, user_id, with_entry=False)

        purged = purge_guests(conn, now=NOW)

        assert purged == set()
        count = conn.execute("SELECT COUNT(*) FROM user WHERE auth_provider != 'guest'").fetchone()[
            0
        ]
        assert count == 3
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cascade leaves no orphans
# ---------------------------------------------------------------------------


OWNED_TABLES = ["category", "sub_tally", "entry", "match"]


def test_purge_cascades_with_no_orphans(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=60)
        old_active = NOW - timedelta(days=31)
        guest_id = _insert_user(
            conn, auth_provider="guest", created_at=old_created, last_active_at=old_active
        )
        _seed_owned_rows(conn, guest_id, with_entry=True)

        for table in OWNED_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            assert count > 0, f"expected seeded rows in {table}"

        purged = purge_guests(conn, now=NOW)
        conn.execute("COMMIT")
        assert guest_id in purged

        for table in OWNED_TABLES:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE owner_id=?",  # noqa: S608
                (guest_id,),
            ).fetchone()[0]
            assert count == 0, f"orphan rows remain in {table}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_reports_but_does_not_delete(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        old_created = NOW - timedelta(days=8)
        guest_id = _insert_user(conn, auth_provider="guest", created_at=old_created)
        _seed_owned_rows(conn, guest_id, with_entry=False)

        purged = purge_guests(conn, now=NOW, dry_run=True)
        conn.execute("COMMIT")

        assert guest_id in purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is not None, "dry run must not delete"

        # A real (non-dry-run) call afterwards reports the same id and deletes it.
        purged_real = purge_guests(conn, now=NOW)
        conn.execute("COMMIT")
        assert purged_real == purged
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is None
    finally:
        conn.close()


def test_no_candidates_returns_empty_set(tmp_path: Path) -> None:
    conn = fresh_conn(tmp_path)
    try:
        guest_id = _insert_user(conn, auth_provider="guest", created_at=NOW)
        _seed_owned_rows(conn, guest_id, with_entry=False)

        purged = purge_guests(conn, now=NOW)

        assert purged == set()
        row = conn.execute("SELECT id FROM user WHERE id=?", (guest_id,)).fetchone()
        assert row is not None
    finally:
        conn.close()
