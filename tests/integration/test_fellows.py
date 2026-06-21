"""Integration tests for the fellows/connection-action web routes (Task 6).

Covers:

1. Connection action routes (send/accept/decline/cancel/disconnect/block/
   unblock) as HTMX fragment swaps — no full page reload, each returning a
   200 fragment rather than a 500 on a service exception.
2. The consent-before-mutation gate: sending a request AND accepting one
   each require a GET (consent fragment) -> POST (confirm) round trip; a
   bare POST without ever visiting the GET still works (the consent screen
   is a UI nudge, not a CSRF-style token — see note below) but the dedicated
   GET fragment itself never mutates anything.
3. Names-vs-count visibility: a stranger viewing a profile sees the fellow
   COUNT only; the owner and a mutual fellow see the clickable `@username`
   rows.
4. Pending-request count surfaces to the owner, content-free.

Fixture pattern mirrors ``tests/integration/test_public_profiles.py``: fresh
migrated temp SQLite DB per test, ``SESSION_SECRET`` set, HTTPS base URL.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import ui_strings
from app.auth import users
from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import connections

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fellows_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client_a(fellows_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client_b(fellows_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client_c(fellows_db: Path) -> AsyncClient:
    """A third, unauthenticated client (the "stranger" viewpoint)."""
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


# ---------------------------------------------------------------------------
# Send request (Connect) — consent-gated
# ---------------------------------------------------------------------------


async def test_connect_confirm_shows_sharing_consent_before_mutating(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """GET connect-confirm renders the consent screen and does not send a request."""
    await _signup(client_a, "alice_cc1")
    await _signup(client_b, "bob_cc1")

    resp = await client_a.get("/fellows/bob_cc1/connect-confirm")
    assert resp.status_code == 200
    assert ui_strings.SHARING_CONSENT_TITLE in resp.text
    assert ui_strings.SHARING_CONSENT_CONFIRM in resp.text

    # No request was actually sent by the GET.
    assert (
        connections.relationship_state(
            users.find_by_username("alice_cc1")["id"], users.find_by_username("bob_cc1")["id"]
        )
        == "none"
    )


async def test_connect_post_sends_request_and_returns_requested_fragment(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_cp1")
    await _signup(client_b, "bob_cp1")

    resp = await client_a.post("/fellows/bob_cp1/connect")
    assert resp.status_code == 200
    assert ui_strings.CONNECT_REQUESTED in resp.text
    # Fragment swap target present, not a full <html> document.
    assert "<html" not in resp.text

    alice_id = users.find_by_username("alice_cp1")["id"]
    bob_id = users.find_by_username("bob_cp1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "pending_outgoing"


async def test_connect_duplicate_request_shows_calm_inline_error(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_dup1")
    await _signup(client_b, "bob_dup1")

    first = await client_a.post("/fellows/bob_dup1/connect")
    assert first.status_code == 200
    second = await client_a.post("/fellows/bob_dup1/connect")
    assert second.status_code == 200
    assert ui_strings.CONNECT_ERROR_ALREADY_EXISTS in second.text
    assert "<html" not in second.text


async def test_connect_to_self_is_rejected(client_a: AsyncClient) -> None:
    await _signup(client_a, "alice_self1")
    resp = await client_a.post("/fellows/alice_self1/connect")
    assert resp.status_code == 400


async def test_connect_unknown_username_is_404(client_a: AsyncClient) -> None:
    await _signup(client_a, "alice_unk1")
    resp = await client_a.post("/fellows/doesnotexist999/connect")
    assert resp.status_code == 404


async def test_connect_requires_session(client_c: AsyncClient, client_b: AsyncClient) -> None:
    await _signup(client_b, "bob_nosess1")
    resp = await client_c.post("/fellows/bob_nosess1/connect")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Accept — consent-gated
# ---------------------------------------------------------------------------


async def test_accept_confirm_shows_sharing_consent_before_mutating(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_ac1")
    await _signup(client_b, "bob_ac1")
    await client_a.post("/fellows/bob_ac1/connect")

    resp = await client_b.get("/fellows/requests/alice_ac1/accept-confirm")
    assert resp.status_code == 200
    assert ui_strings.SHARING_CONSENT_TITLE in resp.text
    assert ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT in resp.text

    alice_id = users.find_by_username("alice_ac1")["id"]
    bob_id = users.find_by_username("bob_ac1")["id"]
    # Still pending — the GET must not have accepted it.
    assert connections.relationship_state(alice_id, bob_id) == "pending_outgoing"


async def test_accept_post_confirms_and_becomes_fellow(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_ap1")
    await _signup(client_b, "bob_ap1")
    await client_a.post("/fellows/bob_ap1/connect")

    resp = await client_b.post("/fellows/requests/alice_ap1/accept")
    assert resp.status_code == 200
    assert "<html" not in resp.text

    alice_id = users.find_by_username("alice_ap1")["id"]
    bob_id = users.find_by_username("bob_ap1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "fellow"


async def test_accept_with_no_pending_request_shows_calm_inline_error(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_nopending1")
    await _signup(client_b, "bob_nopending1")

    resp = await client_b.post("/fellows/requests/alice_nopending1/accept")
    assert resp.status_code == 200
    assert ui_strings.CONNECT_ERROR_NOT_FOUND in resp.text


# ---------------------------------------------------------------------------
# Regression: consent fragment must carry its own swap-target id, or the
# fragment's own "Connect as fellows"/"Accept and connect" button can't find
# its hx-target and htmx silently aborts the swap (the bug this guards).
# ---------------------------------------------------------------------------


async def test_connect_confirm_fragment_carries_relationship_affordance_id(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """The connect-confirm fragment's root must carry #relationship-affordance
    itself, since it swaps in via outerHTML in that id's place — otherwise the
    fragment's own buttons (hx-target=#relationship-affordance) have nothing
    to swap into and the click does nothing."""
    await _signup(client_a, "alice_domid1")
    await _signup(client_b, "bob_domid1")

    resp = await client_a.get("/fellows/bob_domid1/connect-confirm")
    assert resp.status_code == 200
    assert 'id="relationship-affordance"' in resp.text

    # Send-side body must not claim exposure already happened.
    assert "Once you're fellows" not in resp.text
    assert ui_strings.SHARING_CONSENT_BODY_SEND in resp.text


async def test_accept_confirm_fragment_carries_fellows_section_id(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """The accept-confirm fragment's root must carry #fellows-section itself
    for the same reason — its own buttons target #fellows-section."""
    await _signup(client_a, "alice_domid2")
    await _signup(client_b, "bob_domid2")
    await client_a.post("/fellows/bob_domid2/connect")

    resp = await client_b.get("/fellows/requests/alice_domid2/accept-confirm")
    assert resp.status_code == 200
    assert 'id="fellows-section"' in resp.text

    # Accept-side body is the real-exposure-moment wording.
    assert ui_strings.SHARING_CONSENT_BODY_ACCEPT in resp.text


