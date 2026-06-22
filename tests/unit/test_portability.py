"""Unit tests for app.services.portability (data-export half of portability).

Acceptance criteria
-------------------
1. ``export_data(owner_id)`` for a seeded account returns the versioned envelope
   (``schema_version``, ``exported_at``, ``data``) with all eight expected
   top-level data keys, and at least one row per non-empty table.
2. Entry memos are present in the ``entries`` export (PIPA access right).
3. No excluded field — ``owner_id``, ``password_hash``, ``provider_id``,
   ``auth_provider``, ``display_name``, or the derived cache columns — appears
   anywhere in the output (checked recursively).
4. Exporting account A never includes any row belonging to account B
   (multi-user isolation).

Each test uses its own fresh migrated SQLite in ``tmp_path`` (never ``:memory:``
and never the dev DB). The base category/activity/field_def rows come from
``tests.conftest.seed_test_activity``; the few content rows that helper
doesn't create (entries, tags, matches) are inserted directly with raw SQL so
the test doesn't depend on the entries service.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import connections, portability
from tests.conftest import seed_test_activity

# Fields that must never appear anywhere in an export, at any nesting depth.
_FORBIDDEN_KEYS = frozenset(
    {
        "owner_id",
        "password_hash",
        "provider_id",
        "auth_provider",
        "display_name",
        "cached_count",
        "cached_streak",
        "last_entry_at",
    }
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "categories",
        "sub_tallies",
        "field_defs",
        "tags",
        "entries",
        "entry_tags",
        "entry_values",
        "matches",
    }
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
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
    return cur.lastrowid


def _add_entry_with_memo(
    conn: sqlite3.Connection, owner_id: int, activity_id: int, memo: str
) -> int:
    """Insert one entry (with a memo) and return its id."""
    cur = conn.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at, memo) VALUES (?, ?, ?, ?)",
        (owner_id, activity_id, "2026-06-12T00:00:00Z", memo),
    )
    conn.commit()
    return cur.lastrowid


def _add_match(conn: sqlite3.Connection, owner_id: int, entry_id: int) -> None:
    conn.execute(
        "INSERT INTO match (entry_id, owner_id, opponent, score, result) VALUES (?, ?, ?, ?, ?)",
        (entry_id, owner_id, "Rival", "2-1", "win"),
    )
    conn.commit()


def _add_tag_and_link(
    conn: sqlite3.Connection, owner_id: int, activity_id: int, entry_id: int
) -> None:
    """Attach a tag (under the sub-tally's tag_group field) to an entry."""
    field_id = conn.execute(
        "SELECT id FROM field_def WHERE activity_id = ? AND kind = 'tag_group' LIMIT 1",
        (activity_id,),
    ).fetchone()[0]
    tag_id = conn.execute(
        "INSERT INTO tag (owner_id, field_def_id, name) VALUES (?, ?, ?)",
        (owner_id, field_id, "morning"),
    ).lastrowid
    conn.execute("INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)", (entry_id, tag_id))
    conn.execute(
        "INSERT INTO entry_value (entry_id, field_def_id, text_value) VALUES (?, ?, ?)",
        (entry_id, field_id, "freeform"),
    )
    conn.commit()


def _first_activity(conn: sqlite3.Connection, owner_id: int) -> int:
    return conn.execute(
        "SELECT id FROM activity WHERE owner_id = ? ORDER BY id LIMIT 1", (owner_id,)
    ).fetchone()[0]


@pytest.fixture()
def populated_db(tmp_path: Path, monkeypatch):
    """Fresh DB, one seeded user with one entry + memo + match + tag.

    Returns (db_path, owner_id, memo_text).
    """
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    seed_test_activity(owner_id, name="Test Activity")

    memo = "오늘 연습 좋았다"  # personal data: must survive export
    conn = _raw(db_path)
    activity_id = _first_activity(conn, owner_id)
    entry_id = _add_entry_with_memo(conn, owner_id, activity_id, memo)
    _add_match(conn, owner_id, entry_id)
    _add_tag_and_link(conn, owner_id, activity_id, entry_id)
    conn.close()

    return db_path, owner_id, memo


# Recursive forbidden-key scan -------------------------------------------------


def _walk_keys(obj) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.append(key)
            found.extend(_walk_keys(value))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found.extend(_walk_keys(item))
    return found


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_export_has_versioned_envelope(populated_db):
    _db_path, owner_id, _memo = populated_db
    snapshot = portability.export_data(owner_id)

    assert snapshot["schema_version"] == portability.SCHEMA_VERSION
    assert isinstance(snapshot["exported_at"], str)
    assert snapshot["exported_at"].endswith("Z")
    assert set(snapshot["data"].keys()) == _TOP_LEVEL_KEYS


def test_export_includes_a_row_per_nonempty_table(populated_db):
    _db_path, owner_id, _memo = populated_db
    data = portability.export_data(owner_id)["data"]

    # Seeding + the fixture's inserts touch every table.
    for key in _TOP_LEVEL_KEYS:
        assert len(data[key]) >= 1, f"expected at least one {key} row"


def test_memos_are_exported(populated_db):
    _db_path, owner_id, memo = populated_db
    data = portability.export_data(owner_id)["data"]

    memos = [e["memo"] for e in data["entries"]]
    assert memo in memos


def test_no_excluded_fields_anywhere(populated_db):
    _db_path, owner_id, _memo = populated_db
    snapshot = portability.export_data(owner_id)

    keys = set(_walk_keys(snapshot))
    leaked = keys & _FORBIDDEN_KEYS
    assert not leaked, f"export leaked forbidden fields: {sorted(leaked)}"


def test_category_rows_carry_only_allowed_columns(populated_db):
    _db_path, owner_id, _memo = populated_db
    data = portability.export_data(owner_id)["data"]

    expected = {"id", "name", "color", "icon", "sort_order", "archived_at", "created_at"}
    assert data["categories"], "fixture should have seeded categories"
    for row in data["categories"]:
        assert set(row.keys()) == expected


def test_activity_excludes_cache_columns(populated_db):
    _db_path, owner_id, _memo = populated_db
    data = portability.export_data(owner_id)["data"]

    assert data["sub_tallies"]
    for row in data["sub_tallies"]:
        for cache_col in ("cached_count", "cached_streak", "last_entry_at"):
            assert cache_col not in row


def test_isolation_excludes_other_owner_rows(tmp_path, monkeypatch):
    """Account A's export must contain no row belonging to account B."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_a = _make_user(conn)
    owner_b = _make_user(conn)
    conn.close()

    seed_test_activity(owner_a, name="Test Activity")
    seed_test_activity(owner_b, name="Test Activity")

    # Give each owner a distinctly-memo'd entry + match + tag.
    conn = _raw(db_path)
    sub_a = _first_activity(conn, owner_a)
    sub_b = _first_activity(conn, owner_b)
    entry_a = _add_entry_with_memo(conn, owner_a, sub_a, "memo-A")
    entry_b = _add_entry_with_memo(conn, owner_b, sub_b, "memo-B")
    _add_match(conn, owner_a, entry_a)
    _add_match(conn, owner_b, entry_b)
    _add_tag_and_link(conn, owner_a, sub_a, entry_a)
    _add_tag_and_link(conn, owner_b, sub_b, entry_b)
    conn.close()

    # Collect every primary key that belongs to B, by table.
    conn = _raw(db_path)
    b_category_ids = {
        r[0] for r in conn.execute("SELECT id FROM category WHERE owner_id = ?", (owner_b,))
    }
    b_sub_ids = {
        r[0] for r in conn.execute("SELECT id FROM activity WHERE owner_id = ?", (owner_b,))
    }
    b_entry_ids = {
        r[0] for r in conn.execute("SELECT id FROM entry WHERE owner_id = ?", (owner_b,))
    }
    b_tag_ids = {r[0] for r in conn.execute("SELECT id FROM tag WHERE owner_id = ?", (owner_b,))}
    b_field_ids = {
        r[0]
        for r in conn.execute(
            "SELECT id FROM field_def WHERE activity_id IN "
            "(SELECT id FROM activity WHERE owner_id = ?)",
            (owner_b,),
        )
    }
    conn.close()

    data = portability.export_data(owner_a)["data"]

    assert {r["id"] for r in data["categories"]}.isdisjoint(b_category_ids)
    assert {r["id"] for r in data["sub_tallies"]}.isdisjoint(b_sub_ids)
    assert {r["id"] for r in data["entries"]}.isdisjoint(b_entry_ids)
    assert {r["id"] for r in data["tags"]}.isdisjoint(b_tag_ids)
    assert {r["id"] for r in data["field_defs"]}.isdisjoint(b_field_ids)
    # Matches reference B's entries only through entry_id; none should appear.
    assert {m["entry_id"] for m in data["matches"]}.isdisjoint(b_entry_ids)
    # Memos must not cross the boundary.
    assert "memo-B" not in [e["memo"] for e in data["entries"]]
    assert "memo-A" in [e["memo"] for e in data["entries"]]
    # Child tables (entry_tag/entry_value) reference only A's entries.
    a_entry_ids = {r["id"] for r in data["entries"]}
    assert all(et["entry_id"] in a_entry_ids for et in data["entry_tags"])
    assert all(ev["entry_id"] in a_entry_ids for ev in data["entry_values"])
    assert all(m["entry_id"] in a_entry_ids for m in data["matches"])


# ---------------------------------------------------------------------------
# Social-graph export section (social-graph Task 8)
# ---------------------------------------------------------------------------


def _make_named_user(conn: sqlite3.Connection, username: str) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, display_name) VALUES ('email', ?, ?)",
        (username, username.title()),
    )
    conn.commit()
    return cur.lastrowid


def test_social_graph_section_lists_fellows_pending_and_blocked(tmp_path, monkeypatch):
    """A user with a fellow, an incoming pending, an outgoing pending, and a
    block exports those relationships by username — and leaks no counterpart
    entries/notes."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    me = _make_named_user(conn, "me")
    fellow = _make_named_user(conn, "fellow")
    requester = _make_named_user(conn, "requester")  # sends me an incoming request
    target = _make_named_user(conn, "target")  # I send them an outgoing request
    blocked = _make_named_user(conn, "blocked")
    conn.close()

    # Each counterpart owns a seeded account with a distinctive memo, so the
    # test can assert none of that content crosses into my export.
    for uid in (fellow, requester, target, blocked):
        seed_test_activity(uid, name="Test Activity")
    conn = _raw(db_path)
    for uid, label in (
        (fellow, "fellow-secret"),
        (requester, "requester-secret"),
        (target, "target-secret"),
        (blocked, "blocked-secret"),
    ):
        act = _first_activity(conn, uid)
        _add_entry_with_memo(conn, uid, act, label)
    conn.close()

    # Accepted + consented fellow (me <-> fellow).
    connections.send_request(me, fellow)
    connections.accept(fellow, me)
    # Incoming pending: requester -> me.
    connections.send_request(requester, me)
    # Outgoing pending: me -> target.
    connections.send_request(me, target)
    # I blocked someone.
    connections.block(me, blocked)

    snapshot = portability.export_data(me)
    sg = snapshot["social_graph"]

    fellow_names = {f["username"] for f in sg["fellows"]}
    assert fellow_names == {"fellow"}
    assert sg["fellows"][0]["display_name"] == "Fellow"
    assert sg["fellows"][0]["connected_at"] is not None
    assert sg["fellows"][0]["responded_at"] is not None

    incoming = {p["username"] for p in sg["pending_requests"] if p["direction"] == "incoming"}
    outgoing = {p["username"] for p in sg["pending_requests"] if p["direction"] == "outgoing"}
    assert incoming == {"requester"}
    assert outgoing == {"target"}

    assert {b["username"] for b in sg["blocked"]} == {"blocked"}

    # No counterpart private content leaked into my export, anywhere.
    blob = json.dumps(snapshot, ensure_ascii=False)
    for secret in ("fellow-secret", "requester-secret", "target-secret", "blocked-secret"):
        assert secret not in blob
    # My own entries list carries none of the counterparts' entries.
    assert snapshot["data"]["entries"] == []


def test_social_graph_section_empty_for_lone_user(tmp_path, monkeypatch):
    """A user with no relationships still gets the three empty lists."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()
    seed_test_activity(owner_id, name="Test Activity")

    sg = portability.export_data(owner_id)["social_graph"]
    assert sg == {"fellows": [], "pending_requests": [], "blocked": []}


# ===========================================================================
# Import ("carry over your data") tests
# ===========================================================================

_TABLES = (
    "categories",
    "sub_tallies",
    "field_defs",
    "tags",
    "entries",
    "entry_tags",
    "entry_values",
    "matches",
)


def _empty_payload() -> dict:
    """A minimal valid envelope with no rows in any table."""
    return {
        "schema_version": portability.SCHEMA_VERSION,
        "exported_at": "2026-06-12T00:00:00Z",
        "data": {table: [] for table in _TABLES},
    }


def _seed_and_export(tmp_path: Path, monkeypatch) -> tuple[Path, int, dict]:
    """Build a populated account and return (db_path, owner_id, exported snapshot)."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    seed_test_activity(owner_id, name="Test Activity")

    conn = _raw(db_path)
    activity_id = _first_activity(conn, owner_id)
    e1 = _add_entry_with_memo(conn, owner_id, activity_id, "첫 연습")
    _add_entry_with_memo(conn, owner_id, activity_id, "둘째 연습")
    _add_match(conn, owner_id, e1)
    _add_tag_and_link(conn, owner_id, activity_id, e1)
    conn.close()

    snapshot = portability.export_data(owner_id)
    return db_path, owner_id, snapshot


def _strip_ids(data: dict) -> dict:
    """Return data with every id-shaped field removed, for id-agnostic compare.

    Removes primary keys and foreign keys alike so two exports that differ only
    by autoincrement values compare equal on their content.
    """
    id_cols = {
        "id",
        "category_id",
        "activity_id",
        "field_def_id",
        "entry_id",
        "tag_id",
    }
    out: dict = {}
    for table, rows in data.items():
        cleaned = []
        for row in rows:
            cleaned.append({k: v for k, v in row.items() if k not in id_cols})
        # Sort for order-independent comparison.
        cleaned.sort(key=lambda r: sorted(r.items(), key=lambda kv: (kv[0], str(kv[1]))))
        out[table] = cleaned
    return out


# --- round-trip + replace semantics ---------------------------------------


def test_round_trip_into_fresh_account(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    # A second, empty account in the same DB.
    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    summary = portability.import_data(owner_b, snapshot)
    assert summary["categories"] == len(snapshot["data"]["categories"])
    assert summary["entries"] == len(snapshot["data"]["entries"])

    re_export = portability.export_data(owner_b)
    assert re_export["schema_version"] == snapshot["schema_version"]
    # Equivalent except for ids.
    assert _strip_ids(re_export["data"]) == _strip_ids(snapshot["data"])


def test_replace_semantics_wipes_existing(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    # owner_b already has its own (different) seeded data.
    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()
    seed_test_activity(owner_b, name="Test Activity")
    conn = _raw(db_path)
    sub_b = _first_activity(conn, owner_b)
    _add_entry_with_memo(conn, owner_b, sub_b, "owner-b-only-memo")
    conn.close()

    portability.import_data(owner_b, snapshot)

    after = portability.export_data(owner_b)["data"]
    memos = [e["memo"] for e in after["entries"]]
    assert "owner-b-only-memo" not in memos
    assert "첫 연습" in memos
    # Content matches the imported snapshot, ids aside.
    assert _strip_ids(after) == _strip_ids(snapshot["data"])


def test_owner_id_always_from_argument_never_payload(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    portability.import_data(owner_b, snapshot)

    # Every owner-scoped row written must carry owner_b, regardless of payload.
    conn = _raw(db_path)
    for table in ("category", "activity", "entry", "tag", "match"):
        owners = {
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT owner_id FROM {table} WHERE owner_id = ?", (owner_b,)
            )  # noqa: S608, E501
        }
        # And confirm no row for this owner has any other owner_id.
        all_owners = {r[0] for r in conn.execute(f"SELECT owner_id FROM {table}")}  # noqa: S608
        if all_owners:
            assert owner_b in all_owners
        assert owners <= {owner_b}
    conn.close()


def test_cache_recomputed_after_import(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    portability.import_data(owner_b, snapshot)

    # The imported sub-tally that received the two entries should have count 2.
    conn = _raw(db_path)
    rows = conn.execute(
        "SELECT id, cached_count FROM activity WHERE owner_id = ?", (owner_b,)
    ).fetchall()
    conn.close()

    total = sum(r["cached_count"] for r in rows)
    assert total == len(snapshot["data"]["entries"])  # 2 entries imported

    # recompute() must agree with the persisted cache (drift guard).
    from zoneinfo import ZoneInfo

    from app.services import entries

    for r in rows:
        rebuilt = entries.recompute(r["id"], owner_b, tz=ZoneInfo("UTC"))
        assert rebuilt["cached_count"] == r["cached_count"]


# --- validation rejections (no DB write) ----------------------------------


def _count_all_rows(db_path: Path, owner_id: int) -> int:
    conn = _raw(db_path)
    total = 0
    for table in ("category", "activity", "entry", "tag", "match"):
        total += conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE owner_id = ?",
            (owner_id,),  # noqa: S608
        ).fetchone()[0]
    conn.close()
    return total


def test_schema_version_mismatch_rejected(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    payload = _empty_payload()
    payload["schema_version"] = 99
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_id, payload)


def test_missing_table_key_rejected(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))
    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    payload = _empty_payload()
    del payload["data"]["matches"]
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_id, payload)


def test_row_count_cap_rejected_before_write(tmp_path, monkeypatch):
    db_path, owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()
    seed_test_activity(owner_b, name="Test Activity")  # give owner_b existing data to protect
    before = _count_all_rows(db_path, owner_b)

    payload = _empty_payload()
    # One category that satisfies references for an over-cap pile of entries.
    payload["data"]["categories"] = [
        {
            "id": 1,
            "name": "X",
            "color": None,
            "icon": None,
            "sort_order": 0,
            "archived_at": None,
            "created_at": "2026-06-12T00:00:00Z",
        }
    ]
    payload["data"]["sub_tallies"] = [
        {
            "id": 1,
            "category_id": 1,
            "name": "X",
            "count_mode": "running",
            "config_json": None,
            "sort_order": 0,
            "archived_at": None,
            "created_at": "2026-06-12T00:00:00Z",
        }
    ]
    payload["data"]["entries"] = [
        {
            "id": n,
            "activity_id": 1,
            "occurred_at": "2026-06-12T00:00:00Z",
            "memo": None,
            "created_at": "2026-06-12T00:00:00Z",
            "updated_at": "2026-06-12T00:00:00Z",
        }
        for n in range(portability.MAX_ROWS_PER_TABLE + 1)
    ]

    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)

    # Nothing was written: owner_b's data is untouched.
    assert _count_all_rows(db_path, owner_b) == before


