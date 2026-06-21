"""Unit tests for app.services.categories (Task 2).

Acceptance criteria
-------------------
1. ``create_activity(owner_id, ...)`` is ``owner_id``-scoped and produces a
   category + activity + 2 field_defs (memo, tag_group) in one transaction.
2. The activity is the general-log shape: ``count_mode="running"`` with cache
   fields at their defaults; the two field_defs are exactly ``memo`` and
   ``tag_group``.
3. Invalid/unknown ``icon`` values fall back to ``circle-dot``, never erroring.
4. ``ICON_CHOICES`` and ``EXAMPLE_CATEGORIES`` are plain importable constants.
5. Two different owners get independent categories (multi-user isolation).

Each test uses its own fresh migrated SQLite in ``tmp_path`` (never ``:memory:``
and never the dev DB). Assertions read back directly from the DB with raw SQL so
the test doesn't depend on any other service layer.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import categories
from app.services.entries import SubTallyNotFoundError

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    """Create a fresh migrated DB and return its path."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _raw(db_path: Path) -> sqlite3.Connection:
    """Open a plain read-friendly connection."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_user(conn: sqlite3.Connection) -> int:
    """Insert a minimal user row and return its id."""
    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    conn.commit()
    return cur.lastrowid


@pytest.fixture()
def db_with_user(tmp_path: Path, monkeypatch):
    """A fresh DB with one user. Returns (db_path, owner_id)."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()
    return db_path, owner_id


def _field_kinds(conn: sqlite3.Connection, activity_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT kind FROM field_def WHERE activity_id = ? ORDER BY sort_order",
        (activity_id,),
    ).fetchall()
    return [r["kind"] for r in rows]


# ---------------------------------------------------------------------------
# 1. Importable constants
# ---------------------------------------------------------------------------


def test_icon_choices_is_importable_constant():
    assert isinstance(categories.ICON_CHOICES, tuple)
    assert "dumbbell" in categories.ICON_CHOICES
    assert "book-open" in categories.ICON_CHOICES
    assert "circle-check" in categories.ICON_CHOICES
    # circle-dot is the default fallback and must be selectable.
    assert "circle-dot" in categories.ICON_CHOICES
    assert categories.DEFAULT_ICON == "circle-dot"


def test_example_categories_shape():
    assert categories.EXAMPLE_CATEGORIES == [
        {"name": "Workout", "icon": "dumbbell"},
        {"name": "Reading", "icon": "book-open"},
        {"name": "Habits", "icon": "circle-check"},
    ]
    # Every example icon is a valid choice.
    for ex in categories.EXAMPLE_CATEGORIES:
        assert ex["icon"] in categories.ICON_CHOICES


# ---------------------------------------------------------------------------
# 2. General-log shape — category + activity + 2 field_defs in one txn
# ---------------------------------------------------------------------------


def test_create_activity_returns_ids(db_with_user):
    _, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Workout", icon="dumbbell")
    assert set(result) == {"category_id", "activity_id"}
    assert isinstance(result["category_id"], int)
    assert isinstance(result["activity_id"], int)


