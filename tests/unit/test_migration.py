"""Tests for migration 0001 and the migration runner.

Acceptance criteria
-------------------
1. Migration runner applies cleanly against a fresh DB; ``PRAGMA integrity_check``
   returns ``ok``.
2. FK cascade: inserting a user + one row in every owned table, then deleting
   the user, leaves no orphans anywhere.
3. ``EXPLAIN QUERY PLAN`` for the entry-list query uses ``idx_entry_subtally_time``.

Each test gets its own fresh ``tmp_path``-scoped SQLite file (never ``:memory:``
because SQLite's ``executescript`` and some pragma behaviour differ there, and
the tests exercise the same path the app uses).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh_db(tmp_path: Path) -> Path:
    """Return path to a freshly-migrated DB inside *tmp_path*."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def raw_conn(db_path: Path) -> sqlite3.Connection:
    """Open a plain connection with foreign_keys ON (no isolation_level tweak)."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. Migration applies cleanly; integrity_check passes
# ---------------------------------------------------------------------------


def test_migration_applies_cleanly(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok", f"integrity_check failed: {result[0]}"
    finally:
        conn.close()


def test_migration_runner_is_idempotent(tmp_path: Path) -> None:
    """Running the runner twice applies 0001 only once."""
    db_path = tmp_path / "test.db"
    first_run = run_migrations(db_path)
    second_run = run_migrations(db_path)
    assert "0001_initial.sql" in first_run
    assert second_run == [], "Second run should apply nothing"


def test_all_expected_tables_exist(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in rows}
        expected = {
            "_migrations",
            "user",
            "category",
            "sub_tally",
            "field_def",
            "tag",
            "entry",
            "entry_tag",
            "entry_value",
            "match",
            "level",
            "level_rule",
        }
        missing = expected - table_names
        assert not missing, f"Missing tables: {missing}"
    finally:
        conn.close()


def test_all_expected_indexes_exist(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        ).fetchall()
        index_names = {row[0] for row in rows}
        expected = {
            "idx_entry_subtally_time",
            "idx_sub_tally_category_active",
            "idx_category_owner_active",
            "idx_match_entry",
            "idx_level_subtally_track_ordinal",
            "idx_user_guest_last_active",
        }
        missing = expected - index_names
        assert not missing, f"Missing indexes: {missing}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. FK cascade: delete user removes all dependent rows
# ---------------------------------------------------------------------------


def _seed_all_tables(conn: sqlite3.Connection) -> int:
    """Insert one row per owned table under a new user; return the user id."""
    conn.execute("PRAGMA foreign_keys=ON")

    cur = conn.execute(
        "INSERT INTO user (auth_provider, display_name) VALUES ('email', 'Test User')"
    )
    user_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Kendo', 0)",
        (user_id,),
    )
    category_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)
           VALUES (?, ?, 'Practice', 'running', 0)""",
        (user_id, category_id),
    )
    sub_tally_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO field_def (sub_tally_id, kind, label, sort_order)
           VALUES (?, 'memo', 'Notes', 0)""",
        (sub_tally_id,),
    )
    field_def_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO tag (owner_id, field_def_id, name, sort_order)
           VALUES (?, ?, 'morning', 0)""",
        (user_id, field_def_id),
    )
    tag_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO entry (owner_id, sub_tally_id, occurred_at)
           VALUES (?, ?, '2026-06-01T09:00:00')""",
        (user_id, sub_tally_id),
    )
    entry_id = cur.lastrowid

    conn.execute(
        "INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)",
        (entry_id, tag_id),
    )
    conn.execute(
        """INSERT INTO entry_value (entry_id, field_def_id, text_value)
           VALUES (?, ?, 'Good session')""",
        (entry_id, field_def_id),
    )
    conn.execute(
        """INSERT INTO match (entry_id, owner_id, opponent, score, result, sort_order)
           VALUES (?, ?, 'Opponent A', '2-1', 'win', 0)""",
        (entry_id, user_id),
    )

    cur = conn.execute(
        """INSERT INTO level (sub_tally_id, owner_id, track, ordinal, code, label)
           VALUES (?, ?, 'dan', 1, '1dan', '1단')""",
        (sub_tally_id, user_id),
    )
    level_id = cur.lastrowid

    conn.execute(
        """INSERT INTO level_rule
               (owner_id, sub_tally_id, from_level_id, to_level_id, gate_type)
           VALUES (?, ?, NULL, ?, 'count')""",
        (user_id, sub_tally_id, level_id),
    )

    conn.commit()
    return user_id


OWNED_TABLES = [
    "category",
    "sub_tally",
    "field_def",
    "tag",
    "entry",
    "entry_tag",
    "entry_value",
    "match",
    "level",
    "level_rule",
]


def test_cascade_delete_removes_all_owned_rows(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)

    # Use autocommit-style conn for seeding (isolation_level=None with manual COMMIT)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    try:
        user_id = _seed_all_tables(conn)

        # Verify rows exist before deletion
        for table in OWNED_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            assert count > 0, f"Expected rows in {table} before cascade delete"

        # Delete the user — cascade should propagate
        conn.execute("DELETE FROM user WHERE id=?", (user_id,))
        conn.commit()

        # Verify no orphans remain
        for table in OWNED_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            assert count == 0, f"Orphan rows remain in {table} after cascade delete"

        user_count = conn.execute("SELECT COUNT(*) FROM user WHERE id=?", (user_id,)).fetchone()[0]
        assert user_count == 0, "User row should be gone"
    finally:
        conn.close()


def test_cascade_delete_leaves_other_users_data_intact(tmp_path: Path) -> None:
    """Deleting user A must not touch user B's rows."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    try:
        user_a = _seed_all_tables(conn)
        user_b = _seed_all_tables(conn)

        conn.execute("DELETE FROM user WHERE id=?", (user_a,))
        conn.commit()

        # User B's category should still exist
        count = conn.execute(
            "SELECT COUNT(*) FROM category WHERE owner_id=?", (user_b,)
        ).fetchone()[0]
        assert count > 0, "User B's category was incorrectly deleted"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3. EXPLAIN QUERY PLAN uses idx_entry_subtally_time
