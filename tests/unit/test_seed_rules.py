"""Tests for Task 7: seeded level_rule rows and their integration with the
progression engine.

Coverage
--------
1. Rule-count and spot-check assertions (→8단 time=10 min_age=46; →범사
   min_age=60; →달인 count=100).
2. Idempotency: re-seeding does not duplicate level_rule rows.
3. Seed → engine integration:
   a. A 4단 attained 5y ago is eligible for 5단.
   b. A 7단 attained 3y ago is NOT yet eligible for 8단 (needs 10y).
   c. Reading at 12 books is in 초급, count-to-next toward 중급(25) = 13.

Each test uses its own fresh migrated SQLite (never ``:memory:``, never the
dev DB). The progression engine is invoked against the *seeded* rules — not
hand-built fixtures.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import db as db_module
from app.models.migrate import run_migrations
from app.services import progression, seeding

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_user(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


@pytest.fixture()
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fresh DB with one seeded account. Returns (db_path, owner_id)."""
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()
    seeding.seed_account(owner_id)
    return db_path, owner_id


def _grading_sub_tally_id(conn: sqlite3.Connection, owner_id: int) -> int:
    row = conn.execute(
        """SELECT st.id
             FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE c.owner_id = ? AND c.name = '검도' AND st.name = '심사'""",
        (owner_id,),
    ).fetchone()
    assert row is not None, "심사 sub-tally not found"
    return row["id"]


def _reading_sub_tally_id(conn: sqlite3.Connection, owner_id: int) -> int:
    row = conn.execute(
        """SELECT st.id
             FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE c.owner_id = ? AND c.name = '독서'""",
        (owner_id,),
    ).fetchone()
    assert row is not None, "독서 sub-tally not found"
    return row["id"]


def _level_id(conn: sqlite3.Connection, owner_id: int, sub_tally_id: int, code: str) -> int:
    row = conn.execute(
        "SELECT id FROM level WHERE owner_id = ? AND sub_tally_id = ? AND code = ?",
        (owner_id, sub_tally_id, code),
    ).fetchone()
    assert row is not None, f"Level '{code}' not found"
    return row["id"]


def _add_level_entry(
    conn: sqlite3.Connection,
    owner_id: int,
    sub_tally_id: int,
    code: str,
    occurred_at: datetime,
) -> None:
    """Record a level-kind entry_value for the grading sub-tally."""
    # Find the level field_def for this sub-tally.
    fd = conn.execute(
        "SELECT id FROM field_def WHERE sub_tally_id = ? AND kind = 'level'",
        (sub_tally_id,),
    ).fetchone()
    assert fd is not None, "level field_def not found"
    eid = conn.execute(
        "INSERT INTO entry (owner_id, sub_tally_id, occurred_at) VALUES (?, ?, ?)",
        (owner_id, sub_tally_id, occurred_at.isoformat()),
    ).lastrowid
    conn.execute(
        "INSERT INTO entry_value (entry_id, field_def_id, text_value) VALUES (?, ?, ?)",
        (eid, fd["id"], code),
    )
    conn.commit()


def _add_plain_entry(
    conn: sqlite3.Connection,
    owner_id: int,
    sub_tally_id: int,
    occurred_at: datetime,
) -> None:
    """An entry with no recorded level value (e.g. a book read)."""
    conn.execute(
        "INSERT INTO entry (owner_id, sub_tally_id, occurred_at) VALUES (?, ?, ?)",
        (owner_id, sub_tally_id, occurred_at.isoformat()),
    )
    conn.commit()


def _track(status: dict, track: str) -> dict:
    return next(t for t in status["tracks"] if t["track"] == track)


# ---------------------------------------------------------------------------
# 1. Rule-count and spot-check assertions
# ---------------------------------------------------------------------------


