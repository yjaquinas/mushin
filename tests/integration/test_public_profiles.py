"""Integration tests for the public profile routes.

Covers ``GET /@{username}`` and ``GET /@{username}/{slug}``:

1. 404 for unknown usernames and for guest accounts (no username).
2. A private account's profile renders the limited character sheet (activity
   names/levels, no entries/notes, cards not clickable) — no PROFILE_PRIVATE
   stub anymore (three-tier visibility).
3. A public account's profile lists its non-archived activities with
   read-only summaries, linking to ``/@{username}/{slug}``.
4. A public account's activity detail renders read-only stats/history
   including memo text from entries.
5. An unknown slug doesn't leak data; a slug for a private account
   303-redirects a non-connected viewer back to the profile.
6. No write-capable forms/links anywhere on either template (anonymous).
7. Owner viewing ``/@{username}/{slug}`` gets the full dashboard with write
   affordances (log form, HTMX triggers).
8. ``?as=stranger``/``?as=visitor`` forces the read-only (or redirect) view
   even for the owner, never showing more than that real viewer class would
   see; ``?as=connection`` previews the connected/full view.
9. Public-account owners see ACTIVITY_PUBLIC_NOTICE and both preview links;
   private-account owners see neither.
10. ``GET /activities/{id}`` for an active owned sub-tally → 301 redirect to
    ``/@{username}/{slug}``.
11. ``GET /activities/{id}`` for an archived owned sub-tally → 200 (in-place).
12. ``GET /activities/{id}`` for a sub-tally not owned by the session → 404.
13. A fellow (accepted + consented connection) sees the full profile/detail
    on a private account, including entries/notes.
14. A blocked viewer gets 404 on both routes, for public AND private
    accounts — identical to a non-existent user.

These routes must work with NO session cookie for the visitor/anonymous
tests — those tests use a fresh, cookie-less client. Owner-view tests use a
client that has authenticated via ``POST /auth/signup``.
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
from app.services import connections, entries, seeding

_UTC = ZoneInfo("UTC")


@pytest.fixture
def public_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(public_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def _create_account(username: str, *, visibility: str) -> int:
    """Create a username/password account with *visibility*, seeded with starters."""
    owner_id = users.create_username_user(username, "argon2-fake-hash")
    users.set_visibility_consent(owner_id, visibility)
    seeding.seed_account(owner_id)
    return owner_id


def _first_activity(owner_id: int) -> tuple[int, str]:
    """Return (id, slug) of the owner's first active sub-tally."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, slug FROM activity WHERE owner_id = ? AND archived_at IS NULL"
            " ORDER BY id LIMIT 1",
            (owner_id,),
        ).fetchone()
    return int(row["id"]), row["slug"]


# ---------------------------------------------------------------------------
# GET /@{username}
# ---------------------------------------------------------------------------


async def test_unknown_username_404s(client: AsyncClient) -> None:
    resp = await client.get("/@nobody")
    assert resp.status_code == 404


async def test_guest_username_404s(client: AsyncClient) -> None:
    resp = await client.post("/auth/guest")
    assert resp.status_code == 200
    # Guests have no username, so any made-up handle naturally won't match —
    # but verify directly that get_public_user excludes guest rows even if
    # one somehow had a username.
    user_id = int(resp.json()["user_id"])
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute("UPDATE user SET username = 'sneaky-guest' WHERE id = ?", (user_id,))

    resp2 = await client.get("/@sneaky-guest")
    assert resp2.status_code == 404


async def test_private_account_renders_limited_character_sheet(client: AsyncClient) -> None:
    """A private account's profile is the character sheet: activity names +
    levels visible, cards NOT clickable, no entries/notes leaked."""
    _create_account("privateuser", visibility="private")

    resp = await client.get("/@privateuser")
    assert resp.status_code == 200
    body = resp.text
    # Activity names ARE visible on the character sheet (three-tier visibility).
    assert "Kendo" in body
    assert "Reading" in body
    # But cards are not clickable — no link into the activity detail route.
    assert "/@privateuser/" not in body
    assert ui_strings.PROFILE_LIMITED_NOTICE in body


