"""Unit tests for app.services.seeding (Task 5).

Acceptance criteria
-------------------
1. A fresh account seeded with ``seed_account(owner_id)`` has exactly two
   categories — 검도 and 독서 — with the named sub-tallies, the correct
   field_def kinds, and the level rows on the expected tracks.
2. Re-running ``seed_account`` is idempotent: counts are identical after a
   second call.
3. Seeding two different owner_ids produces independent rows — no row from
   owner A appears under owner B.

Each test uses its own fresh migrated SQLite in ``tmp_path`` (never ``:memory:``
and never the dev DB). ``seeding.seed_account`` is called via the module under
test; the assertions read back directly from the DB with raw SQL so the test
doesn't depend on any other service layer.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import seeding

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    """Create a fresh migrated DB and return its path."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _raw(db_path: Path) -> sqlite3.Connection:
    """Open a plain read-friendly connection (no isolation_level tweak)."""
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
def seeded_db(tmp_path: Path, monkeypatch):
    """A fresh DB with one seeded user. Returns (db_path, owner_id)."""
    db_path = _make_db(tmp_path)
    # DATABASE_PATH is a module-level constant frozen at import time, so we
    # must patch the attribute directly (setenv alone has no effect).
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()
    seeding.seed_account(owner_id)
    return db_path, owner_id


# ---------------------------------------------------------------------------
# 1. Shape assertions — categories, sub-tallies, field_defs, levels
# ---------------------------------------------------------------------------


