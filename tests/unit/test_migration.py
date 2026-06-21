"""Tests for migrations and the migration runner.

Acceptance criteria
-------------------
1. Migration runner applies cleanly against a fresh DB; ``PRAGMA integrity_check``
   returns ``ok``.
2. FK cascade: inserting a user + one row in every owned table, then deleting
   the user, leaves no orphans anywhere.
3. ``EXPLAIN QUERY PLAN`` for the entry-list query uses ``idx_entry_activity_time``
   (renamed from ``idx_entry_subtally_time`` by migration 0009).

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
            "activity",
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
            "idx_entry_activity_time",
            "idx_activity_category_active",
            "idx_category_owner_active",
            "idx_match_entry",
            "idx_level_activity_track_ordinal",
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
        """INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)
           VALUES (?, ?, 'Practice', 'running', 0)""",
        (user_id, category_id),
    )
    activity_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO field_def (activity_id, kind, label, sort_order)
           VALUES (?, 'memo', 'Notes', 0)""",
        (activity_id,),
    )
    field_def_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO tag (owner_id, field_def_id, name, sort_order)
           VALUES (?, ?, 'morning', 0)""",
        (user_id, field_def_id),
    )
    tag_id = cur.lastrowid

    cur = conn.execute(
        """INSERT INTO entry (owner_id, activity_id, occurred_at)
           VALUES (?, ?, '2026-06-01T09:00:00')""",
        (user_id, activity_id),
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
        """INSERT INTO level (activity_id, owner_id, track, ordinal, code, label)
           VALUES (?, ?, 'dan', 1, '1dan', '1단')""",
        (activity_id, user_id),
    )
    level_id = cur.lastrowid

    conn.execute(
        """INSERT INTO level_rule
               (owner_id, activity_id, from_level_id, to_level_id, gate_type)
           VALUES (?, ?, NULL, ?, 'count')""",
        (user_id, activity_id, level_id),
    )

    conn.commit()
    return user_id


OWNED_TABLES = [
    "category",
    "activity",
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
               WHERE activity_id = ?
               ORDER BY occurred_at DESC""",
            (1,),
        ).fetchall()
        # sqlite3.Row must be converted to tuple before str() shows the values.
        plan_text = " ".join(str(tuple(row)) for row in plan_rows).lower()
        assert "idx_entry_activity_time" in plan_text, (
            f"Expected idx_entry_activity_time in query plan, got: {plan_text}"
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
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, 'S', 'running', 0)",
            (uid, cat_id),
        )
        st_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'count', 'Reps', 0)",
            (st_id,),
        )
        fd_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO entry (owner_id, activity_id, occurred_at)"
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


def test_migration_0004_drops_kakao_and_adds_timezone(tmp_path: Path) -> None:
    """Migration 0004: auth_provider CHECK no longer allows 'kakao', and the
    new ``timezone`` column defaults to 'UTC'."""
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()}
        assert "0004_user_timezone_and_providers.sql" in applied

        # CHECK constraint rejects 'kakao'.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO user (auth_provider) VALUES ('kakao')")

        # 'google' is still accepted, and timezone defaults to 'UTC'.
        conn.execute("INSERT INTO user (auth_provider) VALUES ('google')")
        row = conn.execute("SELECT timezone FROM user WHERE auth_provider='google'").fetchone()
        assert row["timezone"] == "UTC"
    finally:
        conn.close()


def test_migration_0005_adds_visibility_and_consent_columns(tmp_path: Path) -> None:
    """Migration 0005: user.visibility defaults to 'private', is CHECK-constrained
    to ('public','private'), and user.consent_seen_at defaults to NULL."""
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()}
        assert "0005_user_visibility.sql" in applied

        conn2 = sqlite3.connect(str(db_path), isolation_level=None)
        conn2.execute("PRAGMA foreign_keys=ON")
        cur = conn2.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        uid = cur.lastrowid
        row = conn2.execute(
            "SELECT visibility, consent_seen_at FROM user WHERE id=?", (uid,)
        ).fetchone()
        assert row[0] == "private"
        assert row[1] is None

        # CHECK constraint rejects invalid visibility values.
        with pytest.raises(sqlite3.IntegrityError):
            conn2.execute("UPDATE user SET visibility='nope' WHERE id=?", (uid,))

        # 'public' is accepted.
        conn2.execute("UPDATE user SET visibility='public' WHERE id=?", (uid,))
        conn2.commit()
        row = conn2.execute("SELECT visibility FROM user WHERE id=?", (uid,)).fetchone()
        assert row[0] == "public"
        conn2.close()
    finally:
        conn.close()


