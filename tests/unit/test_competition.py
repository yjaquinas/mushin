"""Tests for the competition service (Task 8: match-list persistence + W/L/D stats).

Acceptance criteria covered
---------------------------
1. A tournament entry records multiple match rows; they persist and are scoped to
   ``owner_id`` (user A cannot add to or read user B's entry's matches).
2. W/L/D record + win_rate compute correctly against a hand-built fixture (incl.
   draws); the results timeline is chronological; head-to-head groups by opponent
   and aggregates the same opponent across different tournament entries.

Each test runs against its own freshly-migrated temp SQLite file; ``DATABASE_PATH``
is pointed at it so the service's ``db.connect()`` uses the test DB (never the dev
DB). Pattern mirrors tests/unit/test_entries.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.services import competition, entries

# These fixtures use +09:00 timestamps; pass the matching zone explicitly so the
# (cache-only) tz parameter on entries.create is satisfied. Competition stats
# themselves don't bucket by calendar day, so the zone choice is immaterial here.
KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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


def _seed_tournament(db_path: Path, owner_id: int, name: str = "Tournament") -> int:
    """A category + activity carrying a match_list field_def. Returns activity_id."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Kendo', 0)",
            (owner_id,),
        )
        category_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, 'running', 0)",
            (owner_id, category_id, name),
        )
        activity_id = cur.lastrowid
        conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'match_list', 'Bouts', 0)",
            (activity_id,),
        )
        return activity_id
    finally:
        conn.close()


def _make_entry(owner_id: int, activity_id: int, occurred_at: str) -> int:
    """Create a tournament entry via the entries service; return its id."""
    return entries.create(owner_id, activity_id, occurred_at=occurred_at, tz=KST)["id"]


# ---------------------------------------------------------------------------
# 1. Persistence + ownership scoping
# ---------------------------------------------------------------------------


