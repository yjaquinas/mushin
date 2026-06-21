"""Unit tests for app.services.comments + profiles.can_comment_on_entry (Task 2).

Acceptance criteria
-------------------
1. ``can_comment_on_entry`` returns ``False`` for any unauthenticated caller
   (``current_user_id=None``), regardless of profile visibility.
2. ``can_comment_on_entry`` matches ``can_view_activity_detail`` exactly across
   the visibility/fellow/block matrix: public, private+non-fellow,
   private+fellow+consented, private+fellow+NOT-consented, blocked.
3. ``list_comments`` returns ``[]`` (not an error) for a viewer who has lost
   access since a comment was posted (revoked connection), while the entry
   owner still sees it — proves hide-not-delete.
4. ``soft_delete_comment`` succeeds for the author, succeeds for the entry
   owner, and raises for an unrelated third user.
5. ``unseen_comment_count`` excludes the owner's own comments on their own
   entries, excludes soft-deleted comments, and treats a NULL watermark as
   "everything is unseen".

Fixture pattern mirrors ``tests/unit/test_profiles_capability.py`` and
``tests/unit/test_categories.py``: a fresh migrated SQLite per test in
``tmp_path``, raw connections, connection/block rows inserted directly with the
canonical ``(MIN, MAX)`` pair.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import comments, profiles
from app.services.comments import CommentNotFoundError, CommentPermissionError

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


def _make_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    visibility: str = "private",
    auth_provider: str = "email",
) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, visibility) VALUES (?, ?, ?)",
        (auth_provider, username, visibility),
    )
    conn.commit()
    return cur.lastrowid


def _profile_dict(uid: int, visibility: str) -> dict:
    return {"id": uid, "visibility": visibility}


def _make_connection(
    conn: sqlite3.Connection,
    requester_id: int,
    addressee_id: int,
    *,
    status: str,
    consented: bool,
) -> None:
    lo, hi = (
        (requester_id, addressee_id)
        if requester_id < addressee_id
        else (addressee_id, requester_id)
    )
    conn.execute(
        "INSERT INTO connection"
        " (requester_id, addressee_id, status, user_lo, user_hi, sharing_consent_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            requester_id,
            addressee_id,
            status,
            lo,
            hi,
            "2026-01-01T00:00:00Z" if consented else None,
        ),
    )
    conn.commit()


def _remove_connection(conn: sqlite3.Connection, a: int, b: int) -> None:
    lo, hi = (a, b) if a < b else (b, a)
    conn.execute("DELETE FROM connection WHERE user_lo = ? AND user_hi = ?", (lo, hi))
    conn.commit()


def _make_block(conn: sqlite3.Connection, blocker_id: int, blocked_id: int) -> None:
    conn.execute(
        "INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)",
        (blocker_id, blocked_id),
    )
    conn.commit()


def _make_activity(conn: sqlite3.Connection, owner_id: int, *, name: str = "Kendo") -> int:
    """Insert a category + activity for *owner_id*, return the activity id."""
    cat = conn.execute(
        "INSERT INTO category (owner_id, name) VALUES (?, ?)", (owner_id, name)
    ).lastrowid
    cur = conn.execute(
        "INSERT INTO activity (owner_id, category_id, name, slug, count_mode)"
        " VALUES (?, ?, ?, ?, 'running')",
        (owner_id, cat, name, name.lower()),
    )
    conn.commit()
    return cur.lastrowid


def _make_entry(conn: sqlite3.Connection, owner_id: int, activity_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO entry (owner_id, activity_id, occurred_at) VALUES (?, ?, ?)",
        (owner_id, activity_id, "2026-06-16T00:00:00Z"),
    )
    conn.commit()
    return cur.lastrowid


def _set_watermark(conn: sqlite3.Connection, user_id: int, value: str | None) -> None:
    conn.execute("UPDATE user SET comments_seen_at = ? WHERE id = ?", (value, user_id))
    conn.commit()


# ---------------------------------------------------------------------------
# 1. can_comment_on_entry — unauthenticated is always False
# ---------------------------------------------------------------------------


def test_can_comment_anonymous_on_public_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    activity_id = _make_activity(conn, owner)
    ok = profiles.can_comment_on_entry(
        conn,
        current_user_id=None,
        profile_user=_profile_dict(owner, "public"),
        activity_id=activity_id,
    )
    conn.close()
    # Anonymous viewer can READ a public profile but never comment.
    assert ok is False


def test_can_comment_anonymous_on_private_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="private")
    activity_id = _make_activity(conn, owner)
    ok = profiles.can_comment_on_entry(
        conn,
        current_user_id=None,
        profile_user=_profile_dict(owner, "private"),
        activity_id=activity_id,
    )
    conn.close()
    assert ok is False


# ---------------------------------------------------------------------------
# 2. can_comment_on_entry matches can_view_activity_detail across the matrix
#    (for an authenticated viewer).
# ---------------------------------------------------------------------------


def _assert_matches_detail(conn, viewer, owner, visibility, activity_id):
    detail = profiles.can_view_activity_detail(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, visibility)
    )
    comment = profiles.can_comment_on_entry(
        conn,
        current_user_id=viewer,
        profile_user=_profile_dict(owner, visibility),
        activity_id=activity_id,
    )
    assert comment == detail
    return comment


def test_can_comment_matches_detail_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    activity_id = _make_activity(conn, owner)
    assert _assert_matches_detail(conn, viewer, owner, "public", activity_id) is True
    conn.close()


def test_can_comment_matches_detail_private_non_fellow(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    activity_id = _make_activity(conn, owner)
    assert _assert_matches_detail(conn, viewer, owner, "private", activity_id) is False
    conn.close()


def test_can_comment_matches_detail_private_fellow_consented(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    activity_id = _make_activity(conn, owner)
    _make_connection(conn, viewer, owner, status="accepted", consented=True)
    assert _assert_matches_detail(conn, viewer, owner, "private", activity_id) is True
    conn.close()


def test_can_comment_matches_detail_private_fellow_not_consented(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    activity_id = _make_activity(conn, owner)
    _make_connection(conn, viewer, owner, status="accepted", consented=False)
    # accepted-without-consent is NOT a fellow -> cannot view detail -> cannot comment.
    assert _assert_matches_detail(conn, viewer, owner, "private", activity_id) is False
    conn.close()


def test_can_comment_matches_detail_blocked(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    activity_id = _make_activity(conn, owner)
    _make_block(conn, owner, viewer)  # block overrides public visibility
    assert _assert_matches_detail(conn, viewer, owner, "public", activity_id) is False
    conn.close()


def test_owner_can_comment_on_own_entry(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="private")
    activity_id = _make_activity(conn, owner)
    assert _assert_matches_detail(conn, owner, owner, "private", activity_id) is True
    conn.close()


# ---------------------------------------------------------------------------
# 3. list_comments — hide-not-delete: revoked viewer gets [], owner still sees it
# ---------------------------------------------------------------------------


def test_list_comments_returns_visible_for_fellow(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="private")
    fellow = _make_user(conn, username="f")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    _make_connection(conn, fellow, owner, status="accepted", consented=True)

    comments.create_comment(conn, entry_id, author_id=fellow, body="Nice progress!")
    conn.commit()

    rows = comments.list_comments(conn, entry_id, viewer_id=fellow)
    conn.close()
    assert len(rows) == 1
    assert rows[0]["body"] == "Nice progress!"
    assert rows[0]["author_id"] == fellow
    assert rows[0]["author_username"] == "f"


def test_list_comments_empty_after_connection_revoked(tmp_path: Path):
    """A fellow posts, then the connection is revoked -> fellow sees []; owner still sees it."""
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="private")
    fellow = _make_user(conn, username="f")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    _make_connection(conn, fellow, owner, status="accepted", consented=True)

    comments.create_comment(conn, entry_id, author_id=fellow, body="Hi there")
    conn.commit()

    # While connected, the fellow can see their comment.
    assert len(comments.list_comments(conn, entry_id, viewer_id=fellow)) == 1

    # Revoke the connection — capability is re-checked live, not cached.
    _remove_connection(conn, fellow, owner)

    # Fellow has lost access: returns [], NOT an error. The row still exists.
    assert comments.list_comments(conn, entry_id, viewer_id=fellow) == []

    # The entry owner still sees the comment (hide-not-delete).
    owner_rows = comments.list_comments(conn, entry_id, viewer_id=owner)
    # The row was never deleted.
    raw_count = conn.execute(
        "SELECT COUNT(*) FROM comment WHERE entry_id = ? AND deleted_at IS NULL", (entry_id,)
    ).fetchone()[0]
    conn.close()
    assert len(owner_rows) == 1
    assert raw_count == 1


def test_list_comments_anonymous_on_private_returns_empty(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="private")
    fellow = _make_user(conn, username="f")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    _make_connection(conn, fellow, owner, status="accepted", consented=True)
    comments.create_comment(conn, entry_id, author_id=fellow, body="secret")
    conn.commit()

    assert comments.list_comments(conn, entry_id, viewer_id=None) == []
    conn.close()


def test_list_comments_excludes_soft_deleted(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    cid1 = comments.create_comment(conn, entry_id, author_id=commenter, body="keep me")
    comments.create_comment(conn, entry_id, author_id=commenter, body="delete me")
    conn.commit()
    comments.soft_delete_comment(conn, cid1 + 1, requester_id=commenter)
    conn.commit()

    rows = comments.list_comments(conn, entry_id, viewer_id=commenter)
    conn.close()
    assert [r["body"] for r in rows] == ["keep me"]


def test_list_comments_unknown_entry_returns_empty(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    rows = comments.list_comments(conn, 999_999, viewer_id=viewer)
    conn.close()
    assert rows == []


# ---------------------------------------------------------------------------
# 4. soft_delete_comment — author OR entry-owner only
# ---------------------------------------------------------------------------


def _is_deleted(conn: sqlite3.Connection, comment_id: int) -> bool:
    row = conn.execute("SELECT deleted_at FROM comment WHERE id = ?", (comment_id,)).fetchone()
    return row["deleted_at"] is not None


def test_soft_delete_by_author_succeeds(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    author = _make_user(conn, username="a")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    cid = comments.create_comment(conn, entry_id, author_id=author, body="mine")
    conn.commit()

    comments.soft_delete_comment(conn, cid, requester_id=author)
    conn.commit()
    assert _is_deleted(conn, cid) is True
    conn.close()


def test_soft_delete_by_entry_owner_succeeds(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    author = _make_user(conn, username="a")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    cid = comments.create_comment(conn, entry_id, author_id=author, body="on my entry")
    conn.commit()

    # The entry owner can moderate a comment on their own entry.
    comments.soft_delete_comment(conn, cid, requester_id=owner)
    conn.commit()
    assert _is_deleted(conn, cid) is True
    conn.close()


def test_soft_delete_by_third_party_raises(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    author = _make_user(conn, username="a")
    stranger = _make_user(conn, username="s")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    cid = comments.create_comment(conn, entry_id, author_id=author, body="not yours")
    conn.commit()

    with pytest.raises(CommentPermissionError):
        comments.soft_delete_comment(conn, cid, requester_id=stranger)
    # Untouched.
    assert _is_deleted(conn, cid) is False
    conn.close()


def test_soft_delete_missing_comment_raises(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o")
    with pytest.raises(CommentNotFoundError):
        comments.soft_delete_comment(conn, 999_999, requester_id=owner)
    conn.close()


def test_soft_delete_already_deleted_raises(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    author = _make_user(conn, username="a")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    cid = comments.create_comment(conn, entry_id, author_id=author, body="x")
    conn.commit()
    comments.soft_delete_comment(conn, cid, requester_id=author)
    conn.commit()
    with pytest.raises(CommentNotFoundError):
        comments.soft_delete_comment(conn, cid, requester_id=author)
    conn.close()


# ---------------------------------------------------------------------------
# 5. unseen_comment_count
# ---------------------------------------------------------------------------


def test_unseen_count_null_watermark_counts_everything(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    comments.create_comment(conn, entry_id, author_id=commenter, body="one")
    comments.create_comment(conn, entry_id, author_id=commenter, body="two")
    conn.commit()
    # Owner's watermark is NULL by default -> everything is unseen.
    assert comments.unseen_comment_count(conn, owner) == 2
    conn.close()


def test_unseen_count_excludes_owns_own_comments(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    # Owner comments on their OWN entry -> never counts toward their badge.
    comments.create_comment(conn, entry_id, author_id=owner, body="self note")
    comments.create_comment(conn, entry_id, author_id=commenter, body="from someone else")
    conn.commit()
    assert comments.unseen_comment_count(conn, owner) == 1
    conn.close()


def test_unseen_count_excludes_soft_deleted(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)
    cid = comments.create_comment(conn, entry_id, author_id=commenter, body="will go")
    comments.create_comment(conn, entry_id, author_id=commenter, body="stays")
    conn.commit()
    comments.soft_delete_comment(conn, cid, requester_id=owner)
    conn.commit()
    assert comments.unseen_comment_count(conn, owner) == 1
    conn.close()


def test_unseen_count_respects_watermark(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    # An older comment that predates the watermark, and a newer one that follows it.
    conn.execute(
        "INSERT INTO comment (entry_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, commenter, "old", "2026-06-01T00:00:00+00:00"),
    )
    conn.commit()
    _set_watermark(conn, owner, "2026-06-10T00:00:00+00:00")
    conn.execute(
        "INSERT INTO comment (entry_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, commenter, "new", "2026-06-15T00:00:00+00:00"),
    )
    conn.commit()
    # Only the comment created strictly after the watermark counts.
    assert comments.unseen_comment_count(conn, owner) == 1
    conn.close()


def test_unseen_count_owner_isolation(tmp_path: Path):
    """A comment on owner A's entry never shows in owner B's unseen count."""
    conn = _raw(_make_db(tmp_path))
    owner_a = _make_user(conn, username="a", visibility="public")
    owner_b = _make_user(conn, username="b", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_a = _make_activity(conn, owner_a)
    entry_a = _make_entry(conn, owner_a, activity_a)
    comments.create_comment(conn, entry_a, author_id=commenter, body="for A")
    conn.commit()
    assert comments.unseen_comment_count(conn, owner_a) == 1
    assert comments.unseen_comment_count(conn, owner_b) == 0
    conn.close()


# ---------------------------------------------------------------------------
# 6. list_comments_for_owner — notification feed
# ---------------------------------------------------------------------------


def _insert_comment_at(
    conn: sqlite3.Connection,
    entry_id: int,
    author_id: int,
    body: str,
    created_at: str,
) -> int:
    """Insert a comment with an explicit created_at, returning its id."""
    cur = conn.execute(
        "INSERT INTO comment (entry_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, author_id, body, created_at),
    )
    conn.commit()
    return cur.lastrowid


def test_list_for_owner_only_returns_own_entries(tmp_path: Path):
    """Never returns comments on another owner's entries."""
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    other = _make_user(conn, username="x", visibility="public")
    commenter = _make_user(conn, username="c")
    my_activity = _make_activity(conn, owner, name="Mine")
    other_activity = _make_activity(conn, other, name="Theirs")
    my_entry = _make_entry(conn, owner, my_activity)
    other_entry = _make_entry(conn, other, other_activity)

    comments.create_comment(conn, my_entry, author_id=commenter, body="on mine")
    comments.create_comment(conn, other_entry, author_id=commenter, body="on theirs")
    conn.commit()

    rows = comments.list_comments_for_owner(conn, owner)
    conn.close()
    assert len(rows) == 1
    assert rows[0]["body"] == "on mine"
    assert rows[0]["entry_id"] == my_entry
    assert rows[0]["activity_name"] == "Mine"
    assert rows[0]["activity_slug"] == "mine"
    assert rows[0]["author_username"] == "c"