def test_migration_0006_backfills_unique_slugs(tmp_path: Path) -> None:
    """Migration 0006: every activity row gets a non-null slug, unique per
    owner_id, with collisions (including same-name duplicates) de-duplicated."""
    db_path = tmp_path / "test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Apply 0001–0005 and 0007–0008, hiding 0006 (the migration under test),
    # 0009 (the rename), and 0011 (the multi-activity-category merge, which
    # queries the post-0009 `activity` table name and so can't run yet either)
    # so we can seed activity rows while the table still has its original
    # name.  After seeding we restore all three and run again so 0006
    # backfills slugs, 0009 renames the table, and 0011 runs against the
    # renamed table — in that order.
    import shutil

    from app.models.migrate import MIGRATIONS_DIR

    migration_0006 = MIGRATIONS_DIR / "0006_sub_tally_slug.sql"
    migration_0009 = MIGRATIONS_DIR / "0009_rename_sub_tally_to_activity.sql"
    migration_0011 = MIGRATIONS_DIR / "0011_merge_multi_activity_categories.sql"
    tmp_hidden_0006 = MIGRATIONS_DIR / "0006_sub_tally_slug.sql.hidden"
    tmp_hidden_0009 = MIGRATIONS_DIR / "0009_rename_sub_tally_to_activity.sql.hidden"
    tmp_hidden_0011 = MIGRATIONS_DIR / "0011_merge_multi_activity_categories.sql.hidden"
    shutil.move(migration_0006, tmp_hidden_0006)
    shutil.move(migration_0009, tmp_hidden_0009)
    shutil.move(migration_0011, tmp_hidden_0011)
    try:
        run_migrations(db_path)
    finally:
        shutil.move(tmp_hidden_0006, migration_0006)
        shutil.move(tmp_hidden_0009, migration_0009)
        shutil.move(tmp_hidden_0011, migration_0011)

    # Seed rows needing slugs, including a same-owner name collision
    # and an empty/non-alphanumeric name.  The table is still named 'sub_tally'
    # at this point (0009 hasn't run yet).
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")

    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    owner_a = cur.lastrowid
    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    owner_b = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Fitness', 0)",
        (owner_a,),
    )
    cat_a = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Fitness', 0)",
        (owner_b,),
    )
    cat_b = cur.lastrowid

    activity_rows = [
        (owner_a, cat_a, "Workout"),
        (owner_a, cat_a, "Workout"),  # duplicate name, same owner
        (owner_a, cat_a, "Café Run #1!"),
        (owner_b, cat_b, "Workout"),  # same name, different owner -- no collision
        (owner_a, cat_a, "!!!"),  # nothing alphanumeric
    ]
    inserted_ids = []
    for owner_id, category_id, name in activity_rows:
        cur = conn.execute(
            "INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, 'running', 0)",
            (owner_id, category_id, name),
        )
        inserted_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()

    # Now apply 0006.
    applied = run_migrations(db_path)
    assert "0006_sub_tally_slug.sql" in applied

    conn = raw_conn(db_path)
    try:
        # After run_migrations completes, 0009 has also been applied so the
        # table is now named 'activity'.
        rows = conn.execute("SELECT id, owner_id, name, slug FROM activity ORDER BY id").fetchall()
        by_id = {row["id"]: row for row in rows}

        # Every row has a non-null, non-empty slug.
        for row in rows:
            assert row["slug"], f"activity {row['id']} has empty/null slug"

        # The pre-existing 'Workout' (id=1) is also present and slugged.
        assert by_id[1]["slug"]

        a1, a2, a3, b1, a4 = (by_id[i] for i in inserted_ids)

        # Same owner, same name -> distinct slugs.
        assert a1["slug"] != a2["slug"]
        assert a1["slug"].startswith("workout")
        assert a2["slug"].startswith("workout")

        # Accented/punctuated name slugifies to ascii lowercase hyphenated.
        assert a3["slug"] == "cafe-run-1"

        # Different owner, same name -> no collision required, both valid.
        assert b1["slug"] == "workout"

        # Non-alphanumeric name gets a fallback slug.
        assert a4["slug"] == f"sub-tally-{a4['id']}"

        # Uniqueness per (owner_id, slug) among non-archived rows.
        dupes = conn.execute(
            """SELECT owner_id, slug, COUNT(*) AS c
               FROM activity
               WHERE archived_at IS NULL
               GROUP BY owner_id, slug
               HAVING c > 1"""
        ).fetchall()
        assert dupes == [], f"Duplicate (owner_id, slug) pairs: {dupes}"

        # Unique index exists (created by 0006; still named ux_activity_owner_slug).
        index_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert "ux_activity_owner_slug" in index_names

        # Index enforces uniqueness on insert (table is 'activity' post-0009).
        conn2 = sqlite3.connect(str(db_path), isolation_level=None)
        conn2.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn2.execute(
                "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order, slug)"
                " VALUES (?, ?, 'Dup', 'running', 0, ?)",
                (owner_a, cat_a, a1["slug"]),
            )
        conn2.close()

        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn.close()