async def test_connect_then_accept_full_flow_via_consent_fragments(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """End-to-end through both consent fragments and their confirm POSTs:
    GET connect-confirm -> POST connect -> pending_outgoing; GET
    accept-confirm -> POST accept -> fellow. Exercises the exact swap targets
    the fragments declare for themselves."""
    await _signup(client_a, "alice_fullflow1")
    await _signup(client_b, "bob_fullflow1")

    confirm_resp = await client_a.get("/fellows/bob_fullflow1/connect-confirm")
    assert confirm_resp.status_code == 200
    assert 'id="relationship-affordance"' in confirm_resp.text

    send_resp = await client_a.post("/fellows/bob_fullflow1/connect")
    assert send_resp.status_code == 200

    alice_id = users.find_by_username("alice_fullflow1")["id"]
    bob_id = users.find_by_username("bob_fullflow1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "pending_outgoing"

    accept_confirm_resp = await client_b.get("/fellows/requests/alice_fullflow1/accept-confirm")
    assert accept_confirm_resp.status_code == 200
    assert 'id="fellows-section"' in accept_confirm_resp.text

    accept_resp = await client_b.post("/fellows/requests/alice_fullflow1/accept")
    assert accept_resp.status_code == 200
    assert connections.relationship_state(alice_id, bob_id) == "fellow"


# ---------------------------------------------------------------------------
# Decline / cancel — direct, no confirm step
# ---------------------------------------------------------------------------


async def test_decline_removes_pending_request(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_dec1")
    await _signup(client_b, "bob_dec1")
    await client_a.post("/fellows/bob_dec1/connect")

    resp = await client_b.post("/fellows/requests/alice_dec1/decline")
    assert resp.status_code == 200

    alice_id = users.find_by_username("alice_dec1")["id"]
    bob_id = users.find_by_username("bob_dec1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "none"


async def test_cancel_withdraws_outgoing_request(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_can1")
    await _signup(client_b, "bob_can1")
    await client_a.post("/fellows/bob_can1/connect")

    resp = await client_a.post("/fellows/requests/bob_can1/cancel")
    assert resp.status_code == 200

    alice_id = users.find_by_username("alice_can1")["id"]
    bob_id = users.find_by_username("bob_can1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "none"


# ---------------------------------------------------------------------------
# Disconnect (remove) — two-step inline confirm
# ---------------------------------------------------------------------------


async def test_remove_confirm_then_post_disconnects(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_rm1")
    await _signup(client_b, "bob_rm1")
    await client_a.post("/fellows/bob_rm1/connect")
    await client_b.post("/fellows/requests/alice_rm1/accept")

    confirm = await client_a.get("/fellows/bob_rm1/remove-confirm")
    assert confirm.status_code == 200
    assert ui_strings.CONNECT_REMOVE_CONFIRM_BODY in confirm.text

    alice_id = users.find_by_username("alice_rm1")["id"]
    bob_id = users.find_by_username("bob_rm1")["id"]
    # The confirm GET alone must not have disconnected anything.
    assert connections.relationship_state(alice_id, bob_id) == "fellow"

    resp = await client_a.post("/fellows/bob_rm1/remove")
    assert resp.status_code == 200
    assert connections.relationship_state(alice_id, bob_id) == "none"


# ---------------------------------------------------------------------------
# Block / unblock
# ---------------------------------------------------------------------------


async def test_block_confirm_then_post_blocks_and_tears_down_connection(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice_bl1")
    await _signup(client_b, "bob_bl1")
    await client_a.post("/fellows/bob_bl1/connect")
    await client_b.post("/fellows/requests/alice_bl1/accept")

    confirm = await client_a.get("/fellows/bob_bl1/block-confirm")
    assert confirm.status_code == 200
    assert ui_strings.CONNECT_BLOCK_CONFIRM_BODY in confirm.text

    resp = await client_a.post("/fellows/bob_bl1/block")
    assert resp.status_code == 200
    assert ui_strings.CONNECT_UNBLOCK in resp.text

    alice_id = users.find_by_username("alice_bl1")["id"]
    bob_id = users.find_by_username("bob_bl1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "blocked"


async def test_unblock_is_direct_no_confirm(client_a: AsyncClient, client_b: AsyncClient) -> None:
    await _signup(client_a, "alice_ub1")
    await _signup(client_b, "bob_ub1")
    await client_a.post("/fellows/bob_ub1/block")

    resp = await client_a.post("/fellows/bob_ub1/unblock")
    assert resp.status_code == 200
    assert ui_strings.CONNECT_ACTION in resp.text

    alice_id = users.find_by_username("alice_ub1")["id"]
    bob_id = users.find_by_username("bob_ub1")["id"]
    assert connections.relationship_state(alice_id, bob_id) == "none"


# ---------------------------------------------------------------------------
# Names-vs-count visibility on the fellows section
# ---------------------------------------------------------------------------


async def test_owner_sees_fellow_names_on_own_profile(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "owner_names1", visibility="public")
    await _signup(client_b, "fellow_names1")
    await client_b.post("/fellows/owner_names1/connect")
    await client_a.post("/fellows/requests/fellow_names1/accept")

    resp = await client_a.get("/@owner_names1")
    assert resp.status_code == 200
    assert "@fellow_names1" in resp.text


async def test_mutual_fellow_sees_fellow_names_on_profile(
    client_a: AsyncClient, client_b: AsyncClient, client_c: AsyncClient
) -> None:
    """A viewer who is themselves a mutual fellow of the profile owner sees names."""
    await _signup(client_a, "owner_names2", visibility="public")
    await _signup(client_b, "viewer_names2")
    await _signup(client_c, "other_fellow2")

    # viewer_names2 and other_fellow2 both become fellows of owner_names2.
    await client_b.post("/fellows/owner_names2/connect")
    await client_a.post("/fellows/requests/viewer_names2/accept")
    await client_c.post("/fellows/owner_names2/connect")
    await client_a.post("/fellows/requests/other_fellow2/accept")

    resp = await client_b.get("/@owner_names2")
    assert resp.status_code == 200
    assert "@other_fellow2" in resp.text


async def test_stranger_sees_only_fellow_count_not_names(
    client_a: AsyncClient, client_b: AsyncClient, client_c: AsyncClient
) -> None:
    """A non-fellow, non-owner viewer sees the count but never the clickable names."""
    await _signup(client_a, "owner_count1", visibility="public")
    await _signup(client_b, "fellow_count1")
    await client_b.post("/fellows/owner_count1/connect")
    await client_a.post("/fellows/requests/fellow_count1/accept")

    # client_c is a logged-out stranger.
    resp = await client_c.get("/@owner_count1")
    assert resp.status_code == 200
    assert "@fellow_count1" not in resp.text
    assert ui_strings.FELLOWS_COUNT_LABEL_ONE in resp.text


async def test_logged_in_non_fellow_sees_only_fellow_count(
    client_a: AsyncClient, client_b: AsyncClient, client_c: AsyncClient
) -> None:
    """A logged-in viewer who is NOT a mutual fellow also sees count only."""
    await _signup(client_a, "owner_count2", visibility="public")
    await _signup(client_b, "fellow_count2")
    await _signup(client_c, "stranger_count2")
    await client_b.post("/fellows/owner_count2/connect")
    await client_a.post("/fellows/requests/fellow_count2/accept")

    resp = await client_c.get("/@owner_count2")
    assert resp.status_code == 200
    assert "@fellow_count2" not in resp.text
    assert ui_strings.FELLOWS_COUNT_LABEL_ONE in resp.text


# ---------------------------------------------------------------------------
# Pending-request count (owner-only, content-free)
# ---------------------------------------------------------------------------


async def test_owner_sees_pending_request_count_badge(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "owner_badge1", visibility="public")
    await _signup(client_b, "requester_badge1")
    await client_b.post("/fellows/owner_badge1/connect")

    resp = await client_a.get("/@owner_badge1")
    assert resp.status_code == 200
    assert ui_strings.REQUESTS_HEADING in resp.text
    assert ui_strings.REQUESTS_ACCEPT in resp.text
    assert ui_strings.REQUESTS_DECLINE in resp.text


async def test_non_owner_does_not_see_requests_cluster(
    client_a: AsyncClient, client_c: AsyncClient
) -> None:
    await _signup(client_a, "owner_norequests1", visibility="public")

    resp = await client_c.get("/@owner_norequests1")
    assert resp.status_code == 200
    assert ui_strings.REQUESTS_HEADING not in resp.text