def test_unknown_key_in_row_rejected(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    payload = copy.deepcopy(snapshot)
    payload["data"]["categories"][0]["surprise"] = "extra"
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)


def test_enum_violation_rejected(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    payload = copy.deepcopy(snapshot)
    payload["data"]["sub_tallies"][0]["count_mode"] = "bogus"
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)


def test_dangling_reference_rejected(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    payload = copy.deepcopy(snapshot)
    # Point an entry at a activity id that exists in no sub_tallies row.
    bogus = 10_000_000
    assert all(s["id"] != bogus for s in payload["data"]["sub_tallies"])
    payload["data"]["entries"][0]["activity_id"] = bogus
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)


def test_wrong_type_rejected(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    payload = copy.deepcopy(snapshot)
    payload["data"]["categories"][0]["sort_order"] = "not-an-int"
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)


def test_string_length_cap_rejected(tmp_path, monkeypatch):
    db_path, _owner_a, snapshot = _seed_and_export(tmp_path, monkeypatch)

    conn = _raw(db_path)
    owner_b = _make_user(conn)
    conn.close()

    payload = copy.deepcopy(snapshot)
    payload["data"]["entries"][0]["memo"] = "x" * (portability.MAX_TEXT_LEN + 1)
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_b, payload)


# --- backward-compatible import of pre-0013 (progression-era) exports -------