def test_migration_0007_adds_time_known_column(tmp_path: Path) -> None:
    """Migration 0007: entry.time_known is INTEGER NOT NULL DEFAULT 1.

    Verified on:
    - a fresh DB (all migrations applied at once),
    - a DB that already has an entry row (backfill via DEFAULT 1).
    """
    import shutil

    from app.models.migrate import MIGRATIONS_DIR

    # --- fresh DB -----------------------------------------------------------
    db_fresh = fresh_db(tmp_path / "fresh")
    conn = raw_conn(db_fresh)
    try:
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()}
        assert "0007_entry_time_known.sql" in applied

        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(entry)").fetchall()}
        assert "time_known" in cols, "time_known column missing from entry"
        col = cols["time_known"]
        assert col[2].upper() == "INTEGER", f"Expected INTEGER type, got {col[2]}"
        assert col[3] == 1, "time_known should be NOT NULL (notnull=1)"
        assert str(col[4]) == "1", f"Expected dflt_value=1, got {col[4]}"

        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn.close()

    # --- pre-existing entry row (simulate upgrade path) ---------------------
    db_pre = tmp_path / "pre" / "test.db"
    db_pre.parent.mkdir(parents=True, exist_ok=True)

    migration_0007 = MIGRATIONS_DIR / "0007_entry_time_known.sql"
    tmp_hidden = MIGRATIONS_DIR / "0007_entry_time_known.sql.hidden"
    shutil.move(migration_0007, tmp_hidden)
    try:
        run_migrations(db_pre)
    finally:
        shutil.move(tmp_hidden, migration_0007)

    # Insert an entry row before the column exists.
    # 0009 has already applied (only 0007 was hidden), so the table is 'activity'
    # and the FK column is 'activity_id'.
    conn2 = sqlite3.connect(str(db_pre), isolation_level=None)
    conn2.execute("PRAGMA foreign_keys=ON")
    cur = conn2.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    uid = cur.lastrowid
    cur = conn2.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)", (uid,)
    )
    cat_id = cur.lastrowid
    cur = conn2.execute(
        "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
        " VALUES (?, ?, 'S', 'running', 0)",
        (uid, cat_id),
    )
    st_id = cur.lastrowid
    cur = conn2.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at)"
        " VALUES (?, ?, '2026-06-01T09:00:00')",
        (uid, st_id),
    )
    entry_id = cur.lastrowid
    conn2.commit()
    conn2.close()

    # Now apply 0007.
    newly = run_migrations(db_pre)
    assert "0007_entry_time_known.sql" in newly

    conn3 = raw_conn(db_pre)
    try:
        row = conn3.execute("SELECT time_known FROM entry WHERE id=?", (entry_id,)).fetchone()
        assert row is not None, "entry row not found after migration"
        assert row[0] == 1, f"Expected time_known=1, got {row[0]}"

        result = conn3.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn3.close()


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
                "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
                " VALUES (?, ?, 'S', 'invalid_mode', 0)",
                (uid, cat_id),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 5. Migration 0008: tag active-name deduplication and unique index