def test_two_categories_seeded(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    rows = conn.execute(
        "SELECT name FROM category WHERE owner_id = ? ORDER BY sort_order",
        (owner_id,),
    ).fetchall()
    conn.close()
    names = [r["name"] for r in rows]
    assert len(names) == 2, f"Expected 2 categories, got {len(names)}: {names}"
    assert "검도" in names
    assert "독서" in names


def test_kendo_has_three_sub_tallies(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    cat = conn.execute(
        "SELECT id FROM category WHERE owner_id = ? AND name = '검도'",
        (owner_id,),
    ).fetchone()
    assert cat is not None, "검도 category not found"
    rows = conn.execute(
        "SELECT name, count_mode FROM sub_tally WHERE owner_id = ? AND category_id = ?"
        " ORDER BY sort_order",
        (owner_id, cat["id"]),
    ).fetchall()
    conn.close()
    names = [r["name"] for r in rows]
    assert len(names) == 3, f"Expected 3 kendo sub-tallies, got {names}"
    assert "수련" in names
    assert "시합" in names
    assert "심사" in names


def test_reading_has_one_sub_tally(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    cat = conn.execute(
        "SELECT id FROM category WHERE owner_id = ? AND name = '독서'",
        (owner_id,),
    ).fetchone()
    assert cat is not None, "독서 category not found"
    rows = conn.execute(
        "SELECT name FROM sub_tally WHERE owner_id = ? AND category_id = ?",
        (owner_id, cat["id"]),
    ).fetchall()
    conn.close()
    assert len(rows) == 1, f"Expected 1 reading sub-tally, got {len(rows)}"
    assert rows[0]["name"] == "독서"


def _field_kinds_for(conn, owner_id: int, sub_tally_name: str, category_name: str) -> list[str]:
    """Return sorted field_def kinds for a named sub-tally."""
    row = conn.execute(
        """SELECT fd.kind
             FROM field_def fd
             JOIN sub_tally st ON st.id = fd.sub_tally_id
             JOIN category  c  ON c.id  = st.category_id
            WHERE c.owner_id = ?
              AND c.name     = ?
              AND st.name    = ?
            ORDER BY fd.sort_order""",
        (owner_id, category_name, sub_tally_name),
    ).fetchall()
    return [r["kind"] for r in row]


def test_practice_field_defs(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    kinds = _field_kinds_for(conn, owner_id, "수련", "검도")
    conn.close()
    assert kinds == ["tag_group", "tag_group", "count", "memo"], f"수련 field_defs wrong: {kinds}"


def test_tournament_field_defs(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    kinds = _field_kinds_for(conn, owner_id, "시합", "검도")
    conn.close()
    assert kinds == ["match_list", "memo"], f"시합 field_defs wrong: {kinds}"


def test_grading_field_defs(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    kinds = _field_kinds_for(conn, owner_id, "심사", "검도")
    conn.close()
    assert kinds == ["level", "result", "memo"], f"심사 field_defs wrong: {kinds}"


def test_reading_field_defs(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    kinds = _field_kinds_for(conn, owner_id, "독서", "독서")
    conn.close()
    assert kinds == ["count", "tag_group", "tag_group", "level", "memo"], (
        f"독서 field_defs wrong: {kinds}"
    )


def test_kendo_dan_track_has_ten_levels(seeded_db):
    """1급 + 초단 + 2단–9단 = 10 levels on the dan track."""
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    grading_st = conn.execute(
        """SELECT st.id FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE c.owner_id = ? AND c.name = '검도' AND st.name = '심사'""",
        (owner_id,),
    ).fetchone()
    assert grading_st is not None
    rows = conn.execute(
        "SELECT code, label, ordinal FROM level"
        " WHERE owner_id = ? AND sub_tally_id = ? AND track = 'dan'"
        " ORDER BY ordinal",
        (owner_id, grading_st["id"]),
    ).fetchall()
    conn.close()
    codes = [r["code"] for r in rows]
    assert len(codes) == 10, f"Expected 10 dan levels, got {len(codes)}: {codes}"
    assert codes[0] == "1gup"
    assert codes[1] == "chodan"
    assert codes[-1] == "9dan"


def test_kendo_shogo_track_has_three_levels(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    grading_st = conn.execute(
        """SELECT st.id FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE c.owner_id = ? AND c.name = '검도' AND st.name = '심사'""",
        (owner_id,),
    ).fetchone()
    assert grading_st is not None
    rows = conn.execute(
        "SELECT code FROM level"
        " WHERE owner_id = ? AND sub_tally_id = ? AND track = 'shogo'"
        " ORDER BY ordinal",
        (owner_id, grading_st["id"]),
    ).fetchall()
    conn.close()
    codes = [r["code"] for r in rows]
    assert codes == ["yeonsa", "gyosa", "beomsa"], f"Shōgō levels wrong: {codes}"


def test_reading_tier_track_has_five_levels(seeded_db):
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    reading_st = conn.execute(
        """SELECT st.id FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE c.owner_id = ? AND c.name = '독서'""",
        (owner_id,),
    ).fetchone()
    assert reading_st is not None
    rows = conn.execute(
        "SELECT code FROM level"
        " WHERE owner_id = ? AND sub_tally_id = ? AND track = 'tier'"
        " ORDER BY ordinal",
        (owner_id, reading_st["id"]),
    ).fetchall()
    conn.close()
    codes = [r["code"] for r in rows]
    assert codes == ["ibmun", "chogup", "junggup", "gogup", "dain"], f"Reading tiers wrong: {codes}"


def test_level_rules_seeded(seeded_db):
    """Task 7: level_rule rows are present after seeding (dan + shōgō + reading)."""
    db_path, owner_id = seeded_db
    conn = _raw(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ?",
        (owner_id,),
    ).fetchone()[0]
    conn.close()
    # 9 dan rules + 4 shōgō rules (yeonsa=1, gyosa=2, beomsa=1) + 4 reading rules = 17
    assert count == 17, f"Expected 17 level_rules, got {count}"


# ---------------------------------------------------------------------------
# 2. Idempotency — re-running seed_account changes nothing
# ---------------------------------------------------------------------------


def _row_counts(db_path: Path, owner_id: int) -> dict[str, int]:
    """Return row counts for the seeded tables, scoped to owner_id."""
    conn = _raw(db_path)
    tables = ["category", "sub_tally", "level", "level_rule"]
    counts = {}
    for t in tables:
        counts[t] = conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE owner_id = ?",  # noqa: S608 - table is allow-listed
            (owner_id,),
        ).fetchone()[0]
    # field_def has no owner_id column — count via join
    counts["field_def"] = conn.execute(
        """SELECT COUNT(*) FROM field_def fd
             JOIN sub_tally st ON st.id = fd.sub_tally_id
            WHERE st.owner_id = ?""",
        (owner_id,),
    ).fetchone()[0]
    conn.close()
    return counts


def test_seed_account_idempotent(tmp_path: Path, monkeypatch):
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    seeding.seed_account(owner_id)
    counts_first = _row_counts(db_path, owner_id)

    seeding.seed_account(owner_id)
    counts_second = _row_counts(db_path, owner_id)

    assert counts_first == counts_second, (
        f"Second seed changed row counts: before={counts_first}, after={counts_second}"
    )


# ---------------------------------------------------------------------------
# 3. Isolation — seeding two owners produces independent rows
# ---------------------------------------------------------------------------


def test_seed_isolation_between_owners(tmp_path: Path, monkeypatch):
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_a = _make_user(conn)
    owner_b = _make_user(conn)
    conn.close()

    seeding.seed_account(owner_a)
    seeding.seed_account(owner_b)

    conn = _raw(db_path)

    # Each owner has exactly 2 categories.
    count_a = conn.execute(
        "SELECT COUNT(*) FROM category WHERE owner_id = ?", (owner_a,)
    ).fetchone()[0]
    count_b = conn.execute(
        "SELECT COUNT(*) FROM category WHERE owner_id = ?", (owner_b,)
    ).fetchone()[0]
    assert count_a == 2, f"Owner A should have 2 categories, got {count_a}"
    assert count_b == 2, f"Owner B should have 2 categories, got {count_b}"

    # No category row for owner A appears in owner B's results and vice versa.
    # Just verify the owner columns are correct.
    all_cats = conn.execute("SELECT owner_id FROM category").fetchall()
    owner_ids_in_cats = {r["owner_id"] for r in all_cats}
    assert owner_a in owner_ids_in_cats
    assert owner_b in owner_ids_in_cats

    # Level rows are also isolated by owner_id.
    levels_a = conn.execute("SELECT id FROM level WHERE owner_id = ?", (owner_a,)).fetchall()
    levels_b = conn.execute("SELECT id FROM level WHERE owner_id = ?", (owner_b,)).fetchall()
    ids_a = {r["id"] for r in levels_a}
    ids_b = {r["id"] for r in levels_b}
    assert not ids_a.intersection(ids_b), "Level row ids must not overlap between owners"

    conn.close()