async def test_public_account_lists_activities(client: AsyncClient) -> None:
    _create_account("publicuser", visibility="public")

    resp = await client.get("/@publicuser")
    assert resp.status_code == 200
    body = resp.text
    assert "This record is private." not in body
    # Seeded starter templates should appear with links to their slugs.
    assert "/@publicuser/" in body


async def test_public_profile_has_no_write_affordances(client: AsyncClient) -> None:
    _create_account("nowrites", visibility="public")

    resp = await client.get("/@nowrites")
    assert resp.status_code == 200
    body = resp.text
    # No log forms, no session-only dashboard links, no category/tag editors.
    assert "<form" not in body
    assert "/activities/" not in body
    assert "/log" not in body
    assert "/categories" not in body
    assert "hx-post" not in body


# ---------------------------------------------------------------------------
# GET /@{username}/{slug}
# ---------------------------------------------------------------------------


async def test_activity_detail_for_unknown_slug_404s(client: AsyncClient) -> None:
    _create_account("publicuser2", visibility="public")

    resp = await client.get("/@publicuser2/not-a-real-slug")
    assert resp.status_code == 404


async def test_activity_detail_for_private_account_redirects_to_profile(
    client: AsyncClient,
) -> None:
    """A non-connected visitor forcing the detail URL on a private account
    gets a 303 redirect to the profile — never the detail itself."""
    owner_id = _create_account("privateuser2", visibility="private")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@privateuser2/{slug}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/@privateuser2"