# ---------------------------------------------------------------------------


def test_migration_0008_deduplicates_and_enforces_unique_active_tag_name(
    tmp_path: Path,
) -> None:
    """Migration 0008 normalizes tag names to lowercase, archives duplicate
    active tags (keeping MIN(id)), re-points entry_tag rows, and adds a partial
    unique index preventing future duplicates among active tags.

    Steps:
    1. Apply migrations 0001–0007 (hiding 0008).
    2. Insert two active tags with the same (owner_id, field_def_id) and names
       differing only in case ("Waza" and "waza"), plus an entry_tag pointing
       to the higher-id (loser) tag.
    3. Apply 0008.
    4. Verify only one active tag remains.
    5. Verify the entry_tag now points to the winner tag.
    6. Verify inserting another active tag with the same name raises IntegrityError.
    """
    import shutil

    from app.models.migrate import MIGRATIONS_DIR

    db_path = tmp_path / "test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    migration_0008 = MIGRATIONS_DIR / "0008_tag_active_unique.sql"
    tmp_hidden = MIGRATIONS_DIR / "0008_tag_active_unique.sql.hidden"
    shutil.move(migration_0008, tmp_hidden)
    try:
        run_migrations(db_path)
    finally:
        shutil.move(tmp_hidden, migration_0008)

    # Seed: one user, one category, one activity, one field_def, two tags
    # with the same name differing only in case, and one entry pointing at
    # the loser (higher-id) tag.
    # 0009 has already applied (only 0008 was hidden), so the table is 'activity'
    # and the FK column is 'activity_id'.
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")

    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    uid = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Kendo', 0)",
        (uid,),
    )
    cat_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
        " VALUES (?, ?, 'Practice', 'running', 0)",
        (uid, cat_id),
    )
    st_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO field_def (activity_id, kind, label, sort_order)"
        " VALUES (?, 'tag_group', 'Techniques', 0)",
        (st_id,),
    )
    fd_id = cur.lastrowid

    # Winner: "Waza" — inserted first so it gets the lower id.
    cur = conn.execute(
        "INSERT INTO tag (owner_id, field_def_id, name, sort_order) VALUES (?, ?, 'Waza', 0)",
        (uid, fd_id),
    )
    winner_id = cur.lastrowid

    # Loser: "waza" — same name, case-insensitively; higher id.
    cur = conn.execute(
        "INSERT INTO tag (owner_id, field_def_id, name, sort_order) VALUES (?, ?, 'waza', 1)",
        (uid, fd_id),
    )
    loser_id = cur.lastrowid

    # One entry whose entry_tag points to the loser.
    cur = conn.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at)"
        " VALUES (?, ?, '2026-06-17T10:00:00')",
        (uid, st_id),
    )
    entry_id = cur.lastrowid

    conn.execute(
        "INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)",
        (entry_id, loser_id),
    )
    conn.commit()
    conn.close()

    # Apply 0008.
    applied = run_migrations(db_path)
    assert "0008_tag_active_unique.sql" in applied

    conn = raw_conn(db_path)
    try:
        # Only one active tag remains.
        active_tags = conn.execute(
            "SELECT id, name FROM tag WHERE owner_id=? AND field_def_id=? AND archived_at IS NULL",
            (uid, fd_id),
        ).fetchall()
        assert len(active_tags) == 1, (
            f"Expected 1 active tag, found {len(active_tags)}: {list(active_tags)}"
        )

        # The surviving tag is the winner (MIN id) with lowercase name.
        surviving = active_tags[0]
        assert surviving["id"] == winner_id, (
            f"Expected winner id {winner_id}, got {surviving['id']}"
        )
        assert surviving["name"] == "waza", (
            f"Expected normalized name 'waza', got '{surviving['name']}'"
        )

        # The loser was archived, not deleted.
        loser_row = conn.execute("SELECT archived_at FROM tag WHERE id=?", (loser_id,)).fetchone()
        assert loser_row is not None, "Loser tag row was deleted; expected it to be archived"
        assert loser_row["archived_at"] is not None, "Loser tag archived_at should not be NULL"

        # entry_tag was re-pointed to the winner.
        et_row = conn.execute(
            "SELECT tag_id FROM entry_tag WHERE entry_id=?", (entry_id,)
        ).fetchone()
        assert et_row is not None, "entry_tag row missing"
        assert et_row["tag_id"] == winner_id, (
            f"entry_tag.tag_id should be winner {winner_id}, got {et_row['tag_id']}"
        )

        # The unique index exists.
        index_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert "idx_tag_active_name" in index_names, "idx_tag_active_name index not found"

        # Integrity check passes.
        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn.close()

    # Inserting a new active tag with the same name as the surviving one raises IntegrityError.
    conn2 = sqlite3.connect(str(db_path), isolation_level=None)
    conn2.execute("PRAGMA foreign_keys=ON")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn2.execute(
                "INSERT INTO tag (owner_id, field_def_id, name, sort_order)"
                " VALUES (?, ?, 'waza', 2)",
                (uid, fd_id),
            )
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# 6. Migration 0010: social graph (connection + block) — raw schema guarantees
# ---------------------------------------------------------------------------