def test_total_level_rule_count(seeded):
    """17 rules total: 9 dan + 4 shōgō + 4 reading."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ?", (owner_id,)
    ).fetchone()[0]
    conn.close()
    # 9 dan rules + 1 yeonsa + 2 gyosa paths + 1 beomsa = 13 kendo rules
    # 4 reading rules (chogup/junggup/gogup/dain)
    assert count == 17, f"Expected 17 level_rule rows, got {count}"


def test_kendo_grading_has_13_rules(seeded):
    """9 dan + 4 shōgō rules on the 심사 sub-tally."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    count = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ? AND sub_tally_id = ?",
        (owner_id, sid),
    ).fetchone()[0]
    conn.close()
    assert count == 13, f"Expected 13 kendo level_rules, got {count}"


def test_reading_has_4_rules(seeded):
    """4 count-gated rules on the 독서 sub-tally (입문 has no entry rule)."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _reading_sub_tally_id(conn, owner_id)
    count = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ? AND sub_tally_id = ?",
        (owner_id, sid),
    ).fetchone()[0]
    conn.close()
    assert count == 4, f"Expected 4 reading level_rules, got {count}"


def test_spot_check_8dan_rule(seeded):
    """→8단: gate_type='time', gate_value=10.0, min_age=46."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    to_id = _level_id(conn, owner_id, sid, "8dan")
    row = conn.execute(
        "SELECT gate_type, gate_value, min_age FROM level_rule"
        " WHERE owner_id = ? AND sub_tally_id = ? AND to_level_id = ?",
        (owner_id, sid, to_id),
    ).fetchone()
    conn.close()
    assert row is not None, "→8단 rule not found"
    assert row["gate_type"] == "time"
    assert row["gate_value"] == pytest.approx(10.0)
    assert row["min_age"] == 46


def test_spot_check_beomsa_rule(seeded):
    """→범사: gate_type='time', gate_value=10.0, min_age=60,
    from_level=교사, prereq=8단."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    to_id = _level_id(conn, owner_id, sid, "beomsa")
    gyosa_id = _level_id(conn, owner_id, sid, "gyosa")
    dan8_id = _level_id(conn, owner_id, sid, "8dan")
    row = conn.execute(
        "SELECT gate_type, gate_value, min_age, from_level_id, prereq_level_id"
        " FROM level_rule"
        " WHERE owner_id = ? AND sub_tally_id = ? AND to_level_id = ?",
        (owner_id, sid, to_id),
    ).fetchone()
    conn.close()
    assert row is not None, "→범사 rule not found"
    assert row["gate_type"] == "time"
    assert row["gate_value"] == pytest.approx(10.0)
    assert row["min_age"] == 60
    assert row["from_level_id"] == gyosa_id, "범사 from_level should be 교사"
    assert row["prereq_level_id"] == dan8_id, "범사 prereq should be 8단"


def test_spot_check_dain_rule(seeded):
    """→달인: gate_type='count', gate_value=100."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _reading_sub_tally_id(conn, owner_id)
    to_id = _level_id(conn, owner_id, sid, "dain")
    row = conn.execute(
        "SELECT gate_type, gate_value FROM level_rule"
        " WHERE owner_id = ? AND sub_tally_id = ? AND to_level_id = ?",
        (owner_id, sid, to_id),
    ).fetchone()
    conn.close()
    assert row is not None, "→달인 rule not found"
    assert row["gate_type"] == "count"
    assert row["gate_value"] == pytest.approx(100.0)