def _legacy_progression_payload() -> dict:
    """A pre-0013 export envelope: one category/activity/entry plus the dropped
    ``levels`` / ``level_rules`` sections and a ``field_defs`` row with the
    removed ``level`` kind.

    This mirrors what ``export_data`` emitted before migration 0013 removed the
    progression system. Importing it today must succeed, silently dropping the
    progression content rather than erroring.
    """
    return {
        "schema_version": portability.SCHEMA_VERSION,
        "exported_at": "2026-06-01T00:00:00Z",
        "data": {
            "categories": [
                {
                    "id": 1,
                    "name": "Judo",
                    "color": None,
                    "icon": None,
                    "sort_order": 0,
                    "archived_at": None,
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ],
            "sub_tallies": [
                {
                    "id": 1,
                    "category_id": 1,
                    "name": "Judo",
                    # 'progression' is still a legal count_mode in the schema;
                    # the importer must round-trip it untouched.
                    "count_mode": "progression",
                    "config_json": None,
                    "sort_order": 0,
                    "archived_at": None,
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ],
            "field_defs": [
                {
                    "id": 1,
                    "activity_id": 1,
                    "kind": "count",
                    "label": "Reps",
                    "config_json": None,
                    "sort_order": 0,
                },
                # A pre-0013 field with the dropped 'level' kind — must be
                # silently dropped, not rejected.
                {
                    "id": 2,
                    "activity_id": 1,
                    "kind": "level",
                    "label": "Belt",
                    "config_json": None,
                    "sort_order": 1,
                },
            ],
            "tags": [],
            "entries": [
                {
                    "id": 1,
                    "activity_id": 1,
                    "occurred_at": "2026-06-01T00:00:00Z",
                    "memo": "legacy-memo",
                    "created_at": "2026-06-01T00:00:00Z",
                    "updated_at": "2026-06-01T00:00:00Z",
                }
            ],
            "entry_tags": [],
            # An entry_value on the dropped 'level' field — must be dropped with it.
            "entry_values": [
                {
                    "entry_id": 1,
                    "field_def_id": 2,
                    "num_value": 3.0,
                    "text_value": None,
                },
            ],
            "matches": [],
            # The dropped progression sections, present in old files.
            "levels": [
                {
                    "id": 1,
                    "activity_id": 1,
                    "track": "dan",
                    "ordinal": 1,
                    "code": "1k",
                    "label": "1st kyu",
                    "archived_at": None,
                }
            ],
            "level_rules": [
                {
                    "id": 1,
                    "activity_id": 1,
                    "from_level_id": None,
                    "to_level_id": 1,
                    "gate_type": "count",
                    "gate_value": 10.0,
                    "min_age": None,
                    "prereq_level_id": None,
                }
            ],
        },
    }


def test_import_old_format_with_levels_succeeds_dropping_them(tmp_path, monkeypatch):
    """A pre-0013 export carrying ``levels``/``level_rules`` keys and a legacy
    ``level`` field_def imports without error, with that content silently
    dropped and the surviving content intact."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    payload = _legacy_progression_payload()
    summary = portability.import_data(owner_id, payload)

    # Surviving tables imported; legacy sections are not in the summary at all.
    assert summary["categories"] == 1
    assert summary["entries"] == 1
    assert "levels" not in summary
    assert "level_rules" not in summary
    # The legacy 'level' field_def was dropped; only the surviving 'count' field
    # was written.
    assert summary["field_defs"] == 1
    # The entry_value pointing at the dropped 'level' field was dropped too.
    assert summary["entry_values"] == 0

    # Re-export confirms no levels/level_rules keys and the surviving content.
    re_export = portability.export_data(owner_id)
    assert "levels" not in re_export["data"]
    assert "level_rules" not in re_export["data"]
    kinds = {f["kind"] for f in re_export["data"]["field_defs"]}
    assert kinds == {"count"}
    assert [e["memo"] for e in re_export["data"]["entries"]] == ["legacy-memo"]
    # 'progression' count_mode round-tripped untouched.
    assert re_export["data"]["sub_tallies"][0]["count_mode"] == "progression"


def test_import_old_format_levels_keys_alone_do_not_error(tmp_path, monkeypatch):
    """Even an otherwise-empty payload that still carries the legacy keys
    imports cleanly (the keys are tolerated, not required)."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    payload = _empty_payload()
    payload["data"]["levels"] = []
    payload["data"]["level_rules"] = []

    summary = portability.import_data(owner_id, payload)
    assert "levels" not in summary
    assert "level_rules" not in summary


def test_import_unknown_extra_table_key_still_rejected(tmp_path, monkeypatch):
    """A genuinely unknown extra key (not a known legacy table) is still a hard
    validation error — the legacy tolerance is narrow."""
    db_path = _make_db(tmp_path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(db_path))

    conn = _raw(db_path)
    owner_id = _make_user(conn)
    conn.close()

    payload = _empty_payload()
    payload["data"]["surprise_table"] = []
    with pytest.raises(portability.ImportValidationError):
        portability.import_data(owner_id, payload)