def _insert_user(conn: sqlite3.Connection, username: str) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username) VALUES ('email', ?)", (username,)
    )
    return cur.lastrowid


def test_migration_0010_applies_and_adds_redefinition_column(tmp_path: Path) -> None:
    """0010 is recorded as applied; user gains private_redefinition_seen_at
    (NULL by default)."""
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()}
        assert "0010_social_graph.sql" in applied

        cols = {row[1] for row in conn.execute("PRAGMA table_info(user)").fetchall()}
        assert "private_redefinition_seen_at" in cols

        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        uid = cur.lastrowid
        row = conn.execute(
            "SELECT private_redefinition_seen_at FROM user WHERE id=?", (uid,)
        ).fetchone()
        assert row[0] is None
    finally:
        conn.close()


def test_migration_0010_connection_and_block_tables_exist_with_indexes(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"connection", "block"} <= tables

        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        expected = {
            "ux_connection_pair",
            "idx_connection_addressee_status",
            "idx_connection_lo_status",
            "idx_connection_hi_status",
            "ux_block_pair",
            "idx_block_blocked",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes: {missing}"
    finally:
        conn.close()


def test_migration_0010_unique_pair_index_rejects_reverse_duplicate_at_sql_level(
    tmp_path: Path,
) -> None:
    """The raw UNIQUE INDEX on (user_lo, user_hi) — not just the service-layer
    catch — rejects a reverse-duplicate row (B->A when A->B already exists),
    proving the schema-level guard Task 1 calls for independent of
    ``app.services.connections``."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        a = _insert_user(conn, "alice")
        b = _insert_user(conn, "bob")
        conn.commit()

        lo, hi = (a, b) if a < b else (b, a)
        conn.execute(
            "INSERT INTO connection (requester_id, addressee_id, user_lo, user_hi)"
            " VALUES (?, ?, ?, ?)",
            (a, b, lo, hi),
        )
        conn.commit()

        # The reverse orientation (B->A) collides on the same canonical pair.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO connection (requester_id, addressee_id, user_lo, user_hi)"
                " VALUES (?, ?, ?, ?)",
                (b, a, lo, hi),
            )
    finally:
        conn.close()


def test_migration_0010_connection_check_constraints(tmp_path: Path) -> None:
    """requester_id <> addressee_id and user_lo < user_hi are enforced by the
    raw CHECK constraints, not merely by service-layer discipline."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        a = _insert_user(conn, "alice")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO connection (requester_id, addressee_id, user_lo, user_hi)"
                " VALUES (?, ?, ?, ?)",
                (a, a, a, a),
            )

        b = _insert_user(conn, "bob")
        conn.commit()
        hi, lo = (b, a) if a < b else (a, b)  # deliberately swapped to violate lo < hi
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO connection (requester_id, addressee_id, user_lo, user_hi)"
                " VALUES (?, ?, ?, ?)",
                (a, b, hi, lo),
            )
    finally:
        conn.close()