def test_entry_records_multiple_matches_in_order(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    entry = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")

    competition.add_matches(
        owner,
        entry,
        [
            {"opponent": "Kim", "score": "2-0", "result": "win"},
            {"opponent": "Lee", "score": "1-2", "result": "loss"},
            {"opponent": "Park", "score": "1-1", "result": "draw"},
        ],
    )

    rows = competition.list_matches(owner, entry)
    assert [r["opponent"] for r in rows] == ["Kim", "Lee", "Park"]
    assert [r["result"] for r in rows] == ["win", "loss", "draw"]
    assert all(r["owner_id"] == owner for r in rows)
    # sort_order defaulted to input position.
    assert [r["sort_order"] for r in rows] == [0, 1, 2]


def test_add_matches_appends_and_respects_explicit_sort_order(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    entry = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")

    competition.add_matches(owner, entry, [{"opponent": "A", "score": "1-0", "result": "win"}])
    competition.add_matches(
        owner,
        entry,
        [{"opponent": "B", "score": "0-1", "result": "loss", "sort_order": 5}],
    )

    rows = competition.list_matches(owner, entry)
    assert [r["opponent"] for r in rows] == ["A", "B"]


def test_add_matches_rejects_bad_result(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    entry = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")

    with pytest.raises(competition.MatchPayloadError):
        competition.add_matches(owner, entry, [{"opponent": "X", "score": "1-0", "result": "bye"}])
    # nothing persisted on the failed call.
    assert competition.list_matches(owner, entry) == []


def test_replace_matches_swaps_the_set(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    entry = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")

    competition.add_matches(owner, entry, [{"opponent": "Old", "score": "2-0", "result": "win"}])
    competition.replace_matches(
        owner,
        entry,
        [
            {"opponent": "New1", "score": "1-2", "result": "loss"},
            {"opponent": "New2", "score": "1-1", "result": "draw"},
        ],
    )

    rows = competition.list_matches(owner, entry)
    assert [r["opponent"] for r in rows] == ["New1", "New2"]


def test_delete_matches_removes_all_for_entry(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    entry = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")

    competition.add_matches(
        owner,
        entry,
        [
            {"opponent": "A", "score": "1-0", "result": "win"},
            {"opponent": "B", "score": "0-1", "result": "loss"},
        ],
    )
    removed = competition.delete_matches(owner, entry)
    assert removed == 2
    assert competition.list_matches(owner, entry) == []


def test_user_a_cannot_add_to_user_b_entry(test_db: Path) -> None:
    a = _seed_user(test_db, "A")
    b = _seed_user(test_db, "B")
    sub_b = _seed_tournament(test_db, b)
    entry_b = _make_entry(b, sub_b, "2026-05-01T10:00:00+09:00")

    with pytest.raises(competition.EntryNotFoundError):
        competition.add_matches(a, entry_b, [{"opponent": "X", "score": "1-0", "result": "win"}])

    # B's entry is untouched.
    assert competition.list_matches(b, entry_b) == []


def test_user_a_cannot_read_user_b_matches(test_db: Path) -> None:
    a = _seed_user(test_db, "A")
    b = _seed_user(test_db, "B")
    sub_b = _seed_tournament(test_db, b)
    entry_b = _make_entry(b, sub_b, "2026-05-01T10:00:00+09:00")
    competition.add_matches(b, entry_b, [{"opponent": "X", "score": "1-0", "result": "win"}])

    with pytest.raises(competition.EntryNotFoundError):
        competition.list_matches(a, entry_b)


def test_stats_never_count_another_owners_matches(test_db: Path) -> None:
    """Same activity id existing for two owners must not bleed across the join."""
    a = _seed_user(test_db, "A")
    b = _seed_user(test_db, "B")
    sub_a = _seed_tournament(test_db, a)
    sub_b = _seed_tournament(test_db, b)

    entry_a = _make_entry(a, sub_a, "2026-05-01T10:00:00+09:00")
    entry_b = _make_entry(b, sub_b, "2026-05-01T10:00:00+09:00")
    competition.add_matches(a, entry_a, [{"opponent": "Kim", "score": "2-0", "result": "win"}])
    competition.add_matches(
        b,
        entry_b,
        [
            {"opponent": "Kim", "score": "0-2", "result": "loss"},
            {"opponent": "Kim", "score": "0-2", "result": "loss"},
        ],
    )

    rec_a = competition.record(a, sub_a)
    rec_b = competition.record(b, sub_b)
    assert (rec_a["wins"], rec_a["losses"], rec_a["draws"]) == (1, 0, 0)
    assert (rec_b["wins"], rec_b["losses"], rec_b["draws"]) == (0, 2, 0)

    # A querying B's activity id sees nothing (owner scope on both join sides).
    cross = competition.record(a, sub_b)
    assert (cross["wins"], cross["losses"], cross["draws"], cross["total"]) == (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# 2. Stats: record / win_rate / timeline / head-to-head
# ---------------------------------------------------------------------------


def _seed_fixture(db_path: Path, owner: int, sub: int) -> None:
    """Two tournament entries with a known W/L/D spread across opponents.

    Entry 1 (May): win vs Kim, loss vs Lee, draw vs Park.
    Entry 2 (June): win vs Kim, win vs Lee, draw vs Park.
    Totals: 3 wins, 1 loss, 2 draws -> 6 bouts, decided=6, win_rate=0.5.
    """
    e1 = _make_entry(owner, sub, "2026-05-01T10:00:00+09:00")
    e2 = _make_entry(owner, sub, "2026-06-01T10:00:00+09:00")
    competition.add_matches(
        owner,
        e1,
        [
            {"opponent": "Kim", "score": "2-0", "result": "win"},
            {"opponent": "Lee", "score": "1-2", "result": "loss"},
            {"opponent": "Park", "score": "1-1", "result": "draw"},
        ],
    )
    competition.add_matches(
        owner,
        e2,
        [
            {"opponent": "Kim", "score": "2-1", "result": "win"},
            {"opponent": "Lee", "score": "2-0", "result": "win"},
            {"opponent": "Park", "score": "0-0", "result": "draw"},
        ],
    )


def test_record_and_win_rate_include_draws_in_denominator(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    _seed_fixture(test_db, owner, sub)

    rec = competition.record(owner, sub)
    assert rec["wins"] == 3
    assert rec["losses"] == 1
    assert rec["draws"] == 2
    assert rec["total"] == 6
    assert rec["decided"] == 6
    # 3 / (3 + 1 + 2) = 0.5 — draws count in the denominator.
    assert rec["win_rate"] == pytest.approx(0.5)


def test_win_rate_is_none_with_no_matches(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)

    rec = competition.record(owner, sub)
    assert rec == {
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "total": 0,
        "decided": 0,
        "win_rate": None,
    }


def test_results_timeline_is_chronological(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    _seed_fixture(test_db, owner, sub)

    timeline = competition.results_timeline(owner, sub)
    assert len(timeline) == 6
    # Oldest entry (May) bouts come first, in sort_order, then June.
    assert [t["occurred_at"] for t in timeline] == sorted(t["occurred_at"] for t in timeline)
    assert timeline[0]["occurred_at"].startswith("2026-05-01")
    assert timeline[-1]["occurred_at"].startswith("2026-06-01")
    # Within May, order preserved by sort_order.
    assert [t["opponent"] for t in timeline[:3]] == ["Kim", "Lee", "Park"]


def test_head_to_head_groups_opponent_across_entries(test_db: Path) -> None:
    owner = _seed_user(test_db)
    sub = _seed_tournament(test_db, owner)
    _seed_fixture(test_db, owner, sub)

    h2h = competition.head_to_head(owner, sub)
    by_opp = {r["opponent"]: r for r in h2h}

    # Kim met in both entries: 2 wins aggregated.
    assert by_opp["Kim"]["wins"] == 2
    assert by_opp["Kim"]["losses"] == 0
    assert by_opp["Kim"]["total"] == 2
    assert by_opp["Kim"]["win_rate"] == pytest.approx(1.0)

    # Lee: one loss, one win across the two entries.
    assert (by_opp["Lee"]["wins"], by_opp["Lee"]["losses"]) == (1, 1)
    assert by_opp["Lee"]["win_rate"] == pytest.approx(0.5)

    # Park: two draws.
    assert by_opp["Park"]["draws"] == 2
    assert by_opp["Park"]["wins"] == 0
    assert by_opp["Park"]["win_rate"] == pytest.approx(0.0)

    # Every opponent appears exactly once.
    assert sorted(by_opp) == ["Kim", "Lee", "Park"]
    assert len(h2h) == 3
