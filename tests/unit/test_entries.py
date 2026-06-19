"""Tests for the entry CRUD + cache-discipline service (Task 2).

Acceptance criteria covered
---------------------------
1. Every accessor requires ``owner_id`` — a query without it is impossible by
   construction (``test_accessor_requires_owner_id_by_construction`` and the
   multi-user isolation tests).
2. Create/delete update the activity cache atomically; ``recompute()`` returns
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
from zoneinfo import ZoneInfo

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.services import _db, entries

# Existing fixtures use +09:00 offsets and assert on Asia/Seoul calendar days, so
# pass that zone explicitly to preserve their expected values. The new
# America/Los_Angeles cases below prove the tz parameter actually changes which
# calendar day an instant falls in.
KST = ZoneInfo("Asia/Seoul")
LA = ZoneInfo("America/Los_Angeles")

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


def _seed_activity(
    db_path: Path, owner_id: int, *, mode: str = "running", name: str = "Practice"
) -> dict[str, int]:
    """Create a category + activity + a count field_def + a tag, all for owner.

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
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, ?, 0)",
            (owner_id, category_id, name, mode),
        )
        activity_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'count', 'Reps', 0)",
            (activity_id,),
        )
        count_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'tag_group', 'Mood', 1)",
            (activity_id,),
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
            "activity_id": activity_id,
            "count_fid": count_fid,
            "tag_group_fid": tag_group_fid,
            "tag_id": tag_id,
        }
    finally:
        conn.close()


def _cache(db_path: Path, activity_id: int) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT cached_count, cached_streak, last_entry_at FROM activity WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def _tag_archived_at(db_path: Path, tag_id: int) -> str | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT archived_at FROM tag WHERE id = ?",
            (tag_id,),
        ).fetchone()
        return None if row is None else row["archived_at"]
    finally:
        conn.close()