def test_migration_0010_block_check_constraint_and_unique_pair(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        a = _insert_user(conn, "alice")
        b = _insert_user(conn, "bob")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)", (a, a))

        conn.execute("INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)", (a, b))
        conn.commit()
        # Block is one-directional: (b, a) is a DIFFERENT pair and must succeed
        # (block has no canonical-pair folding, unlike connection).
        conn.execute("INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)", (b, a))
        conn.commit()
        # But the identical (a, b) pair again is rejected by ux_block_pair.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)", (a, b))
    finally:
        conn.close()


def test_migration_0010_deleting_user_cascades_connection_and_block_at_sql_level(
    tmp_path: Path,
) -> None:
    """Raw FK ON DELETE CASCADE — independent of app.auth.users.delete_user —
    removes connection/block rows referencing the deleted user in either
    column, per Task 1's acceptance criterion."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        a = _insert_user(conn, "alice")
        b = _insert_user(conn, "bob")
        c = _insert_user(conn, "carol")
        conn.commit()

        lo, hi = (a, b) if a < b else (b, a)
        conn.execute(
            "INSERT INTO connection (requester_id, addressee_id, user_lo, user_hi)"
            " VALUES (?, ?, ?, ?)",
            (a, b, lo, hi),
        )
        conn.execute("INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)", (a, c))
        conn.commit()

        conn.execute("DELETE FROM user WHERE id=?", (a,))
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM connection").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM block").fetchone()[0] == 0

        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7. Migration 0012: entry comments + comments_seen_at watermark
# ---------------------------------------------------------------------------


def test_migration_0012_applies_and_comment_table_exists_with_expected_columns(
    tmp_path: Path,
) -> None:
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations").fetchall()}
        assert "0012_entry_comments.sql" in applied

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "comment" in tables

        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(comment)").fetchall()}
        for expected_col in ("id", "entry_id", "author_id", "body", "created_at", "deleted_at"):
            assert expected_col in cols, f"comment.{expected_col} missing"

        # NOT NULL expectations (notnull flag is column index 3).
        assert cols["entry_id"][3] == 1
        assert cols["author_id"][3] == 1
        assert cols["body"][3] == 1
        assert cols["created_at"][3] == 1
        assert cols["deleted_at"][3] == 0, "deleted_at should be nullable"

        # Index on (entry_id, created_at) for the comment-thread list query.
        index_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert "idx_comment_entry_created" in index_names
    finally:
        conn.close()


def test_migration_0012_comment_foreign_keys_cascade_on_delete(tmp_path: Path) -> None:
    """PRAGMA foreign_key_list confirms both FKs are declared ON DELETE CASCADE."""
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        fk_rows = conn.execute("PRAGMA foreign_key_list(comment)").fetchall()
        fks_by_table = {row["table"]: row for row in fk_rows}

        assert "entry" in fks_by_table
        assert fks_by_table["entry"]["on_delete"].upper() == "CASCADE"

        assert "user" in fks_by_table
        assert fks_by_table["user"]["on_delete"].upper() == "CASCADE"
    finally:
        conn.close()


def test_migration_0012_body_check_constraint_rejects_blank_comment(tmp_path: Path) -> None:
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        uid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
            (uid,),
        )
        cat_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, 'S', 'running', 0)",
            (uid, cat_id),
        )
        activity_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO entry (owner_id, activity_id, occurred_at)"
            " VALUES (?, ?, '2026-06-19T09:00:00')",
            (uid, activity_id),
        )
        entry_id = cur.lastrowid
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO comment (entry_id, author_id, body) VALUES (?, ?, ?)",
                (entry_id, uid, "   "),
            )
    finally:
        conn.close()


def test_migration_0012_deleting_author_cascades_comment(tmp_path: Path) -> None:
    """Deleting the comment's author (a different user than the entry owner)
    removes the comment via ON DELETE CASCADE on author_id."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        owner_id = cur.lastrowid
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        author_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
            (owner_id,),
        )
        cat_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, 'S', 'running', 0)",
            (owner_id, cat_id),
        )
        activity_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO entry (owner_id, activity_id, occurred_at)"
            " VALUES (?, ?, '2026-06-19T09:00:00')",
            (owner_id, activity_id),
        )
        entry_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO comment (entry_id, author_id, body) VALUES (?, ?, 'Nice work!')",
            (entry_id, author_id),
        )
        comment_id = cur.lastrowid
        conn.commit()

        # Sanity: comment exists before deletion.
        assert (
            conn.execute("SELECT COUNT(*) FROM comment WHERE id=?", (comment_id,)).fetchone()[0]
            == 1
        )

        # Delete the author (not the entry owner) -- the comment must cascade.
        conn.execute("DELETE FROM user WHERE id=?", (author_id,))
        conn.commit()

        assert (
            conn.execute("SELECT COUNT(*) FROM comment WHERE id=?", (comment_id,)).fetchone()[0]
            == 0
        )

        # The entry and its owner are untouched.
        assert conn.execute("SELECT COUNT(*) FROM entry WHERE id=?", (entry_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user WHERE id=?", (owner_id,)).fetchone()[0] == 1
    finally:
        conn.close()


def test_migration_0012_deleting_entry_owner_cascades_entry_and_comment(tmp_path: Path) -> None:
    """Deleting the entry owner cascades entry -> comment (entry_id FK), even
    when the comment's author is a different (still-existing) user."""
    db_path = fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        owner_id = cur.lastrowid
        cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        author_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
            (owner_id,),
        )
        cat_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, 'S', 'running', 0)",
            (owner_id, cat_id),
        )
        activity_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO entry (owner_id, activity_id, occurred_at)"
            " VALUES (?, ?, '2026-06-19T09:00:00')",
            (owner_id, activity_id),
        )
        entry_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO comment (entry_id, author_id, body) VALUES (?, ?, 'Nice work!')",
            (entry_id, author_id),
        )
        comment_id = cur.lastrowid
        conn.commit()

        # Delete the entry owner -- entry cascades, and the comment must
        # follow via its entry_id FK even though its author still exists.
        conn.execute("DELETE FROM user WHERE id=?", (owner_id,))
        conn.commit()

        assert conn.execute("SELECT COUNT(*) FROM entry WHERE id=?", (entry_id,)).fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM comment WHERE id=?", (comment_id,)).fetchone()[0]
            == 0
        )

        # The comment's author account is untouched.
        assert conn.execute("SELECT COUNT(*) FROM user WHERE id=?", (author_id,)).fetchone()[0] == 1

        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
    finally:
        conn.close()


def test_migration_0012_adds_comments_seen_at_column_defaulting_null(tmp_path: Path) -> None:
    """user.comments_seen_at exists and defaults to NULL, matching the
    consent_seen_at watermark pattern from 0005."""
    db_path = fresh_db(tmp_path)
    conn = raw_conn(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(user)").fetchall()}
        assert "comments_seen_at" in cols

        conn2 = sqlite3.connect(str(db_path), isolation_level=None)
        conn2.execute("PRAGMA foreign_keys=ON")
        cur = conn2.execute("INSERT INTO user (auth_provider) VALUES ('email')")
        uid = cur.lastrowid
        row = conn2.execute("SELECT comments_seen_at FROM user WHERE id=?", (uid,)).fetchone()
        assert row[0] is None
        conn2.close()
    finally:
        conn.close()
