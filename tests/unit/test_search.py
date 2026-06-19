"""Unit tests for the search service (social-graph Tasks 9 + 10).

People search returns all real accounts (public AND private) by username /
display-name prefix, exposing ONLY handle + display name + visibility +
relationship state, with the searcher, guests, and blocked users excluded.

Tag search returns ONLY public accounts' activities matched by tag NAME, and is
structurally incapable of leaking private/limited accounts or matching
memo/entry free-text.

Each test gets a fresh tmp_path-scoped SQLite DB with all migrations applied and
``app.models.db.DATABASE_PATH`` monkeypatched at it (the ``test_connections.py``
pattern).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import connections, search


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "test.db"
    run_migrations(path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(path))
    return path


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_user(
    db_path: Path,
    username: str,
    *,
    display_name: str | None = None,
    visibility: str = "private",
    auth_provider: str = "email",
) -> int:
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, display_name, visibility) VALUES (?, ?, ?, ?)",
        (
            auth_provider,
            username,
            display_name or (username.title() if username else None),
            visibility,
        ),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _make_guest(db_path: Path) -> int:
    """A guest: auth_provider='guest', NULL username."""
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, display_name) VALUES ('guest', NULL, NULL)"
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _make_activity(db_path: Path, owner_id: int, name: str, slug: str) -> int:
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO category (owner_id, name) VALUES (?, ?)",
        (owner_id, name + " cat"),
    )
    category_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO activity (owner_id, category_id, name, count_mode, slug)"
        " VALUES (?, ?, ?, 'running', ?)",
        (owner_id, category_id, name, slug),
    )
    activity_id = cur.lastrowid
    conn.commit()
    conn.close()
    return activity_id


def _make_tag(db_path: Path, owner_id: int, activity_id: int, tag_name: str) -> int:
    """Create a tag-group field_def on the activity and a tag under it."""
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO field_def (activity_id, kind, label) VALUES (?, 'tag_group', 'Tags')",
        (activity_id,),
    )
    field_def_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO tag (owner_id, field_def_id, name) VALUES (?, ?, ?)",
        (owner_id, field_def_id, tag_name),
    )
    tag_id = cur.lastrowid
    conn.commit()
    conn.close()
    return tag_id


def _make_entry_with_memo(db_path: Path, owner_id: int, activity_id: int, memo: str) -> int:
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at, memo)"
        " VALUES (?, ?, '2026-06-18T00:00:00', ?)",
        (owner_id, activity_id, memo),
    )
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()
    return entry_id


# ---------------------------------------------------------------------------
# People search
# ---------------------------------------------------------------------------


PEOPLE_KEYS = {"id", "username", "display_name", "visibility", "relationship_state"}


def test_blank_query_returns_empty(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    _make_user(db_path, "alice")
    assert search.search_people(me, "") == []
    assert search.search_people(me, "   ") == []


def test_finds_private_user_by_username_prefix(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    alice = _make_user(db_path, "aliceblue", visibility="private")
    results = search.search_people(me, "alice")
    assert [r["id"] for r in results] == [alice]
    assert results[0]["visibility"] == "private"


def test_finds_private_user_by_display_name_prefix(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    bob = _make_user(db_path, "xq42", display_name="Bobby Tables", visibility="private")
    results = search.search_people(me, "Bobby")
    assert [r["id"] for r in results] == [bob]


def test_finds_public_user(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "publicpete", visibility="public")
    results = search.search_people(me, "public")
    assert [r["id"] for r in results] == [pub]
    assert results[0]["visibility"] == "public"


def test_result_exposes_only_allowed_keys(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    alice = _make_user(db_path, "alice")
    # Give alice an activity + tag so any accidental join would surface data.
    act = _make_activity(db_path, alice, "Kendo", "kendo")
    _make_tag(db_path, alice, act, "footwork")
    results = search.search_people(me, "alice")
    assert len(results) == 1
    row = results[0]
    assert set(row.keys()) == PEOPLE_KEYS
    # Explicitly assert no activity/entry/tag leakage.
    for forbidden in ("activity", "activity_slug", "activity_name", "tag", "entry", "memo", "slug"):
        assert forbidden not in row


def test_relationship_state_per_result(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    fellow = _make_user(db_path, "afellow")
    pending = _make_user(db_path, "apending")
    stranger = _make_user(db_path, "astranger")

    # me -> fellow: accepted (fellow)
    connections.send_request(me, fellow)
    connections.accept(fellow, me)
    # me -> pending: pending outgoing
    connections.send_request(me, pending)

    results = {r["id"]: r["relationship_state"] for r in search.search_people(me, "a")}
    assert results[fellow] == "fellow"
    assert results[pending] == "pending_outgoing"
    assert results[stranger] == "none"


def test_blocked_user_either_direction_absent(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    iblocked = _make_user(db_path, "ablockee")
    blockedme = _make_user(db_path, "ablocker")
    visible = _make_user(db_path, "avisible")

    connections.block(me, iblocked)  # I blocked them
    connections.block(blockedme, me)  # they blocked me

    ids = [r["id"] for r in search.search_people(me, "a")]
    assert iblocked not in ids
    assert blockedme not in ids
    assert visible in ids


def test_searcher_themselves_absent(db_path: Path) -> None:
    me = _make_user(db_path, "alexandra")
    other = _make_user(db_path, "alexa")
    ids = [r["id"] for r in search.search_people(me, "alex")]
    assert me not in ids
    assert other in ids


def test_guests_absent(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    _make_guest(db_path)
    real = _make_user(db_path, "realuser")
    ids = [r["id"] for r in search.search_people(me, "")]
    # blank short-circuits; do a real prefix that the guest could never match.
    ids = [r["id"] for r in search.search_people(me, "real")]
    assert ids == [real]


def test_wildcard_chars_treated_literally(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    # These would all match-all if % / _ were active wildcards.
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    # A literal '%' query matches nothing (no username starts with '%').
    assert search.search_people(me, "%") == []
    assert search.search_people(me, "_") == []
    # Sanity: a real prefix still works and didn't return everyone.
    ids = {r["id"] for r in search.search_people(me, "alic")}
    assert ids == {a}
    assert b not in ids


def test_results_capped_at_limit(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    for i in range(10):
        _make_user(db_path, f"user{i:02d}")
    results = search.search_people(me, "user", limit=3)
    assert len(results) == 3


def test_limit_clamped_to_max(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    for i in range(5):
        _make_user(db_path, f"user{i:02d}")
    # An absurd limit is clamped, but with only 5 matches we just get 5.
    results = search.search_people(me, "user", limit=10_000)
    assert len(results) == 5


# ---------------------------------------------------------------------------
# Tag search (public-only)
# ---------------------------------------------------------------------------


def test_tag_blank_query_returns_empty(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    assert search.search_tags_public(me, "") == []
    assert search.search_tags_public(me, "  ") == []


def test_tag_on_private_account_returns_nothing(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    priv = _make_user(db_path, "privuser", visibility="private")
    act = _make_activity(db_path, priv, "Kendo", "kendo")
    _make_tag(db_path, priv, act, "footwork")
    assert search.search_tags_public(me, "foot") == []


def test_tag_on_public_account_returns_activity(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    act = _make_activity(db_path, pub, "Kendo", "kendo")
    _make_tag(db_path, pub, act, "footwork")

    results = search.search_tags_public(me, "foot")
    assert len(results) == 1
    row = results[0]
    assert row == {
        "username": "pubuser",
        "activity_slug": "kendo",
        "activity_name": "Kendo",
        "tag": "footwork",
    }


def test_tag_search_ignores_memo_and_entry_text(db_path: Path) -> None:
    """A memo equal to the query string must NEVER surface in tag search."""
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    act = _make_activity(db_path, pub, "Kendo", "kendo")
    # The tag is 'footwork'; seed a memo whose text IS the search string.
    _make_tag(db_path, pub, act, "footwork")
    _make_entry_with_memo(db_path, pub, act, "secretquery")

    # Searching the memo text returns nothing — only tag names are matched.
    assert search.search_tags_public(me, "secretquery") == []
    # And the real tag still matches, proving the search works at all.
    assert len(search.search_tags_public(me, "foot")) == 1


def test_tag_search_excludes_blocked_public_owner(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    other = _make_user(db_path, "otherpub", visibility="public")
    act_blocked = _make_activity(db_path, pub, "Kendo", "kendo")
    _make_tag(db_path, pub, act_blocked, "footwork")
    act_ok = _make_activity(db_path, other, "Sparring", "sparring")
    _make_tag(db_path, other, act_ok, "footwork")

    connections.block(me, pub)

    results = search.search_tags_public(me, "foot")
    usernames = {r["username"] for r in results}
    assert "pubuser" not in usernames
    assert "otherpub" in usernames


def test_tag_search_excludes_blocked_either_direction(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    act = _make_activity(db_path, pub, "Kendo", "kendo")
    _make_tag(db_path, pub, act, "footwork")

    connections.block(pub, me)  # they blocked me
    assert search.search_tags_public(me, "foot") == []


def test_tag_search_wildcards_literal(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    act = _make_activity(db_path, pub, "Kendo", "kendo")
    _make_tag(db_path, pub, act, "footwork")
    assert search.search_tags_public(me, "%") == []


def test_tag_search_dedupes(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    act = _make_activity(db_path, pub, "Kendo", "kendo")
    # Two distinct tag rows with the same name on the same activity (different
    # field_defs) collapse to a single result.
    _make_tag(db_path, pub, act, "footwork")
    _make_tag(db_path, pub, act, "footwork")
    results = search.search_tags_public(me, "foot")
    assert len(results) == 1


def test_tag_search_excludes_archived_tag_and_activity(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    # Archived activity
    act_arch = _make_activity(db_path, pub, "Old", "old")
    _make_tag(db_path, pub, act_arch, "footwork")
    conn = _raw(db_path)
    conn.execute("UPDATE activity SET archived_at = '2026-01-01' WHERE id = ?", (act_arch,))
    conn.commit()
    conn.close()
    assert search.search_tags_public(me, "foot") == []


def test_tag_search_capped(db_path: Path) -> None:
    me = _make_user(db_path, "me")
    pub = _make_user(db_path, "pubuser", visibility="public")
    for i in range(10):
        act = _make_activity(db_path, pub, f"Act{i:02d}", f"act{i:02d}")
        _make_tag(db_path, pub, act, f"foot{i:02d}")
    results = search.search_tags_public(me, "foot", limit=3)
    assert len(results) == 3