def test_spot_check_gyosa_has_two_paths(seeded):
    """→교사 has exactly 2 rules (OR-paths A and B)."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    to_id = _level_id(conn, owner_id, sid, "gyosa")
    rows = conn.execute(
        "SELECT prereq_level_id, gate_value FROM level_rule"
        " WHERE owner_id = ? AND sub_tally_id = ? AND to_level_id = ?"
        " ORDER BY gate_value",
        (owner_id, sid, to_id),
    ).fetchall()
    conn.close()
    assert len(rows) == 2, f"Expected 2 →교사 paths, got {len(rows)}"
    # Path B: prereq=6단, 4y; Path A: prereq=연사, 7y
    gate_values = sorted(r["gate_value"] for r in rows)
    assert gate_values == pytest.approx([4.0, 7.0])


def test_spot_check_yeonsa_rule(seeded):
    """→연사: no from_level, prereq=5단, time=3y."""
    db_path, owner_id = seeded
    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    to_id = _level_id(conn, owner_id, sid, "yeonsa")
    dan5_id = _level_id(conn, owner_id, sid, "5dan")
    row = conn.execute(
        "SELECT from_level_id, prereq_level_id, gate_value FROM level_rule"
        " WHERE owner_id = ? AND sub_tally_id = ? AND to_level_id = ?",
        (owner_id, sid, to_id),
    ).fetchone()
    conn.close()
    assert row is not None, "→연사 rule not found"
    assert row["from_level_id"] is None, "연사 rule should have no from_level"
    assert row["prereq_level_id"] == dan5_id
    assert row["gate_value"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


def test_level_rules_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-seeding the same owner does not add duplicate level_rule rows."""
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    seeding.seed_account(owner_id)
    conn = _raw(db_path)
    count_first = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ?", (owner_id,)
    ).fetchone()[0]
    conn.close()

    seeding.seed_account(owner_id)
    conn = _raw(db_path)
    count_second = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ?", (owner_id,)
    ).fetchone()[0]
    conn.close()

    assert count_first == count_second == 17, (
        f"Re-seed changed rule count: first={count_first}, second={count_second}"
    )


# ---------------------------------------------------------------------------
# 3. Seed → engine integration
# ---------------------------------------------------------------------------


def test_engine_4dan_5years_eligible_for_5dan(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """4단 attained 5y ago → eligible for 5단 (needs 4y)."""
    db_path, owner_id = seeded
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    attained_at = datetime(2019, 1, 1, tzinfo=KST)
    _add_level_entry(conn, owner_id, sid, "4dan", attained_at)
    conn.close()

    now = datetime(2024, 1, 1, tzinfo=KST)
    st = progression.status(sid, owner_id, now=now)
    dan = _track(st, "dan")
    assert dan["current_level"]["code"] == "4dan"
    assert dan["next_level"]["code"] == "5dan"
    assert dan["eligible"] is True, "4단 held 5y should be eligible for 5단 (needs 4y)"


def test_engine_7dan_3years_not_eligible_for_8dan(seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """7단 attained 3y ago → NOT eligible for 8단 (needs 10y, min_age 46)."""
    db_path, owner_id = seeded
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    sid = _grading_sub_tally_id(conn, owner_id)
    attained_at = datetime(2021, 1, 1, tzinfo=KST)
    _add_level_entry(conn, owner_id, sid, "7dan", attained_at)
    conn.close()

    now = datetime(2024, 1, 1, tzinfo=KST)
    st = progression.status(sid, owner_id, now=now)
    dan = _track(st, "dan")
    assert dan["current_level"]["code"] == "7dan"
    assert dan["next_level"]["code"] == "8dan"
    assert dan["eligible"] is False, "7단 held 3y should NOT be eligible for 8단 (needs 10y)"
    gate = dan["paths"][0]["gate"]
    assert gate["years_remaining"] == pytest.approx(7.0, abs=0.05)


def test_engine_reading_12_books_in_chogup_toward_junggup(
    seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """12 books logged: in 초급, count-to-next toward 중급(25) = 13 remaining."""
    db_path, owner_id = seeded
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    sid = _reading_sub_tally_id(conn, owner_id)

    # Record 초급 attainment (counts as 1 entry).
    _add_level_entry(conn, owner_id, sid, "chogup", datetime(2024, 1, 1, tzinfo=KST))
    # Add 11 plain entries (books) → 12 total.
    for _ in range(11):
        _add_plain_entry(conn, owner_id, sid, datetime(2024, 2, 1, tzinfo=KST))
    conn.close()

    now = datetime(2024, 6, 1, tzinfo=KST)
    st = progression.status(sid, owner_id, now=now)
    tier = _track(st, "tier")
    assert tier["current_level"]["code"] == "chogup"
    assert tier["next_level"]["code"] == "junggup"
    gate = tier["paths"][0]["gate"]
    assert gate["current_count"] == 12
    assert gate["required_count"] == 25
    assert gate["count_remaining"] == 13
    assert tier["eligible"] is False