async def test_activity_detail_renders_for_public_account_with_memo(
    client: AsyncClient,
) -> None:
    owner_id = _create_account("publicuser3", visibility="public")
    activity_id, slug = _first_activity(owner_id)

    # Log an entry with a memo (renderer-agnostic service layer, owner-scoped).
    entries.create(
        owner_id,
        activity_id,
        {"tags": [], "values": {}, "memo": "secret training notes"},
        tz=_UTC,
    )

    resp = await client.get(f"/@publicuser3/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert "secret training notes" in body


async def test_activity_detail_has_no_write_affordances(client: AsyncClient) -> None:
    owner_id = _create_account("nowrites2", visibility="public")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@nowrites2/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert "hx-post" not in body
    assert "hx-get" not in body
    assert "<form" not in body
    assert "/log" not in body
    # No link back into the session-only owner dashboard.
    assert "/activities/" not in body


# ---------------------------------------------------------------------------
# Helpers for authenticated (owner-view) tests
# ---------------------------------------------------------------------------


async def _signup_and_set_visibility(client: AsyncClient, username: str, *, visibility: str) -> int:
    """Create an account via the signup route (gets a session cookie), set visibility.

    Returns the new owner_id.
    """
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "test-pw-1234", "consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    owner_id = int(resp.json()["user_id"])
    # Seed the account and set visibility/consent so /home is reachable.
    seeding.seed_account(owner_id)
    users.set_visibility_consent(owner_id, visibility)
    return owner_id


# ---------------------------------------------------------------------------
# Owner view: GET /@{username}/{slug}
# ---------------------------------------------------------------------------


async def test_owner_viewing_own_activity_gets_dashboard(client: AsyncClient) -> None:
    """Owner visiting /@{username}/{slug} → 200 with the log form (write affordance)."""
    owner_id = await _signup_and_set_visibility(client, "ownertest1", visibility="public")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@ownertest1/{slug}")
    assert resp.status_code == 200
    body = resp.text
    # The owner dashboard has the log button / log form trigger.
    assert ui_strings.SUBTALLY_LOG_BUTTON in body
    # HTMX write affordance present.
    assert "hx-get" in body


async def test_non_owner_authenticated_gets_readonly_view(client: AsyncClient) -> None:
    """Another logged-in user visiting the URL gets the read-only viewer, no log form."""
    # Create the profile owner (not logged into the client).
    profile_owner_id = _create_account("profileowner1", visibility="public")
    _, slug = _first_activity(profile_owner_id)

    # Log in as a different user.
    await _signup_and_set_visibility(client, "otheruser1", visibility="public")

    resp = await client.get(f"/@profileowner1/{slug}")
    assert resp.status_code == 200
    body = resp.text
    # Read-only viewer: no log button.
    assert ui_strings.SUBTALLY_LOG_BUTTON not in body
    assert "hx-post" not in body
    assert "<form" not in body


async def test_anonymous_visitor_public_account_gets_readonly_view(
    client: AsyncClient,
) -> None:
    """Anonymous visitor on a public account → read-only viewer (existing behavior)."""
    owner_id = _create_account("anontest1", visibility="public")
    _, slug = _first_activity(owner_id)

    # Clear session cookie to simulate anonymous visitor.
    client.cookies.clear()

    resp = await client.get(f"/@anontest1/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.SUBTALLY_LOG_BUTTON not in body
    assert "<form" not in body


async def test_anonymous_visitor_private_account_gets_redirected(client: AsyncClient) -> None:
    """Anonymous visitor on a private account forcing detail → 303 to profile."""
    owner_id = _create_account("privateanon1", visibility="private")
    _, slug = _first_activity(owner_id)

    client.cookies.clear()

    resp = await client.get(f"/@privateanon1/{slug}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/@privateanon1"


async def test_owner_as_visitor_public_account_gets_readonly_view(
    client: AsyncClient,
) -> None:
    """Owner visiting with ?as=visitor → read-only view (no log form)."""
    owner_id = await _signup_and_set_visibility(client, "ownerpreview1", visibility="public")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@ownerpreview1/{slug}?as=visitor")
    assert resp.status_code == 200
    body = resp.text
    # Read-only viewer — log form must be absent.
    assert ui_strings.SUBTALLY_LOG_BUTTON not in body
    assert "<form" not in body


async def test_owner_as_visitor_private_account_gets_redirected(client: AsyncClient) -> None:
    """Owner previewing ?as=visitor (stranger alias) on a private account →
    303 to the profile, same as a real stranger would get — a preview can
    never show more than the real viewer class would see."""
    owner_id = await _signup_and_set_visibility(client, "ownerpreview2", visibility="private")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@ownerpreview2/{slug}?as=visitor", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/@ownerpreview2"


async def test_non_owner_as_visitor_param_is_noop(client: AsyncClient) -> None:
    """?as=visitor is a no-op for a non-owner — still read-only."""
    profile_owner_id = _create_account("profileowner2", visibility="public")
    _, slug = _first_activity(profile_owner_id)

    # Log in as a different user.
    await _signup_and_set_visibility(client, "otheruser2", visibility="public")

    resp = await client.get(f"/@profileowner2/{slug}?as=visitor")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.SUBTALLY_LOG_BUTTON not in body
    assert "<form" not in body


async def test_public_account_owner_sees_public_notice(client: AsyncClient) -> None:
    """Public-account owner gets ACTIVITY_PUBLIC_NOTICE and the preview link."""
    owner_id = await _signup_and_set_visibility(client, "publicnotice1", visibility="public")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@publicnotice1/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.ACTIVITY_PUBLIC_NOTICE in body
    assert ui_strings.ACTIVITY_PREVIEW_VISITOR in body
    assert ui_strings.ACTIVITY_PREVIEW_CONNECTION in body
    assert f"/@publicnotice1/{slug}?as=stranger" in body
    assert f"/@publicnotice1/{slug}?as=connection" in body


async def test_private_account_owner_sees_no_public_notice(client: AsyncClient) -> None:
    """Private-account owner does NOT see ACTIVITY_PUBLIC_NOTICE or the preview link."""
    owner_id = await _signup_and_set_visibility(client, "privatenotice1", visibility="private")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@privatenotice1/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.ACTIVITY_PUBLIC_NOTICE not in body
    assert ui_strings.ACTIVITY_PREVIEW_VISITOR not in body


# ---------------------------------------------------------------------------
# GET /activities/{activity_id} redirect and fallback
# ---------------------------------------------------------------------------


async def test_activities_route_redirects_active_slugged_activity(
    client: AsyncClient,
) -> None:
    """Active owned sub-tally → 301 redirect to /@{username}/{slug}."""
    owner_id = await _signup_and_set_visibility(client, "redirecttest1", visibility="private")
    activity_id, slug = _first_activity(owner_id)

    resp = await client.get(f"/activities/{activity_id}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/@redirecttest1/{slug}"


async def test_activities_route_archived_renders_in_place(client: AsyncClient) -> None:
    """Archived sub-tally → 200 (rendered in place, no redirect)."""
    owner_id = await _signup_and_set_visibility(client, "archivedtest1", visibility="private")
    activity_id, _ = _first_activity(owner_id)

    # Archive the sub-tally directly.
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE activity SET archived_at = datetime('now') WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        )

    resp = await client.get(f"/activities/{activity_id}", follow_redirects=False)
    assert resp.status_code == 200


async def test_activities_route_other_owners_activity_is_404(client: AsyncClient) -> None:
    """Sub-tally belonging to another user → 404 (not the session user's)."""
    other_owner_id = _create_account("otherown1", visibility="private")
    other_activity_id, _ = _first_activity(other_owner_id)

    # Log in as a different user.
    await _signup_and_set_visibility(client, "currentuser1", visibility="private")

    resp = await client.get(f"/activities/{other_activity_id}", follow_redirects=False)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Fellows: a consented connection sees the full record on a private account.
# ---------------------------------------------------------------------------


async def test_fellow_sees_full_profile_on_private_account(client: AsyncClient) -> None:
    """An accepted+consented fellow sees clickable cards on a private profile
    (not the limited character sheet)."""
    owner_id = _create_account("fellowowner1", visibility="private")
    viewer_id = await _signup_and_set_visibility(client, "fellowviewer1", visibility="private")

    connections.send_request(viewer_id, owner_id)
    connections.accept(owner_id, viewer_id)

    resp = await client.get("/@fellowowner1")
    assert resp.status_code == 200
    body = resp.text
    assert "/@fellowowner1/" in body  # clickable card link present
    assert ui_strings.PROFILE_LIMITED_NOTICE not in body


async def test_fellow_sees_entries_and_notes_on_private_activity_detail(
    client: AsyncClient,
) -> None:
    """A fellow opening /@{username}/{slug} on a private account sees the
    full read-only detail, including memo text."""
    owner_id = _create_account("fellowowner2", visibility="private")
    activity_id, slug = _first_activity(owner_id)
    entries.create(
        owner_id,
        activity_id,
        {"tags": [], "values": {}, "memo": "fellow-visible notes"},
        tz=_UTC,
    )

    viewer_id = await _signup_and_set_visibility(client, "fellowviewer2", visibility="private")
    connections.send_request(viewer_id, owner_id)
    connections.accept(owner_id, viewer_id)

    resp = await client.get(f"/@fellowowner2/{slug}")
    assert resp.status_code == 200
    body = resp.text
    assert "fellow-visible notes" in body
    # Still read-only — no write affordances.
    assert "<form" not in body
    assert "hx-post" not in body


async def test_pending_unaccepted_connection_is_not_a_fellow(client: AsyncClient) -> None:
    """A pending (not yet accepted) request does NOT unlock fellow access —
    the viewer falls through to the account's own limited/public state."""
    owner_id = _create_account("pendingowner1", visibility="private")
    viewer_id = await _signup_and_set_visibility(client, "pendingviewer1", visibility="private")

    connections.send_request(viewer_id, owner_id)
    # Not accepted yet.

    resp = await client.get("/@pendingowner1")
    assert resp.status_code == 200
    assert ui_strings.PROFILE_LIMITED_NOTICE in resp.text


# ---------------------------------------------------------------------------
# Blocked viewer: 404 on both routes, public AND private accounts — no
# existence oracle.
# ---------------------------------------------------------------------------


async def test_blocked_viewer_gets_404_on_private_profile(client: AsyncClient) -> None:
    owner_id = _create_account("blockedowner1", visibility="private")
    viewer_id = await _signup_and_set_visibility(client, "blockedviewer1", visibility="private")

    connections.block(owner_id, viewer_id)

    resp = await client.get("/@blockedowner1")
    assert resp.status_code == 404


async def test_blocked_viewer_gets_404_on_public_profile(client: AsyncClient) -> None:
    """A block overrides public visibility too — blocked viewers see nothing."""
    owner_id = _create_account("blockedowner2", visibility="public")
    viewer_id = await _signup_and_set_visibility(client, "blockedviewer2", visibility="public")

    connections.block(owner_id, viewer_id)

    resp = await client.get("/@blockedowner2")
    assert resp.status_code == 404


async def test_blocked_viewer_gets_404_on_activity_detail(client: AsyncClient) -> None:
    owner_id = _create_account("blockedowner3", visibility="public")
    _, slug = _first_activity(owner_id)
    viewer_id = await _signup_and_set_visibility(client, "blockedviewer3", visibility="public")

    connections.block(owner_id, viewer_id)

    resp = await client.get(f"/@blockedowner3/{slug}")
    assert resp.status_code == 404


async def test_blocking_viewer_also_cannot_see_blocker(client: AsyncClient) -> None:
    """A block silences both directions: the blocker also gets 404 viewing
    the blocked party's profile."""
    owner_id = _create_account("blockedowner4", visibility="public")
    viewer_id = await _signup_and_set_visibility(client, "blockedviewer4", visibility="public")

    # viewer blocks owner.
    connections.block(viewer_id, owner_id)

    resp = await client.get("/@blockedowner4")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Owner two-mode preview: ?as=stranger / ?as=connection
# ---------------------------------------------------------------------------


async def test_owner_preview_as_stranger_on_private_shows_limited(client: AsyncClient) -> None:
    """?as=stranger on a private account renders the limited character sheet
    for the owner — exactly what a real anonymous stranger would see."""
    await _signup_and_set_visibility(client, "previewstranger1", visibility="private")

    resp = await client.get("/@previewstranger1?as=stranger")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.PROFILE_LIMITED_NOTICE in body
    assert "/@previewstranger1/" not in body  # cards not clickable


async def test_owner_preview_as_connection_on_private_shows_full(client: AsyncClient) -> None:
    """?as=connection on a private account renders the full (clickable-card)
    view for the owner — what a real fellow would see."""
    await _signup_and_set_visibility(client, "previewconn1", visibility="private")

    resp = await client.get("/@previewconn1?as=connection")
    assert resp.status_code == 200
    body = resp.text
    assert ui_strings.PROFILE_LIMITED_NOTICE not in body
    assert "/@previewconn1/" in body  # clickable card link present


async def test_owner_preview_as_stranger_skips_consent_gate(client: AsyncClient) -> None:
    """Preview mode never detours through the consent gate, even for an
    account that hasn't completed it (real navigation would redirect)."""
    resp = await client.post(
        "/auth/signup",
        data={"username": "previewgate1", "password": "test-pw-1234", "consent": "true"},
    )
    assert resp.status_code == 200
    owner_id = int(resp.json()["user_id"])
    seeding.seed_account(owner_id)
    # Deliberately do NOT call set_visibility_consent — consent_seen_at is
    # still NULL, so real navigation to /@{username} would redirect to
    # /welcome-sharing.

    resp = await client.get("/@previewgate1?as=stranger", follow_redirects=False)
    assert resp.status_code == 200
    assert "/welcome-sharing" not in resp.headers.get("location", "")


async def test_owner_preview_as_connection_on_activity_detail(client: AsyncClient) -> None:
    """?as=connection on a private activity detail renders the read-only
    detail (a fellow could open it), not a redirect."""
    owner_id = await _signup_and_set_visibility(client, "previewconn2", visibility="private")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@previewconn2/{slug}?as=connection", follow_redirects=False)
    assert resp.status_code == 200
    assert "<form" not in resp.text


async def test_owner_preview_as_stranger_on_private_activity_detail_redirects(
    client: AsyncClient,
) -> None:
    """?as=stranger on a private activity detail redirects to the profile —
    a real stranger could not open this detail either."""
    owner_id = await _signup_and_set_visibility(client, "previewstr2", visibility="private")
    _, slug = _first_activity(owner_id)

    resp = await client.get(f"/@previewstr2/{slug}?as=stranger", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/@previewstr2"
