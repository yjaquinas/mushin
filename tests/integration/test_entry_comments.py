"""Integration tests for the entry-comments routes (Task 4 of the entry-comments
build plan: ``meetings/MEETING-2026-06-19-entry-comments/3-BUILD-PLAN.md``).

Covers the route-level/HTTP scenarios for:

  GET  /@{username}/{slug}/entries/{entry_id}/comments
  POST /@{username}/{slug}/entries/{entry_id}/comments
  POST /@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/delete

plus the home-page unseen-badge rendering (the route-level half of Task 2's
``unseen_comment_count``, which already has unit coverage in
``tests/unit/test_comments.py``).

Fixture pattern mirrors ``tests/integration/test_access_control.py`` and
``tests/integration/test_fellows.py``: a fresh migrated temp SQLite DB per
test, ``SESSION_SECRET`` set, an HTTPS base URL so the ``Secure`` session
cookie round-trips through httpx's cookie jar, and a ``_signup`` helper that
also clears the one-time visibility-consent gate via
``users.set_visibility_consent`` so a fresh signup can reach ``/@{username}``
immediately.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app import ui_strings
from app.auth import users
from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import categories, connections, entries
from app.services import comments as comments_service

_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def comments_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client_a(comments_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client_b(comments_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client_c(comments_db: Path) -> AsyncClient:
    """A third client (used for both "logged-out stranger" and "unrelated
    third logged-in user" scenarios, signing up only when the latter is needed)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


async def _signup(client: AsyncClient, username: str, *, visibility: str = "private") -> int:
    """Sign up a username/password account and clear its one-time consent gate.

    Returns the owner_id. The session cookie is stored in *client*'s jar.
    """
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    owner_id = int(resp.json()["user_id"])
    users.set_visibility_consent(owner_id, visibility)
    return owner_id


async def _logout(client: AsyncClient) -> None:
    await client.post("/auth/logout")
    client.cookies.clear()


def _make_activity_with_entry(owner_id: int, *, name: str = "Running") -> tuple[str, int]:
    """Create a fresh activity + one entry for *owner_id*; return (slug, entry_id)."""
    result = categories.create_activity(owner_id, name=name)
    activity_id = result["activity_id"]
    entry = entries.create(owner_id, activity_id, tz=_UTC)
    with db.connect() as conn:
        conn.execute("BEGIN")
        slug = conn.execute("SELECT slug FROM activity WHERE id = ?", (activity_id,)).fetchone()[
            "slug"
        ]
    return slug, entry["id"]


def _comments_url(username: str, slug: str, entry_id: int) -> str:
    return f"/@{username}/{slug}/entries/{entry_id}/comments"


# ---------------------------------------------------------------------------
# Public profile + logged-in non-owner viewer
# ---------------------------------------------------------------------------


async def test_public_profile_logged_in_viewer_sees_composer_and_can_post(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "pub_owner1", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "pub_viewer1")

    url = _comments_url("pub_owner1", slug, entry_id)

    get_resp = await client_b.get(url)
    assert get_resp.status_code == 200
    assert "<form" in get_resp.text
    assert "<textarea" in get_resp.text
    assert "<html" not in get_resp.text

    post_resp = await client_b.post(url, data={"body": "Great session!"})
    assert post_resp.status_code == 200
    assert "Great session!" in post_resp.text

    # The comment persists and shows up on a fresh GET too.
    second_get = await client_b.get(url)
    assert "Great session!" in second_get.text


async def test_public_activity_page_shows_glyph_for_permitted_viewer_at_zero_comments(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """Regression: the row-level comment glyph must render for a permitted
    commenter even when an entry has zero existing comments, so they have a
    way to start the thread. Originally the glyph was gated on
    ``entry.comment_count`` alone, which made the very first comment on any
    entry unreachable from the browser."""
    owner_id = await _signup(client_a, "pub_owner_zero", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "pub_viewer_zero")

    page_resp = await client_b.get(f"/@pub_owner_zero/{slug}")
    assert page_resp.status_code == 200
    assert f"/entries/{entry_id}/comments" in page_resp.text


# ---------------------------------------------------------------------------
# Public profile + logged-out (no session)
# ---------------------------------------------------------------------------


async def test_public_profile_logged_out_sees_read_only_thread_no_composer(
    client_a: AsyncClient, client_b: AsyncClient, client_c: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "pub_owner2", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "pub_viewer2")
    url = _comments_url("pub_owner2", slug, entry_id)

    # A fellow-less but logged-in viewer posts a comment so there's something
    # to read.
    await client_b.post(url, data={"body": "Visible to everyone"})

    # client_c is logged out (never signed up / cleared its cookie jar).
    get_resp = await client_c.get(url)
    assert get_resp.status_code == 200
    assert "Visible to everyone" in get_resp.text
    assert "<form" not in get_resp.text
    assert "<textarea" not in get_resp.text
    assert ui_strings.COMMENTS_LOGIN_TO_COMMENT in get_resp.text

    post_resp = await client_c.post(url, data={"body": "I should not be allowed"})
    assert post_resp.status_code == 403
    # No write occurred.
    final_get = await client_b.get(url)
    assert "I should not be allowed" not in final_get.text


# ---------------------------------------------------------------------------
# Private profile + non-fellow logged-in viewer
# ---------------------------------------------------------------------------


async def test_private_profile_non_fellow_get_and_post_are_rejected(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "priv_owner1", visibility="private")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "priv_viewer1")
    url = _comments_url("priv_owner1", slug, entry_id)

    get_resp = await client_b.get(url)
    assert get_resp.status_code == 404

    post_resp = await client_b.post(url, data={"body": "let me in"})
    assert post_resp.status_code == 404


# ---------------------------------------------------------------------------
# Private profile + accepted+consented fellow
# ---------------------------------------------------------------------------


async def test_private_profile_consented_fellow_can_get_and_post(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "priv_owner2", visibility="private")
    slug, entry_id = _make_activity_with_entry(owner_id)
    fellow_id = await _signup(client_b, "priv_fellow2")

    await client_b.post("/fellows/priv_owner2/connect")
    await client_a.post("/fellows/requests/priv_fellow2/accept")
    assert connections.relationship_state(fellow_id, owner_id) == "fellow"

    url = _comments_url("priv_owner2", slug, entry_id)
    get_resp = await client_b.get(url)
    assert get_resp.status_code == 200
    assert "<form" in get_resp.text
    assert "<textarea" in get_resp.text

    post_resp = await client_b.post(url, data={"body": "Nice progress on this one"})
    assert post_resp.status_code == 200
    assert "Nice progress on this one" in post_resp.text


# ---------------------------------------------------------------------------
# Revoke the fellow connection after a comment exists
# ---------------------------------------------------------------------------


async def test_revoking_fellow_connection_hides_comment_for_former_fellow_not_owner(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "priv_owner3", visibility="private")
    slug, entry_id = _make_activity_with_entry(owner_id)
    fellow_id = await _signup(client_b, "priv_fellow3")

    await client_b.post("/fellows/priv_owner3/connect")
    await client_a.post("/fellows/requests/priv_fellow3/accept")
    assert connections.relationship_state(fellow_id, owner_id) == "fellow"

    url = _comments_url("priv_owner3", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "before the breakup"})
    assert post_resp.status_code == 200
    assert "before the breakup" in post_resp.text

    # Owner removes the connection.
    remove_resp = await client_a.post("/fellows/priv_fellow3/remove")
    assert remove_resp.status_code == 200
    assert connections.relationship_state(fellow_id, owner_id) == "none"

    # Former fellow has lost access -> 404 on the fragment route (matches
    # existing private-entry-detail behavior, never a leak of the comment).
    former_fellow_get = await client_b.get(url)
    assert former_fellow_get.status_code == 404

    # The row itself is never deleted -- the owner still sees it via their own
    # (owner) view of the fragment route.
    owner_get = await client_a.get(url)
    assert owner_get.status_code == 200
    assert "before the breakup" in owner_get.text

    with db.connect() as conn:
        conn.execute("BEGIN")
        raw_count = conn.execute(
            "SELECT COUNT(*) AS n FROM comment WHERE entry_id = ? AND deleted_at IS NULL",
            (entry_id,),
        ).fetchone()["n"]
    assert raw_count == 1


