"""Unit tests for app.routes.web._history_context._build_card_top_tags.

Acceptance criteria covered
----------------------------
1. Returns ``None`` when *field_defs* has zero ``tag_group`` rows (the
   activity has no tags at all — distinct from "has tags but none logged").
2. When multiple ``tag_group`` fields exist, picks the one with the lowest
   ``sort_order`` (tiebreak: lowest ``id``) — not list order.
3. Returns ``{"label": ..., "tags": []}`` (not ``None``) when the chosen
   field exists but has zero tagged entries.
4. ``tags`` is capped at *top* (default 3) and sorted by lifetime total
   descending (delegated to ``stats.tag_frequency``, confirmed not re-sorted).

Fixture style follows ``tests/unit/test_stats.py``: a fresh migrated temp
SQLite per test, seeded directly via raw inserts (no need to go through
``app.services.categories`` since these tests want precise control over
field_def ``sort_order``/``id`` ordering).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.routes.web._history_context import _build_card_top_tags
from app.services import entries

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point the service layer's connect() at it."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    return db_path


def _seed_user(db_path: Path, name: str = "U") -> int:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO user (auth_provider, display_name) VALUES ('email', ?)",
            (name,),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _seed_bare_activity(db_path: Path, owner_id: int, *, name: str = "Practice") -> int:
    """Category + activity, no field_defs at all."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Cat', 0)",
            (owner_id,),
        )
        category_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, 'running', 0)",
            (owner_id, category_id, name),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _add_field_def(
    db_path: Path, activity_id: int, *, kind: str, label: str, sort_order: int
) -> int:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order) VALUES (?, ?, ?, ?)",
            (activity_id, kind, label, sort_order),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _add_tag(db_path: Path, owner_id: int, field_def_id: int, *, name: str, sort_order: int) -> int:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order) VALUES (?, ?, ?, ?)",
            (owner_id, field_def_id, name, sort_order),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _field_defs_for(db_path: Path, activity_id: int) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM field_def WHERE activity_id = ? ORDER BY sort_order, id",
            (activity_id,),
        ).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# No tag_group field at all -> None
# ---------------------------------------------------------------------------


def test_returns_none_when_no_tag_group_field(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)
    _add_field_def(test_db, activity_id, kind="memo", label="Notes", sort_order=0)
    _add_field_def(test_db, activity_id, kind="scale", label="Mood", sort_order=1)

    field_defs = _field_defs_for(test_db, activity_id)
    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST)
    assert result is None


def test_returns_none_when_field_defs_empty(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)

    result = _build_card_top_tags(activity_id, owner, [], tz=KST)
    assert result is None


# ---------------------------------------------------------------------------
# Tag-group field exists but nothing logged yet -> {"label", "tags": []}
# ---------------------------------------------------------------------------


def test_returns_empty_tags_when_field_exists_but_unused(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)
    _add_field_def(test_db, activity_id, kind="tag_group", label="Tags", sort_order=0)

    field_defs = _field_defs_for(test_db, activity_id)
    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST)

    assert result is not None
    assert result == {"label": "Tags", "tags": []}


# ---------------------------------------------------------------------------
# Multiple tag_group fields -> pick lowest sort_order, tiebreak lowest id
# ---------------------------------------------------------------------------


def test_picks_lowest_sort_order_field_not_list_order(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)

    # Insert the higher-sort_order field FIRST so its id is lower — proves the
    # selection isn't accidentally just "first in list" or "lowest id" alone.
    second_field = _add_field_def(
        test_db, activity_id, kind="tag_group", label="Locations", sort_order=1
    )
    first_field = _add_field_def(
        test_db, activity_id, kind="tag_group", label="Techniques", sort_order=0
    )

    tech_tag = _add_tag(test_db, owner, first_field, name="kata", sort_order=0)
    _add_tag(test_db, owner, second_field, name="dojo", sort_order=0)

    entries.create(
        owner, activity_id, {"tags": [tech_tag]}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST
    )

    # Pass field_defs sorted by id ascending (second_field has the lower id,
    # since it was inserted first) so it's list-order[0] — proves the
    # selection isn't accidentally just "first in the passed-in list".
    field_defs = sorted(_field_defs_for(test_db, activity_id), key=lambda r: r["id"])
    assert field_defs[0]["id"] == second_field  # confirm list-order trap is set

    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST)

    assert result is not None
    assert result["label"] == "Techniques"  # the lowest sort_order field, not list-order[0]
    assert [t["name"] for t in result["tags"]] == ["kata"]


def test_tiebreaks_equal_sort_order_on_lowest_id(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)

    first_field = _add_field_def(
        test_db, activity_id, kind="tag_group", label="First", sort_order=0
    )
    second_field = _add_field_def(
        test_db, activity_id, kind="tag_group", label="Second", sort_order=0
    )
    assert first_field < second_field

    field_defs = _field_defs_for(test_db, activity_id)
    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST)

    assert result is not None
    assert result["label"] == "First"


# ---------------------------------------------------------------------------
# tags capped at top, sorted by lifetime total descending (delegated, but
# confirm it isn't re-sorted incorrectly by this helper)
# ---------------------------------------------------------------------------


def test_tags_capped_at_top_and_sorted_desc(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)
    fid = _add_field_def(test_db, activity_id, kind="tag_group", label="Tags", sort_order=0)

    tag_a = _add_tag(test_db, owner, fid, name="a", sort_order=0)
    tag_b = _add_tag(test_db, owner, fid, name="b", sort_order=1)
    tag_c = _add_tag(test_db, owner, fid, name="c", sort_order=2)
    tag_d = _add_tag(test_db, owner, fid, name="d", sort_order=3)

    # Lifetime totals: a=4, b=3, c=2, d=1.
    for tag_id, count in ((tag_a, 4), (tag_b, 3), (tag_c, 2), (tag_d, 1)):
        for i in range(count):
            entries.create(
                owner,
                activity_id,
                {"tags": [tag_id]},
                occurred_at=f"2026-0{i % 6 + 1}-0{tag_id % 5 + 1}T10:00:00+09:00",
                tz=KST,
            )

    field_defs = _field_defs_for(test_db, activity_id)
    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST, top=3)

    assert result is not None
    assert len(result["tags"]) == 3
    assert [t["name"] for t in result["tags"]] == ["a", "b", "c"]


def test_default_top_is_three(test_db: Path) -> None:
    owner = _seed_user(test_db)
    activity_id = _seed_bare_activity(test_db, owner)
    fid = _add_field_def(test_db, activity_id, kind="tag_group", label="Tags", sort_order=0)

    tag_ids = [_add_tag(test_db, owner, fid, name=f"t{i}", sort_order=i) for i in range(5)]
    for idx, tag_id in enumerate(tag_ids):
        # Descending counts so order is deterministic: t0 has most entries.
        for i in range(5 - idx):
            entries.create(
                owner,
                activity_id,
                {"tags": [tag_id]},
                occurred_at=f"2026-01-{i + 1:02d}T1{idx}:00:00+09:00",
                tz=KST,
            )

    field_defs = _field_defs_for(test_db, activity_id)
    result = _build_card_top_tags(activity_id, owner, field_defs, tz=KST)

    assert result is not None
    assert len(result["tags"]) == 3
    assert [t["name"] for t in result["tags"]] == ["t0", "t1", "t2"]