# ---------------------------------------------------------------------------


def test_entry_list_query_uses_index(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        plan_rows = conn.execute(
            """EXPLAIN QUERY PLAN
               SELECT * FROM entry
               WHERE sub_tally_id = ?
               ORDER BY occurred_at DESC""",
            (1,),
        ).fetchall()
        # sqlite3.Row must be converted to tuple before str() shows the values.
        plan_text = " ".join(str(tuple(row)) for row in plan_rows).lower()
        assert "idx_entry_subtally_time" in plan_text, (
            f"Expected idx_entry_subtally_time in query plan, got: {plan_text}"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 4. Constraint checks
# ---------------------------------------------------------------------------


def test_auth_provider_check_constraint(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO user (auth_provider) VALUES ('twitter')",
            )
    finally:
        conn.close()


def test_entry_value_requires_at_least_one_value(tmp_path: Path) -> None:
    """entry_value CHECK: num_value IS NOT NULL OR text_value IS NOT NULL."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        # Seed minimal parent rows
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        uid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
            (uid,),
        )
        cat_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, 'S', 'running', 0)",
            (uid, cat_id),
        )
        st_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (sub_tally_id, kind, label, sort_order)"
            " VALUES (?, 'count', 'Reps', 0)",
            (st_id,),
        )
        fd_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO entry (owner_id, sub_tally_id, occurred_at)"
            " VALUES (?, ?, '2026-06-01T10:00:00')",
            (uid, st_id),
        )
        entry_id = cur.lastrowid
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO entry_value (entry_id, field_def_id, num_value, text_value)"
                " VALUES (?, ?, NULL, NULL)",
                (entry_id, fd_id),
            )
    finally:
        conn.close()


def test_count_mode_check_constraint(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('guest')")
        uid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
            (uid,),
        )
        cat_id = cur.lastrowid
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)"
                " VALUES (?, ?, 'S', 'invalid_mode', 0)",
                (uid, cat_id),
            )
    finally:
        conn.close()