def test_create_activity_inserts_category_row(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Workout", icon="dumbbell")
    conn = _raw(db_path)
    row = conn.execute(
        "SELECT owner_id, name, icon FROM category WHERE id = ?",
        (result["category_id"],),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["owner_id"] == owner_id
    assert row["name"] == "Workout"
    assert row["icon"] == "dumbbell"


def test_create_activity_running_activity(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Workout")
    conn = _raw(db_path)
    row = conn.execute(
        "SELECT owner_id, category_id, count_mode, cached_count, cached_streak, last_entry_at"
        " FROM activity WHERE id = ?",
        (result["activity_id"],),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["owner_id"] == owner_id
    assert row["category_id"] == result["category_id"]
    assert row["count_mode"] == "running"
    # Cache fields at their DB defaults — no entries yet.
    assert row["cached_count"] == 0
    assert row["cached_streak"] == 0
    assert row["last_entry_at"] is None


def test_create_activity_has_memo_and_tag_group_field_defs(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Workout")
    conn = _raw(db_path)
    kinds = _field_kinds(conn, result["activity_id"])
    conn.close()
    assert kinds == ["memo", "tag_group"], f"general-log field_defs wrong: {kinds}"


def test_create_activity_sets_slug(db_with_user):
    """The new activity gets a slug derived from its name."""
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Morning Workout")
    conn = _raw(db_path)
    slug = conn.execute(
        "SELECT slug FROM activity WHERE id = ?", (result["activity_id"],)
    ).fetchone()["slug"]
    conn.close()
    assert slug == "morning-workout"


def test_create_activity_slug_unique_per_owner(db_with_user):
    """Two sub-tallies with the same name under one owner get name and name-2."""
    db_path, owner_id = db_with_user
    first = categories.create_activity(owner_id, name="Workout")
    second = categories.create_activity(owner_id, name="Workout")
    conn = _raw(db_path)
    slug_first = conn.execute(
        "SELECT slug FROM activity WHERE id = ?", (first["activity_id"],)
    ).fetchone()["slug"]
    slug_second = conn.execute(
        "SELECT slug FROM activity WHERE id = ?", (second["activity_id"],)
    ).fetchone()["slug"]
    conn.close()
    assert slug_first == "workout"
    assert slug_second == "workout-2"


def test_create_activity_no_levels_or_rules(db_with_user):
    """General-log categories have no progression rows."""
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Workout")
    conn = _raw(db_path)
    levels = conn.execute(
        "SELECT COUNT(*) FROM level WHERE activity_id = ?",
        (result["activity_id"],),
    ).fetchone()[0]
    rules = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE activity_id = ?",
        (result["activity_id"],),
    ).fetchone()[0]
    conn.close()
    assert levels == 0
    assert rules == 0


def test_create_activity_is_atomic(db_with_user):
    """Exactly one category, one activity, two field_defs — nothing partial."""
    db_path, owner_id = db_with_user
    categories.create_activity(owner_id, name="Workout")
    conn = _raw(db_path)
    cat_count = conn.execute(
        "SELECT COUNT(*) FROM category WHERE owner_id = ?", (owner_id,)
    ).fetchone()[0]
    st_count = conn.execute(
        "SELECT COUNT(*) FROM activity WHERE owner_id = ?", (owner_id,)
    ).fetchone()[0]
    fd_count = conn.execute(
        """SELECT COUNT(*) FROM field_def fd
             JOIN activity st ON st.id = fd.activity_id
            WHERE st.owner_id = ?""",
        (owner_id,),
    ).fetchone()[0]
    conn.close()
    assert cat_count == 1
    assert st_count == 1
    assert fd_count == 2


# ---------------------------------------------------------------------------
# 3. Icon fallback — unknown/None icon becomes circle-dot, never errors
# ---------------------------------------------------------------------------


def test_create_activity_invalid_icon_falls_back(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Mystery", icon="not-a-real-icon")
    conn = _raw(db_path)
    icon = conn.execute(
        "SELECT icon FROM category WHERE id = ?", (result["category_id"],)
    ).fetchone()["icon"]
    conn.close()
    assert icon == "circle-dot"


def test_create_activity_none_icon_falls_back(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Plain")
    conn = _raw(db_path)
    icon = conn.execute(
        "SELECT icon FROM category WHERE id = ?", (result["category_id"],)
    ).fetchone()["icon"]
    conn.close()
    assert icon == "circle-dot"


def test_create_activity_valid_icon_preserved(db_with_user):
    db_path, owner_id = db_with_user
    result = categories.create_activity(owner_id, name="Read", icon="book-open")
    conn = _raw(db_path)
    icon = conn.execute(
        "SELECT icon FROM category WHERE id = ?", (result["category_id"],)
    ).fetchone()["icon"]
    conn.close()
    assert icon == "book-open"


# ---------------------------------------------------------------------------
# 4. Multi-user isolation — two owners get independent categories
# ---------------------------------------------------------------------------


def test_create_activity_owner_isolation(tmp_path: Path, monkeypatch):
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_a = _make_user(conn)
    owner_b = _make_user(conn)
    conn.close()

    res_a = categories.create_activity(owner_a, name="A-cat", icon="dumbbell")
    res_b = categories.create_activity(owner_b, name="B-cat", icon="music")

    conn = _raw(db_path)

    # Each owner sees exactly their own category.
    cats_a = conn.execute("SELECT id, name FROM category WHERE owner_id = ?", (owner_a,)).fetchall()
    cats_b = conn.execute("SELECT id, name FROM category WHERE owner_id = ?", (owner_b,)).fetchall()
    assert [r["name"] for r in cats_a] == ["A-cat"]
    assert [r["name"] for r in cats_b] == ["B-cat"]

    # Category ids don't cross owners.
    assert res_a["category_id"] != res_b["category_id"]
    assert {r["id"] for r in cats_a}.isdisjoint({r["id"] for r in cats_b})

    # Sub-tallies are likewise owner-scoped.
    st_a = conn.execute(
        "SELECT owner_id FROM activity WHERE id = ?", (res_a["activity_id"],)
    ).fetchone()
    st_b = conn.execute(
        "SELECT owner_id FROM activity WHERE id = ?", (res_b["activity_id"],)
    ).fetchone()
    conn.close()
    assert st_a["owner_id"] == owner_a
    assert st_b["owner_id"] == owner_b


# ---------------------------------------------------------------------------
# 5. rename_activity — updates name + slug atomically, owner-scoped
# ---------------------------------------------------------------------------


def _activity_row(db_path: Path, activity_id: int) -> sqlite3.Row:
    conn = _raw(db_path)
    row = conn.execute("SELECT name, slug FROM activity WHERE id = ?", (activity_id,)).fetchone()
    conn.close()
    return row


def test_rename_activity_updates_name_and_slug(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    activity_id = created["activity_id"]

    conn = _raw(db_path)
    new_slug = categories.rename_activity(
        conn, owner_id=owner_id, activity_id=activity_id, new_name="Morning Workout"
    )
    conn.commit()
    conn.close()

    assert new_slug == "morning-workout"
    row = _activity_row(db_path, activity_id)
    assert row["name"] == "Morning Workout"
    assert row["slug"] == "morning-workout"


def test_rename_activity_trims_whitespace(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    activity_id = created["activity_id"]

    conn = _raw(db_path)
    new_slug = categories.rename_activity(
        conn, owner_id=owner_id, activity_id=activity_id, new_name="  Evening Run  "
    )
    conn.commit()
    conn.close()

    assert new_slug == "evening-run"
    row = _activity_row(db_path, activity_id)
    assert row["name"] == "Evening Run"
    assert row["slug"] == "evening-run"


def test_rename_activity_empty_name_raises(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    activity_id = created["activity_id"]

    conn = _raw(db_path)
    try:
        with pytest.raises(ValueError):
            categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name=""
            )
        with pytest.raises(ValueError):
            categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name="   "
            )
    finally:
        conn.close()

    # Name unchanged after the rejected renames.
    row = _activity_row(db_path, activity_id)
    assert row["name"] == "Workout"


def test_rename_activity_too_long_name_raises(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    activity_id = created["activity_id"]

    over = "x" * (categories.RENAME_SUB_TALLY_MAX_NAME + 1)
    at_cap = "y" * categories.RENAME_SUB_TALLY_MAX_NAME

    conn = _raw(db_path)
    try:
        with pytest.raises(ValueError):
            categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name=over
            )
        # Exactly at the cap is accepted.
        slug = categories.rename_activity(
            conn, owner_id=owner_id, activity_id=activity_id, new_name=at_cap
        )
        conn.commit()
    finally:
        conn.close()

    assert slug  # non-empty slug returned
    row = _activity_row(db_path, activity_id)
    assert row["name"] == at_cap


def test_rename_activity_not_owned_raises(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    activity_id = created["activity_id"]

    # A different owner must not be able to rename this sub-tally.
    conn = _raw(db_path)
    other_owner = _make_user(conn)
    try:
        with pytest.raises(SubTallyNotFoundError):
            categories.rename_activity(
                conn, owner_id=other_owner, activity_id=activity_id, new_name="Hijack"
            )
    finally:
        conn.close()

    # Original row untouched.
    row = _activity_row(db_path, activity_id)
    assert row["name"] == "Workout"
    assert row["slug"] == "workout"


def test_rename_activity_missing_id_raises(db_with_user):
    db_path, owner_id = db_with_user
    conn = _raw(db_path)
    try:
        with pytest.raises(SubTallyNotFoundError):
            categories.rename_activity(
                conn, owner_id=owner_id, activity_id=999_999, new_name="Nope"
            )
    finally:
        conn.close()


def test_rename_activity_slug_collision_gets_suffix(db_with_user):
    db_path, owner_id = db_with_user
    # Two sub-tallies; rename the second to collide with the first's slug.
    first = categories.create_activity(owner_id, name="Running")
    second = categories.create_activity(owner_id, name="Lifting")

    conn = _raw(db_path)
    new_slug = categories.rename_activity(
        conn, owner_id=owner_id, activity_id=second["activity_id"], new_name="Running"
    )
    conn.commit()
    conn.close()

    assert new_slug == "running-2"
    row = _activity_row(db_path, second["activity_id"])
    assert row["name"] == "Running"
    assert row["slug"] == "running-2"
    # First sub-tally keeps the unsuffixed slug.
    first_row = _activity_row(db_path, first["activity_id"])
    assert first_row["slug"] == "running"


def test_rename_activity_owner_isolation_for_slug(db_with_user):
    """A slug collision is only checked within the renaming owner's rows."""
    db_path, owner_a = db_with_user
    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    # owner_b has a sub-tally that slugifies to "running".
    categories.create_activity(owner_b, name="Running")
    a_st = categories.create_activity(owner_a, name="Lifting")

    conn = _raw(db_path)
    new_slug = categories.rename_activity(
        conn, owner_id=owner_a, activity_id=a_st["activity_id"], new_name="Running"
    )
    conn.commit()
    conn.close()

    # owner_b's identical slug does not force a suffix for owner_a.
    assert new_slug == "running"


# ---------------------------------------------------------------------------
# 6. delete_category — owner-scoped, cascades the whole subtree
# ---------------------------------------------------------------------------


def _insert_entry(conn: sqlite3.Connection, owner_id: int, activity_id: int) -> int:
    """Insert a minimal entry row and return its id."""
    cur = conn.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at) VALUES (?, ?, ?)",
        (owner_id, activity_id, "2026-06-16T00:00:00Z"),
    )
    conn.commit()
    return cur.lastrowid


def _count(conn: sqlite3.Connection, table: str, column: str, value: int) -> int:
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",  # noqa: S608 - literals only
        (value,),
    ).fetchone()[0]


def test_delete_category_removes_row_and_cascades(db_with_user):
    db_path, owner_id = db_with_user
    created = categories.create_activity(owner_id, name="Workout")
    category_id = created["category_id"]
    activity_id = created["activity_id"]

    # Give the sub-tally at least one entry so we can prove the cascade.
    conn = _raw(db_path)
    _insert_entry(conn, owner_id, activity_id)
    assert _count(conn, "entry", "activity_id", activity_id) == 1
    conn.close()

    conn = _raw(db_path)
    try:
        deleted = categories.delete_category(conn, owner_id=owner_id, category_id=category_id)
        conn.commit()
    finally:
        conn.close()

    assert deleted is True
    conn = _raw(db_path)
    assert _count(conn, "category", "id", category_id) == 0
    assert _count(conn, "activity", "category_id", category_id) == 0
    assert _count(conn, "entry", "activity_id", activity_id) == 0
    conn.close()


def test_delete_category_wrong_owner_no_op(db_with_user):
    db_path, owner_a = db_with_user
    created = categories.create_activity(owner_a, name="Workout")
    category_id = created["category_id"]
    activity_id = created["activity_id"]

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    conn = _raw(db_path)
    try:
        deleted = categories.delete_category(conn, owner_id=owner_b, category_id=category_id)
        conn.commit()
    finally:
        conn.close()

    assert deleted is False
    # Nothing of owner_a's was touched.
    conn = _raw(db_path)
    assert _count(conn, "category", "id", category_id) == 1
    assert _count(conn, "activity", "category_id", category_id) == 1
    conn.close()
    # activity still belongs to owner_a.
    row = _activity_row(db_path, activity_id)
    assert row is not None


def test_delete_category_missing_id_no_op(db_with_user):
    db_path, owner_id = db_with_user
    conn = _raw(db_path)
    try:
        deleted = categories.delete_category(conn, owner_id=owner_id, category_id=999_999)
        conn.commit()
    finally:
        conn.close()
    assert deleted is False