def _active_tag_ids_for_field(db_path: Path, owner_id: int, field_def_id: int) -> list[int]:
    """Mirror the renderer's active-tag query: WHERE archived_at IS NULL."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = _db.fetch_all(
            conn,
            "tag",
            owner_id,
            where="field_def_id = ? AND archived_at IS NULL",
            params=(field_def_id,),
            columns="id",
            order_by="sort_order, id",
        )
    return [r["id"] for r in rows]


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
    ids = _seed_activity(test_db, owner)

    created = entries.create(
        owner,
        ids["activity_id"],
        {
            "memo": "good session",
            "tags": [ids["tag_id"]],
            "values": {ids["count_fid"]: 30},
        },
        tz=KST,
    )
    assert created["memo"] == "good session"
    assert created["tags"] == [ids["tag_id"]]
    assert created["values"][0]["num_value"] == 30.0

    fetched = entries.get(owner, created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["tags"] == [ids["tag_id"]]


def test_occurred_at_defaults_to_now(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)

    before = datetime.now(UTC)
    created = entries.create(owner, ids["activity_id"], {}, tz=KST)
    after = datetime.now(UTC)

    occurred = datetime.fromisoformat(created["occurred_at"])
    assert before <= occurred <= after


def test_occurred_at_accepts_backfill(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)

    past = "2020-01-15T08:30:00+09:00"
    created = entries.create(owner, ids["activity_id"], {}, occurred_at=past, tz=KST)
    assert created["occurred_at"] == past


def test_list_newest_first(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)

    entries.create(owner, ids["activity_id"], {}, occurred_at="2026-01-01T10:00:00+09:00", tz=KST)
    entries.create(owner, ids["activity_id"], {}, occurred_at="2026-03-01T10:00:00+09:00", tz=KST)
    entries.create(owner, ids["activity_id"], {}, occurred_at="2026-02-01T10:00:00+09:00", tz=KST)

    listed = entries.list_for_activity(owner, ids["activity_id"])
    occurreds = [e["occurred_at"] for e in listed]
    assert occurreds == sorted(occurreds, reverse=True)


def test_update_bumps_updated_at_and_replaces_values(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    created = entries.create(owner, ids["activity_id"], {"values": {ids["count_fid"]: 10}}, tz=KST)

    updated = entries.update(
        owner,
        created["id"],
        memo="edited",
        values={ids["count_fid"]: 99},
        tags=[ids["tag_id"]],
        tz=KST,
    )
    assert updated["memo"] == "edited"
    assert updated["values"][0]["num_value"] == 99.0
    assert updated["tags"] == [ids["tag_id"]]
    assert updated["updated_at"] >= created["updated_at"]


def test_delete_removes_entry(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    created = entries.create(owner, ids["activity_id"], {}, tz=KST)

    assert entries.delete(owner, created["id"], tz=KST) is True
    with pytest.raises(entries.EntryNotFoundError):
        entries.get(owner, created["id"])
    assert entries.delete(owner, created["id"], tz=KST) is False


# ---------------------------------------------------------------------------
# 3. Payload validation
# ---------------------------------------------------------------------------


def test_create_rejects_foreign_field_def(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids_a = _seed_activity(test_db, owner, name="A")
    ids_b = _seed_activity(test_db, owner, name="B")

    with pytest.raises(entries.PayloadError):
        entries.create(
            owner,
            ids_a["activity_id"],
            {"values": {ids_b["count_fid"]: 5}},  # field_def from the other sub-tally
            tz=KST,
        )


def test_create_rejects_foreign_tag(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids_a = _seed_activity(test_db, owner, name="A")
    ids_b = _seed_activity(test_db, owner, name="B")

    with pytest.raises(entries.PayloadError):
        entries.create(owner, ids_a["activity_id"], {"tags": [ids_b["tag_id"]]}, tz=KST)


# ---------------------------------------------------------------------------
# 4. Cache maintenance + recompute drift guard
# ---------------------------------------------------------------------------


def test_create_delete_maintain_cache_equals_recompute(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    def assert_cache_consistent() -> dict:
        maintained = _cache(test_db, st)
        recomputed = entries.recompute(st, owner, tz=KST)
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
    entries.create(owner, st, {}, occurred_at="2026-06-01T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    e3 = entries.create(owner, st, {}, occurred_at="2026-06-03T10:00:00+09:00", tz=KST)
    c = assert_cache_consistent()
    assert c["cached_count"] == 3
    assert c["cached_streak"] == 3
    assert c["last_entry_at"] == "2026-06-03T10:00:00+09:00"

    # Same-day double-log: count rises, streak unchanged (one day counts once).
    entries.create(owner, st, {}, occurred_at="2026-06-03T22:00:00+09:00", tz=KST)
    c = assert_cache_consistent()
    assert c["cached_count"] == 4
    assert c["cached_streak"] == 3

    # Backfill a gap day far in the past: count rises, streak run still ends at
    # the most-recent day and stays 3 (the old day doesn't extend it).
    entries.create(owner, st, {}, occurred_at="2020-01-01T10:00:00+09:00", tz=KST)
    c = assert_cache_consistent()
    assert c["cached_count"] == 5
    assert c["cached_streak"] == 3

    # Delete the newest day's two entries -> last_entry_at moves back to 06-02,
    # streak becomes 2 (06-01, 06-02).
    entries.delete(owner, e3["id"], tz=KST)
    listed = entries.list_for_activity(owner, st)
    for e in listed:
        if e["occurred_at"] == "2026-06-03T22:00:00+09:00":
            entries.delete(owner, e["id"], tz=KST)
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
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T23:30:00+00:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-02T05:30:00+00:00", tz=KST)

    c = _cache(test_db, st)
    assert c["cached_count"] == 2
    assert c["cached_streak"] == 1
    assert c["cached_streak"] == entries.recompute(st, owner, tz=KST)["cached_streak"]


def test_streak_crosses_kst_midnight(test_db: Path) -> None:
    """Two instants 1 hour apart in UTC that straddle KST midnight are two
    consecutive KST days -> streak 2.

    2026-06-01T14:30:00Z -> 2026-06-01 23:30 KST.
    2026-06-01T15:30:00Z -> 2026-06-02 00:30 KST. Consecutive days -> streak 2.
    """
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T14:30:00+00:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-01T15:30:00+00:00", tz=KST)

    c = _cache(test_db, st)
    assert c["cached_streak"] == 2


def test_streak_day_depends_on_caller_timezone(test_db: Path) -> None:
    """The same two instants collapse to one streak day in LA but split into two
    in KST — proof that ``tz`` actually selects which calendar day applies.

    2026-06-01T05:30:00Z  -> 2026-05-31 22:30 LA (PDT, -07) | 2026-06-01 14:30 KST
    2026-06-01T08:30:00Z  -> 2026-06-01 01:30 LA            | 2026-06-01 17:30 KST

    In LA these straddle local midnight -> two consecutive days -> streak 2.
    In KST both fall on 2026-06-01 -> one day -> streak 1.
    """
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T05:30:00+00:00", tz=LA)
    entries.create(owner, st, {}, occurred_at="2026-06-01T08:30:00+00:00", tz=LA)

    # Computed with LA: the two instants are different LA days -> streak 2.
    la = entries.recompute(st, owner, tz=LA)
    assert la["cached_streak"] == 2

    # The exact same stored rows, recomputed with KST: same KST day -> streak 1.
    kst = entries.recompute(st, owner, tz=KST)
    assert kst["cached_streak"] == 1


# ---------------------------------------------------------------------------
# 5. Multi-user isolation
# ---------------------------------------------------------------------------


def test_list_and_get_isolated_between_users(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")
    ids_b = _seed_activity(test_db, b, name="B-st")

    entry_a = entries.create(a, ids_a["activity_id"], {"memo": "A secret"}, tz=KST)
    entries.create(b, ids_b["activity_id"], {"memo": "B secret"}, tz=KST)

    # B cannot read A's entry by id.
    with pytest.raises(entries.EntryNotFoundError):
        entries.get(b, entry_a["id"])

    # B listing A's sub-tally sees nothing (owner predicate, not activity alone).
    assert entries.list_for_activity(b, ids_a["activity_id"]) == []

    # A's own list returns only A's entry.
    a_list = entries.list_for_activity(a, ids_a["activity_id"])
    assert [e["memo"] for e in a_list] == ["A secret"]


def test_update_and_delete_isolated_between_users(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")
    _seed_activity(test_db, b, name="B-st")

    entry_a = entries.create(a, ids_a["activity_id"], {"memo": "A only"}, tz=KST)

    # B cannot update A's entry.
    with pytest.raises(entries.EntryNotFoundError):
        entries.update(b, entry_a["id"], memo="hijacked", tz=KST)

    # B cannot delete A's entry (no row removed for B).
    assert entries.delete(b, entry_a["id"], tz=KST) is False

    # A's entry is untouched.
    still = entries.get(a, entry_a["id"])
    assert still["memo"] == "A only"


def test_create_rejects_other_users_activity(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")

    # B tries to log into A's sub-tally.
    with pytest.raises(entries.SubTallyNotFoundError):
        entries.create(b, ids_a["activity_id"], {}, tz=KST)


# ---------------------------------------------------------------------------
# 6. Tag archival (soft delete)
# ---------------------------------------------------------------------------


def test_archive_tag_success(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    tag_id = ids["tag_id"]
    field_def_id = ids["tag_group_fid"]

    # The tag starts active and visible in the field's active-tag list.
    assert _tag_archived_at(test_db, tag_id) is None
    assert tag_id in _active_tag_ids_for_field(test_db, owner, field_def_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        archived = entries.archive_tag(conn, owner_id=owner, tag_id=tag_id)
    assert archived is True

    # archived_at is now set and the tag no longer appears in the active list.
    assert _tag_archived_at(test_db, tag_id) is not None
    assert tag_id not in _active_tag_ids_for_field(test_db, owner, field_def_id)


def test_archive_tag_wrong_owner(test_db: Path) -> None:
    owner = _seed_user(test_db, name="A")
    other = _seed_user(test_db, name="B")
    ids = _seed_activity(test_db, owner)
    tag_id = ids["tag_id"]

    with db.connect() as conn:
        conn.execute("BEGIN")
        archived = entries.archive_tag(conn, owner_id=other, tag_id=tag_id)
    assert archived is False

    # The tag is untouched.
    assert _tag_archived_at(test_db, tag_id) is None


def test_archive_tag_nonexistent(test_db: Path) -> None:
    owner = _seed_user(test_db)
    _seed_activity(test_db, owner)

    with db.connect() as conn:
        conn.execute("BEGIN")
        archived = entries.archive_tag(conn, owner_id=owner, tag_id=999999)
    assert archived is False


# ---------------------------------------------------------------------------
# 7. Hashtag parsing (pure function)
# ---------------------------------------------------------------------------


def test_parse_hashtags_basic() -> None:
    assert entries.parse_hashtags("#waza #randori") == ["waza", "randori"]


def test_parse_hashtags_empty() -> None:
    assert entries.parse_hashtags("") == []
    assert entries.parse_hashtags("   ") == []


def test_parse_hashtags_dedup() -> None:
    assert entries.parse_hashtags("#Waza #waza") == ["waza"]


def test_parse_hashtags_hyphen_underscore() -> None:
    assert entries.parse_hashtags("#comp-prep #long_run") == ["comp-prep", "long_run"]


def test_parse_hashtags_no_hashes() -> None:
    assert entries.parse_hashtags("waza randori") == []


def test_parse_hashtags_korean() -> None:
    result = entries.parse_hashtags("#태그 #상단 #중단 #발구름 에 집중")
    assert result == ["태그", "상단", "중단", "발구름"]


def test_parse_hashtags_mixed_scripts() -> None:
    result = entries.parse_hashtags("#men #태그 #kote")
    assert result == ["men", "태그", "kote"]


# ---------------------------------------------------------------------------
# 8. find_or_create_tags (text -> resolved tag ids)
# ---------------------------------------------------------------------------


def _tag_count_for_field(db_path: Path, field_def_id: int) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM tag WHERE field_def_id = ?",
            (field_def_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def test_find_or_create_tags_creates_new(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    field_def_id = ids["tag_group_fid"]
    before = _tag_count_for_field(test_db, field_def_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        result = entries.find_or_create_tags(
            conn, owner_id=owner, field_def_id=field_def_id, names=["waza"]
        )

    assert len(result) == 1
    assert _tag_count_for_field(test_db, field_def_id) == before + 1


def test_find_or_create_tags_finds_active(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    field_def_id = ids["tag_group_fid"]
    existing_id = ids["tag_id"]  # 'morning', active
    before = _tag_count_for_field(test_db, field_def_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        result = entries.find_or_create_tags(
            conn, owner_id=owner, field_def_id=field_def_id, names=["Morning"]
        )

    assert result == [existing_id]
    assert _tag_count_for_field(test_db, field_def_id) == before  # no INSERT


def test_find_or_create_tags_revives_archived(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    field_def_id = ids["tag_group_fid"]
    tag_id = ids["tag_id"]

    # Archive the tag first.
    with db.connect() as conn:
        conn.execute("BEGIN")
        entries.archive_tag(conn, owner_id=owner, tag_id=tag_id)
    assert _tag_archived_at(test_db, tag_id) is not None
    before = _tag_count_for_field(test_db, field_def_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        result = entries.find_or_create_tags(
            conn, owner_id=owner, field_def_id=field_def_id, names=["morning"]
        )

    assert result == [tag_id]
    assert _tag_archived_at(test_db, tag_id) is None  # revived in place
    assert _tag_count_for_field(test_db, field_def_id) == before  # no INSERT


def test_find_or_create_tags_empty(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    field_def_id = ids["tag_group_fid"]
    before = _tag_count_for_field(test_db, field_def_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        result = entries.find_or_create_tags(
            conn, owner_id=owner, field_def_id=field_def_id, names=[]
        )

    assert result == []
    assert _tag_count_for_field(test_db, field_def_id) == before


def test_backfill_via_update_refreshes_cache(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    e = entries.create(owner, st, {}, occurred_at="2026-06-01T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    assert _cache(test_db, st)["cached_streak"] == 2

    # Move the first entry far away -> the two days are no longer consecutive.
    entries.update(owner, e["id"], occurred_at="2020-01-01T10:00:00+09:00", tz=KST)
    c = _cache(test_db, st)
    assert c["cached_streak"] == 1
    assert c["last_entry_at"] == "2026-06-02T10:00:00+09:00"
    assert c["cached_streak"] == entries.recompute(st, owner, tz=KST)["cached_streak"]
