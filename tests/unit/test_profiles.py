"""Unit tests for app.services.profiles (public-profile Phase 1, Task 5).

Acceptance criteria
-------------------
1. ``get_public_user`` returns a dict for a real (non-guest) user, ``None`` for
   an unknown username, and ``None`` for a guest account.
2. ``resolve_activity_slug`` returns the activity id for a valid owner+slug,
   ``None`` for an unknown slug, and ``None`` for a slug owned by someone else.

Each test uses its own fresh migrated SQLite in ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.migrate import run_migrations
from app.services import profiles

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
    auth_provider: str = "email",
    username: str | None = None,
    visibility: str = "private",
) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, visibility) VALUES (?, ?, ?)",
        (auth_provider, username, visibility),
    )
    conn.commit()
    return cur.lastrowid


def _make_activity(
    conn: sqlite3.Connection,
    owner_id: int,
    slug: str,
    *,
    archived: bool = False,
) -> int:
    cat = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
        (owner_id,),
    )
    category_id = cat.lastrowid
    cur = conn.execute(
        "INSERT INTO activity"
        " (owner_id, category_id, name, slug, count_mode, sort_order, archived_at)"
        " VALUES (?, ?, ?, ?, 'running', 0, ?)",
        (owner_id, category_id, slug, slug, "2020-01-01T00:00:00Z" if archived else None),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# get_public_user
# ---------------------------------------------------------------------------


def test_get_public_user_real_user(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    uid = _make_user(conn, username="alice", visibility="public")
    result = profiles.get_public_user(conn, "alice")
    conn.close()
    assert result is not None
    assert result["id"] == uid
    assert result["username"] == "alice"
    assert result["visibility"] == "public"


def test_get_public_user_private_user_still_resolves(tmp_path: Path):
    """A private user still resolves (visibility is returned for the caller)."""
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    _make_user(conn, username="bob", visibility="private")
    result = profiles.get_public_user(conn, "bob")
    conn.close()
    assert result is not None
    assert result["visibility"] == "private"


def test_get_public_user_unknown_username(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    _make_user(conn, username="alice")
    result = profiles.get_public_user(conn, "nobody")
    conn.close()
    assert result is None


def test_get_public_user_guest_returns_none(tmp_path: Path):
    """Even if a guest somehow has a username, it never resolves publicly."""
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    _make_user(conn, auth_provider="guest", username="ghost", visibility="public")
    result = profiles.get_public_user(conn, "ghost")
    conn.close()
    assert result is None


# ---------------------------------------------------------------------------
# resolve_activity_slug
# ---------------------------------------------------------------------------


def test_resolve_activity_slug_valid(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    st_id = _make_activity(conn, owner, "workout")
    result = profiles.resolve_activity_slug(conn, owner, "workout")
    conn.close()
    assert result == st_id


def test_resolve_activity_slug_unknown(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    _make_activity(conn, owner, "workout")
    result = profiles.resolve_activity_slug(conn, owner, "does-not-exist")
    conn.close()
    assert result is None


def test_resolve_activity_slug_wrong_owner(tmp_path: Path):
    """A slug belonging to another owner does not resolve under this owner."""
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner_a = _make_user(conn, username="alice")
    owner_b = _make_user(conn, username="bob")
    _make_activity(conn, owner_a, "workout")
    # owner_b has no 'workout' of their own.
    result = profiles.resolve_activity_slug(conn, owner_b, "workout")
    conn.close()
    assert result is None


def test_resolve_activity_slug_ignores_archived(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    _make_activity(conn, owner, "workout", archived=True)
    result = profiles.resolve_activity_slug(conn, owner, "workout")
    conn.close()
    assert result is None


# ---------------------------------------------------------------------------
# is_owner_viewing
# ---------------------------------------------------------------------------


def test_is_owner_viewing_anonymous_visitor():
    """No current_user_id (anonymous visitor) is never the owner."""
    assert profiles.is_owner_viewing(current_user_id=None, profile_user_id=5) is False


def test_is_owner_viewing_owner_match():
    assert profiles.is_owner_viewing(current_user_id=5, profile_user_id=5) is True


def test_is_owner_viewing_other_user():
    assert profiles.is_owner_viewing(current_user_id=7, profile_user_id=5) is False


# ---------------------------------------------------------------------------
# canonical URL builders
# ---------------------------------------------------------------------------


def test_canonical_profile_url():
    assert profiles.canonical_profile_url("yuki") == "/@yuki"


def test_canonical_activity_url():
    assert profiles.canonical_activity_url("yuki", "kendo") == "/@yuki/kendo"


# ---------------------------------------------------------------------------
# get_activity_for_owner
# ---------------------------------------------------------------------------


def test_get_activity_for_owner_returns_row(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    st_id = _make_activity(conn, owner, "workout")
    result = profiles.get_activity_for_owner(conn, activity_id=st_id, owner_id=owner)
    conn.close()
    assert result is not None
    assert result["id"] == st_id
    assert result["slug"] == "workout"
    assert result["name"] == "workout"
    assert result["archived_at"] is None


def test_get_activity_for_owner_wrong_owner_returns_none(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner_a = _make_user(conn, username="alice")
    owner_b = _make_user(conn, username="bob")
    st_id = _make_activity(conn, owner_a, "workout")
    result = profiles.get_activity_for_owner(conn, activity_id=st_id, owner_id=owner_b)
    conn.close()
    assert result is None


def test_get_activity_for_owner_missing_returns_none(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    result = profiles.get_activity_for_owner(conn, activity_id=99999, owner_id=owner)
    conn.close()
    assert result is None


def test_get_activity_for_owner_returns_archived_row(tmp_path: Path):
    """Unlike resolve_activity_slug, this lookup returns archived rows too —
    the redirect logic needs the archived_at value to decide what to do."""
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner = _make_user(conn, username="alice")
    st_id = _make_activity(conn, owner, "workout", archived=True)
    result = profiles.get_activity_for_owner(conn, activity_id=st_id, owner_id=owner)
    conn.close()
    assert result is not None
    assert result["archived_at"] is not None


# ---------------------------------------------------------------------------
# safe_next_path — the single authority for "is this a safe post-login
# redirect target" (no open-redirect). Pure function, no DB.
# ---------------------------------------------------------------------------


def test_safe_next_path_accepts_plain_relative_path():
    assert profiles.safe_next_path("/@yuki/kendo") == "/@yuki/kendo"


def test_safe_next_path_accepts_root():
    assert profiles.safe_next_path("/") == "/"


def test_safe_next_path_rejects_none():
    assert profiles.safe_next_path(None) is None


def test_safe_next_path_rejects_empty_string():
    assert profiles.safe_next_path("") is None


def test_safe_next_path_rejects_path_without_leading_slash():
    assert profiles.safe_next_path("evil.com/@yuki") is None


def test_safe_next_path_rejects_scheme_relative_double_slash():
    """``//evil.com/...`` has no scheme but a real netloc — browsers treat it
    as "same scheme as the current page", making it a classic open-redirect
    shape that a bare ``startswith("/")`` check alone would miss."""
    assert profiles.safe_next_path("//evil.com/@yuki") is None


def test_safe_next_path_rejects_absolute_http_url():
    assert profiles.safe_next_path("http://evil.com/@yuki") is None


def test_safe_next_path_rejects_absolute_https_url():
    assert profiles.safe_next_path("https://evil.com/@yuki") is None


def test_safe_next_path_rejects_bare_backslash_prefix():
    """``\\\\evil.com`` (no leading ``/``) fails the leading-slash check —
    the same rejection path as any other string that doesn't start with
    ``/``, regardless of what a client might do with backslashes."""
    assert profiles.safe_next_path("\\\\evil.com") is None


def test_safe_next_path_preserves_query_string():
    assert profiles.safe_next_path("/@yuki/kendo?c=5") == "/@yuki/kendo?c=5"
