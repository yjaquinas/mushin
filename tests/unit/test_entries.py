"""Tests for the entry CRUD + cache-discipline service (Task 2).

Acceptance criteria covered
---------------------------
1. Every accessor requires ``owner_id`` — a query without it is impossible by
   construction (``test_accessor_requires_owner_id_by_construction`` and the
   multi-user isolation tests).
2. Create/delete update the sub_tally cache atomically; ``recompute()`` returns
   identical values to the maintained cache across a sequence of creates/deletes
   incl. backfill and same-day double-log.
3. ``occurred_at`` defaults to now and accepts a past timestamp (backfill).

Each test runs against its own freshly-migrated temp SQLite file; ``DATABASE_PATH``
is pointed at it so the service's ``db.connect()`` uses the test DB (never the dev
DB). Pattern mirrors tests/unit/test_migration.py.
"""

from __future__ import annotations

import inspect
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.services import _db, entries

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


def _seed_user(db_path: Path, provider: str = "email", name: str = "U") -> int:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO user (auth_provider, display_name) VALUES (?, ?)",
            (provider, name),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _seed_sub_tally(
    db_path: Path, owner_id: int, *, mode: str = "running", name: str = "Practice"
) -> dict[str, int]:
    """Create a category + sub_tally + a count field_def + a tag, all for owner.

    Returns the ids of interest.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Kendo', 0)",
            (owner_id,),
        )
        category_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO sub_tally (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, ?, 0)",
            (owner_id, category_id, name, mode),
        )
        sub_tally_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (sub_tally_id, kind, label, sort_order)"
            " VALUES (?, 'count', 'Reps', 0)",
            (sub_tally_id,),
        )
        count_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (sub_tally_id, kind, label, sort_order)"
            " VALUES (?, 'tag_group', 'Mood', 1)",
            (sub_tally_id,),
        )
        tag_group_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order)"
            " VALUES (?, ?, 'morning', 0)",
            (owner_id, tag_group_fid),
        )
        tag_id = cur.lastrowid
        return {
            "category_id": category_id,
            "sub_tally_id": sub_tally_id,
            "count_fid": count_fid,
            "tag_group_fid": tag_group_fid,
            "tag_id": tag_id,
        }
    finally:
        conn.close()


def _cache(db_path: Path, sub_tally_id: int) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT cached_count, cached_streak, last_entry_at FROM sub_tally WHERE id = ?",
            (sub_tally_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. owner_id is required by construction
# ---------------------------------------------------------------------------


def test_accessor_requires_owner_id_by_construction() -> None:
    """Every _db accessor takes owner_id as a required positional arg.

    There is no overload that omits it — the signature itself is the guard.
    """
    for fn in (_db.fetch_one, _db.fetch_all, _db.exists, _db.update, _db.delete):
        sig = inspect.signature(fn)
        owner = sig.parameters.get("owner_id")
        assert owner is not None, f"{fn.__name__} must take owner_id"
        # Required: no default -> the call can't omit it.
        assert owner.default is inspect.Parameter.empty
        # Positional (conn, table, owner_id, ...) — it sits in the call's spine,
        # not tucked away as an optional keyword.
        assert owner.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )


def test_accessor_rejects_unowned_table(test_db: Path) -> None:
    """A table without owner_id cannot be scope-queried — fails loudly."""
    with pytest.raises(_db.OwnerScopeError), db.connect() as conn:
        conn.execute("BEGIN")
        _db.fetch_one(conn, "field_def", 1, where="id = 1")


# ---------------------------------------------------------------------------
# 2. CRUD round-trip
# ---------------------------------------------------------------------------


def test_create_and_get_round_trip(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)

    created = entries.create(
        owner,
        ids["sub_tally_id"],
        {
            "memo": "good session",
            "tags": [ids["tag_id"]],
            "values": {ids["count_fid"]: 30},
        },
    )
    assert created["memo"] == "good session"
    assert created["tags"] == [ids["tag_id"]]
    assert created["values"][0]["num_value"] == 30.0

    fetched = entries.get(owner, created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["tags"] == [ids["tag_id"]]


def test_occurred_at_defaults_to_now(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)

    before = datetime.now(UTC)
    created = entries.create(owner, ids["sub_tally_id"], {})
    after = datetime.now(UTC)

    occurred = datetime.fromisoformat(created["occurred_at"])
    assert before <= occurred <= after


def test_occurred_at_accepts_backfill(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)

    past = "2020-01-15T08:30:00+09:00"
    created = entries.create(owner, ids["sub_tally_id"], {}, occurred_at=past)
    assert created["occurred_at"] == past


def test_list_newest_first(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)

    entries.create(owner, ids["sub_tally_id"], {}, occurred_at="2026-01-01T10:00:00+09:00")
    entries.create(owner, ids["sub_tally_id"], {}, occurred_at="2026-03-01T10:00:00+09:00")
    entries.create(owner, ids["sub_tally_id"], {}, occurred_at="2026-02-01T10:00:00+09:00")

    listed = entries.list_for_sub_tally(owner, ids["sub_tally_id"])
    occurreds = [e["occurred_at"] for e in listed]
    assert occurreds == sorted(occurreds, reverse=True)


def test_update_bumps_updated_at_and_replaces_values(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    created = entries.create(owner, ids["sub_tally_id"], {"values": {ids["count_fid"]: 10}})

    updated = entries.update(
        owner,
        created["id"],
        memo="edited",
        values={ids["count_fid"]: 99},
        tags=[ids["tag_id"]],
    )
    assert updated["memo"] == "edited"
    assert updated["values"][0]["num_value"] == 99.0
    assert updated["tags"] == [ids["tag_id"]]
    assert updated["updated_at"] >= created["updated_at"]


def test_delete_removes_entry(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    created = entries.create(owner, ids["sub_tally_id"], {})

    assert entries.delete(owner, created["id"]) is True
    with pytest.raises(entries.EntryNotFoundError):
        entries.get(owner, created["id"])
    assert entries.delete(owner, created["id"]) is False


# ---------------------------------------------------------------------------
# 3. Payload validation
# ---------------------------------------------------------------------------


def test_create_rejects_foreign_field_def(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids_a = _seed_sub_tally(test_db, owner, name="A")
    ids_b = _seed_sub_tally(test_db, owner, name="B")

    with pytest.raises(entries.PayloadError):
        entries.create(
            owner,
            ids_a["sub_tally_id"],
            {"values": {ids_b["count_fid"]: 5}},  # field_def from the other sub-tally
        )


def test_create_rejects_foreign_tag(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids_a = _seed_sub_tally(test_db, owner, name="A")
    ids_b = _seed_sub_tally(test_db, owner, name="B")

    with pytest.raises(entries.PayloadError):
        entries.create(owner, ids_a["sub_tally_id"], {"tags": [ids_b["tag_id"]]})


# ---------------------------------------------------------------------------
# 4. Cache maintenance + recompute drift guard
# ---------------------------------------------------------------------------


def test_create_delete_maintain_cache_equals_recompute(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    st = ids["sub_tally_id"]

    def assert_cache_consistent() -> dict:
        maintained = _cache(test_db, st)
        recomputed = entries.recompute(st, owner)
        assert maintained["cached_count"] == recomputed["cached_count"]
        assert maintained["cached_streak"] == recomputed["cached_streak"]
        assert maintained["last_entry_at"] == recomputed["last_entry_at"]
        return maintained

    # Empty.
    c = assert_cache_consistent()
    assert c["cached_count"] == 0
    assert c["cached_streak"] == 0
    assert c["last_entry_at"] is None

    # Three consecutive KST days -> streak 3.
    entries.create(owner, st, {}, occurred_at="2026-06-01T10:00:00+09:00")
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00")
    e3 = entries.create(owner, st, {}, occurred_at="2026-06-03T10:00:00+09:00")
    c = assert_cache_consistent()
    assert c["cached_count"] == 3
    assert c["cached_streak"] == 3
    assert c["last_entry_at"] == "2026-06-03T10:00:00+09:00"

    # Same-day double-log: count rises, streak unchanged (one day counts once).
    entries.create(owner, st, {}, occurred_at="2026-06-03T22:00:00+09:00")
    c = assert_cache_consistent()
    assert c["cached_count"] == 4
    assert c["cached_streak"] == 3

    # Backfill a gap day far in the past: count rises, streak run still ends at
    # the most-recent day and stays 3 (the old day doesn't extend it).
    entries.create(owner, st, {}, occurred_at="2020-01-01T10:00:00+09:00")
    c = assert_cache_consistent()
    assert c["cached_count"] == 5
    assert c["cached_streak"] == 3

    # Delete the newest day's two entries -> last_entry_at moves back to 06-02,
    # streak becomes 2 (06-01, 06-02).
    entries.delete(owner, e3["id"])
    listed = entries.list_for_sub_tally(owner, st)
    for e in listed:
        if e["occurred_at"] == "2026-06-03T22:00:00+09:00":
            entries.delete(owner, e["id"])
    c = assert_cache_consistent()
    assert c["cached_count"] == 3
    assert c["cached_streak"] == 2
    assert c["last_entry_at"] == "2026-06-02T10:00:00+09:00"


def test_streak_kst_day_boundary(test_db: Path) -> None:
    """An entry at 23:30 UTC and one at 14:30 UTC the next UTC-day are the same
    KST calendar day, so they must not inflate the streak.

    2026-06-01T23:30:00Z -> 2026-06-02 08:30 KST.
    2026-06-02T05:30:00Z -> 2026-06-02 14:30 KST. Same KST day -> streak 1.
    """
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    st = ids["sub_tally_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T23:30:00+00:00")
    entries.create(owner, st, {}, occurred_at="2026-06-02T05:30:00+00:00")

    c = _cache(test_db, st)
    assert c["cached_count"] == 2
    assert c["cached_streak"] == 1
    assert c["cached_streak"] == entries.recompute(st, owner)["cached_streak"]


def test_streak_crosses_kst_midnight(test_db: Path) -> None:
    """Two instants 1 hour apart in UTC that straddle KST midnight are two
    consecutive KST days -> streak 2.

    2026-06-01T14:30:00Z -> 2026-06-01 23:30 KST.
    2026-06-01T15:30:00Z -> 2026-06-02 00:30 KST. Consecutive days -> streak 2.
    """
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    st = ids["sub_tally_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T14:30:00+00:00")
    entries.create(owner, st, {}, occurred_at="2026-06-01T15:30:00+00:00")

    c = _cache(test_db, st)
    assert c["cached_streak"] == 2


# ---------------------------------------------------------------------------
# 5. Multi-user isolation
# ---------------------------------------------------------------------------


def test_list_and_get_isolated_between_users(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_sub_tally(test_db, a, name="A-st")
    ids_b = _seed_sub_tally(test_db, b, name="B-st")

    entry_a = entries.create(a, ids_a["sub_tally_id"], {"memo": "A secret"})
    entries.create(b, ids_b["sub_tally_id"], {"memo": "B secret"})

    # B cannot read A's entry by id.
    with pytest.raises(entries.EntryNotFoundError):
        entries.get(b, entry_a["id"])

    # B listing A's sub-tally sees nothing (owner predicate, not sub_tally alone).
    assert entries.list_for_sub_tally(b, ids_a["sub_tally_id"]) == []

    # A's own list returns only A's entry.
    a_list = entries.list_for_sub_tally(a, ids_a["sub_tally_id"])
    assert [e["memo"] for e in a_list] == ["A secret"]


def test_update_and_delete_isolated_between_users(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_sub_tally(test_db, a, name="A-st")
    _seed_sub_tally(test_db, b, name="B-st")

    entry_a = entries.create(a, ids_a["sub_tally_id"], {"memo": "A only"})

    # B cannot update A's entry.
    with pytest.raises(entries.EntryNotFoundError):
        entries.update(b, entry_a["id"], memo="hijacked")

    # B cannot delete A's entry (no row removed for B).
    assert entries.delete(b, entry_a["id"]) is False

    # A's entry is untouched.
    still = entries.get(a, entry_a["id"])
    assert still["memo"] == "A only"


def test_create_rejects_other_users_sub_tally(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_sub_tally(test_db, a, name="A-st")

    # B tries to log into A's sub-tally.
    with pytest.raises(entries.SubTallyNotFoundError):
        entries.create(b, ids_a["sub_tally_id"], {})


def test_backfill_via_update_refreshes_cache(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_sub_tally(test_db, owner)
    st = ids["sub_tally_id"]

    e = entries.create(owner, st, {}, occurred_at="2026-06-01T10:00:00+09:00")
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00")
    assert _cache(test_db, st)["cached_streak"] == 2

    # Move the first entry far away -> the two days are no longer consecutive.
    entries.update(owner, e["id"], occurred_at="2020-01-01T10:00:00+09:00")
    c = _cache(test_db, st)
    assert c["cached_streak"] == 1
    assert c["last_entry_at"] == "2026-06-02T10:00:00+09:00"
    assert c["cached_streak"] == entries.recompute(st, owner)["cached_streak"]