def test_list_for_owner_excludes_soft_deleted_and_own_comments(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    # Owner's own comment on their own entry -> excluded.
    comments.create_comment(conn, entry_id, author_id=owner, body="self note")
    # A soft-deleted comment from someone else -> excluded.
    cid_del = comments.create_comment(conn, entry_id, author_id=commenter, body="will go")
    # A live comment from someone else -> the only one returned.
    comments.create_comment(conn, entry_id, author_id=commenter, body="keep me")
    conn.commit()
    comments.soft_delete_comment(conn, cid_del, requester_id=owner)
    conn.commit()

    rows = comments.list_comments_for_owner(conn, owner)
    conn.close()
    assert [r["body"] for r in rows] == ["keep me"]


def test_list_for_owner_ordered_newest_first(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    _insert_comment_at(conn, entry_id, commenter, "oldest", "2026-06-01T00:00:00+00:00")
    _insert_comment_at(conn, entry_id, commenter, "middle", "2026-06-10T00:00:00+00:00")
    _insert_comment_at(conn, entry_id, commenter, "newest", "2026-06-15T00:00:00+00:00")

    rows = comments.list_comments_for_owner(conn, owner)
    conn.close()
    assert [r["body"] for r in rows] == ["newest", "middle", "oldest"]


def test_list_for_owner_limit_and_before_id_cursor(tmp_path: Path):
    """Keyset pagination: second page excludes already-returned rows."""
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    # Five comments, monotonically increasing time -> ids ascend with time.
    for i in range(5):
        _insert_comment_at(
            conn, entry_id, commenter, f"c{i}", f"2026-06-0{i + 1}T00:00:00+00:00"
        )

    page1 = comments.list_comments_for_owner(conn, owner, limit=2)
    assert [r["body"] for r in page1] == ["c4", "c3"]

    cursor = page1[-1]["comment_id"]
    page2 = comments.list_comments_for_owner(conn, owner, limit=2, before_id=cursor)
    assert [r["body"] for r in page2] == ["c2", "c1"]

    cursor2 = page2[-1]["comment_id"]
    page3 = comments.list_comments_for_owner(conn, owner, limit=2, before_id=cursor2)
    conn.close()
    assert [r["body"] for r in page3] == ["c0"]
    # No overlap between pages.
    all_ids = [r["comment_id"] for r in page1 + page2 + page3]
    assert len(all_ids) == len(set(all_ids))


def test_list_for_owner_is_new_respects_watermark(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    _insert_comment_at(conn, entry_id, commenter, "old", "2026-06-01T00:00:00+00:00")
    _insert_comment_at(conn, entry_id, commenter, "new", "2026-06-15T00:00:00+00:00")

    rows = comments.list_comments_for_owner(
        conn, owner, watermark="2026-06-10T00:00:00+00:00"
    )
    conn.close()
    by_body = {r["body"]: r["is_new"] for r in rows}
    assert by_body["new"] is True
    assert by_body["old"] is False


def test_list_for_owner_is_new_true_for_all_when_watermark_none(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    commenter = _make_user(conn, username="c")
    activity_id = _make_activity(conn, owner)
    entry_id = _make_entry(conn, owner, activity_id)

    _insert_comment_at(conn, entry_id, commenter, "old", "2026-06-01T00:00:00+00:00")
    _insert_comment_at(conn, entry_id, commenter, "new", "2026-06-15T00:00:00+00:00")

    rows = comments.list_comments_for_owner(conn, owner, watermark=None)
    conn.close()
    assert all(r["is_new"] is True for r in rows)


def test_list_for_owner_empty_when_no_comments(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    owner = _make_user(conn, username="o", visibility="public")
    _make_activity(conn, owner)
    rows = comments.list_comments_for_owner(conn, owner)
    conn.close()
    assert rows == []