# ---------------------------------------------------------------------------
# Delete: author, owner, and an unrelated third party
# ---------------------------------------------------------------------------


async def test_comment_author_can_soft_delete_own_comment(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "del_owner1", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "del_author1")
    url = _comments_url("del_owner1", slug, entry_id)

    post_resp = await client_b.post(url, data={"body": "delete me later"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        comment_id = conn.execute(
            "SELECT id FROM comment WHERE entry_id = ? ORDER BY id DESC LIMIT 1", (entry_id,)
        ).fetchone()["id"]

    delete_url = f"/@del_owner1/{slug}/entries/{entry_id}/comments/{comment_id}/delete"
    delete_resp = await client_b.post(delete_url)
    assert delete_resp.status_code == 200
    assert "delete me later" not in delete_resp.text


async def test_entry_owner_can_delete_fellows_comment_on_own_entry(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "del_owner2", visibility="private")
    slug, entry_id = _make_activity_with_entry(owner_id)
    fellow_id = await _signup(client_b, "del_fellow2")

    await client_b.post("/fellows/del_owner2/connect")
    await client_a.post("/fellows/requests/del_fellow2/accept")
    assert connections.relationship_state(fellow_id, owner_id) == "fellow"

    url = _comments_url("del_owner2", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "fellow comment"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        comment_id = conn.execute(
            "SELECT id FROM comment WHERE entry_id = ? ORDER BY id DESC LIMIT 1", (entry_id,)
        ).fetchone()["id"]

    delete_url = f"/@del_owner2/{slug}/entries/{entry_id}/comments/{comment_id}/delete"
    delete_resp = await client_a.post(delete_url)
    assert delete_resp.status_code == 200
    assert "fellow comment" not in delete_resp.text


async def test_unrelated_third_user_cannot_delete_comment(
    client_a: AsyncClient, client_b: AsyncClient, client_c: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "del_owner3", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "del_author3")
    await _signup(client_c, "del_stranger3")

    url = _comments_url("del_owner3", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "not yours to delete"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        comment_id = conn.execute(
            "SELECT id FROM comment WHERE entry_id = ? ORDER BY id DESC LIMIT 1", (entry_id,)
        ).fetchone()["id"]

    delete_url = f"/@del_owner3/{slug}/entries/{entry_id}/comments/{comment_id}/delete"
    delete_resp = await client_c.post(delete_url)
    assert delete_resp.status_code == 403

    # Unchanged.
    get_resp = await client_a.get(url)
    assert "not yours to delete" in get_resp.text


async def test_delete_requires_session(client_a: AsyncClient, client_b: AsyncClient) -> None:
    owner_id = await _signup(client_a, "del_owner4", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "del_author4")

    url = _comments_url("del_owner4", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "anonymous cannot delete this"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        comment_id = conn.execute(
            "SELECT id FROM comment WHERE entry_id = ? ORDER BY id DESC LIMIT 1", (entry_id,)
        ).fetchone()["id"]

    await _logout(client_b)
    delete_url = f"/@del_owner4/{slug}/entries/{entry_id}/comments/{comment_id}/delete"
    delete_resp = await client_b.post(delete_url)
    assert delete_resp.status_code == 401


async def test_delete_unknown_comment_404s(client_a: AsyncClient) -> None:
    owner_id = await _signup(client_a, "del_owner5", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)

    delete_url = f"/@del_owner5/{slug}/entries/{entry_id}/comments/999999/delete"
    delete_resp = await client_a.post(delete_url)
    assert delete_resp.status_code == 404


# ---------------------------------------------------------------------------
# Empty/whitespace-only body is rejected (composer + server-side, can't be
# bypassed by a tampered client)
# ---------------------------------------------------------------------------


async def test_posting_empty_body_returns_422(client_a: AsyncClient, client_b: AsyncClient) -> None:
    owner_id = await _signup(client_a, "empty_owner1", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    await _signup(client_b, "empty_viewer1")

    url = _comments_url("empty_owner1", slug, entry_id)
    resp = await client_b.post(url, data={"body": "   "})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Account deletion cascade -- the FK-cascade behavior itself is covered at the
# unit level in tests/unit/test_migration.py
# (test_migration_0012_deleting_author_cascades_comment and
#  test_migration_0012_deleting_entry_owner_cascades_entry_and_comment). This
# confirms the production code path (the auth delete-account route) actually
# removes a comment row when invoked through the real service layer.
# ---------------------------------------------------------------------------


async def test_deleting_commenter_account_removes_their_comment(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "cascade_owner1", visibility="public")
    slug, entry_id = _make_activity_with_entry(owner_id)
    commenter_id = await _signup(client_b, "cascade_commenter1")

    url = _comments_url("cascade_owner1", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "ephemeral comment"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM comment WHERE author_id = ?", (commenter_id,)
        ).fetchone()["n"]
    assert before == 1

    users.delete_user(commenter_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM comment WHERE author_id = ?", (commenter_id,)
        ).fetchone()["n"]
    assert after == 0


# ---------------------------------------------------------------------------
# Home badge: post a comment, owner sees it on repeated home loads, and it
# only clears once the owner visits the dedicated /comments page (not on
# every home load -- see meetings/MEETING-2026-06-20-comment-notifications).
# ---------------------------------------------------------------------------


async def test_home_badge_persists_across_home_loads_and_clears_via_comments_page(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    owner_id = await _signup(client_a, "badge_owner1", visibility="private")
    slug, entry_id = _make_activity_with_entry(owner_id)
    fellow_id = await _signup(client_b, "badge_fellow1")

    await client_b.post("/fellows/badge_owner1/connect")
    await client_a.post("/fellows/requests/badge_fellow1/accept")
    assert connections.relationship_state(fellow_id, owner_id) == "fellow"

    url = _comments_url("badge_owner1", slug, entry_id)
    post_resp = await client_b.post(url, data={"body": "congrats on the streak"})
    assert post_resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        assert comments_service.unseen_comment_count(conn, owner_id) == 1

    # Repeated home loads keep showing the badge -- identified by its
    # content-free aria-label (the count format string is just "{count}",
    # too generic to assert on directly without colliding with unrelated "1"s
    # elsewhere on the page, e.g. the htmx CDN script tag's version pin).
    # Visiting home must NOT advance the watermark (the bug this build fixes).
    first_home = await client_a.get("/home")
    assert first_home.status_code == 200
    assert f'aria-label="{ui_strings.COMMENTS_UNSEEN_ARIA}"' in first_home.text

    second_home = await client_a.get("/home")
    assert second_home.status_code == 200
    assert f'aria-label="{ui_strings.COMMENTS_UNSEEN_ARIA}"' in second_home.text

    with db.connect() as conn:
        conn.execute("BEGIN")
        assert comments_service.unseen_comment_count(conn, owner_id) == 1

    # Visiting the dedicated /comments page advances the watermark.
    comments_page = await client_a.get("/comments")
    assert comments_page.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        assert comments_service.unseen_comment_count(conn, owner_id) == 0
        still_there = conn.execute(
            "SELECT COUNT(*) AS n FROM comment WHERE entry_id = ? AND deleted_at IS NULL",
            (entry_id,),
        ).fetchone()["n"]
    assert still_there == 1

    # Now home reflects the cleared badge.
    third_home = await client_a.get("/home")
    assert third_home.status_code == 200
    assert f'aria-label="{ui_strings.COMMENTS_UNSEEN_ARIA}"' not in third_home.text
