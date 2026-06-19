"""Integration tests for the one-time visibility-consent screen (Phase 1, Task 3).

Covers:

1. An existing/new non-guest account (``consent_seen_at`` NULL) hitting
   ``GET /home`` is redirected (303) straight to ``GET /welcome-sharing``
   until they submit a choice. (``/home`` renders the dashboard in place for
   anyone with a valid session, after this inline consent-gate check — it is
   not a redirect shim to ``/@{username}``.)
2. Guests bypass the gate entirely — ``GET /home`` renders home directly and
   ``GET /welcome-sharing`` bounces them to ``/home``.
3. ``POST /welcome-sharing`` persists ``visibility`` + ``consent_seen_at`` and
   redirects to the user's canonical destination (``/@{username}`` for named
   accounts, via ``_home_url_for``); ``/home`` then renders in place without
   detouring through the consent gate.
4. An invalid ``visibility`` value is rejected with 400.

Setup mirrors ``tests/integration/test_web.py``: a fresh migrated temp SQLite DB
per test, ``SESSION_SECRET`` set, and an HTTPS base URL so the ``Secure`` session
cookie round-trips through httpx's cookie jar.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import sessions, users
from app.main import app
from app.models import db
from app.models.migrate import run_migrations

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def web_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(web_db: Path) -> AsyncClient:
    """Async client with an HTTPS base URL so the Secure session cookie persists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def _login_as(client: AsyncClient, user_id: int) -> None:
    """Attach a signed session cookie for *user_id* to the client's jar."""
    client.cookies.set(sessions.COOKIE_NAME, sessions.sign_uid(user_id))


def _make_real_user() -> int:
    """Create a username/password account (consent_seen_at NULL at creation)."""
    return users.create_username_user("logger", "argon2-fake-hash")


async def _make_guest(client: AsyncClient) -> int:
    """Mint a guest session and return its owner_id."""
    resp = await client.post("/auth/guest")
    assert resp.status_code == 200
    return int(resp.json()["user_id"])


# ---------------------------------------------------------------------------
# Gate: non-guest with NULL consent is redirected and blocked
# ---------------------------------------------------------------------------


async def test_existing_user_home_redirects_to_welcome_sharing(client: AsyncClient) -> None:
    user_id = _make_real_user()
    _login_as(client, user_id)

    # /home renders in place after the inline consent-gate check — a
    # non-guest account with consent_seen_at NULL is redirected (303)
    # straight to /welcome-sharing.
    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/welcome-sharing"


async def test_new_signup_home_redirects_to_welcome_sharing(client: AsyncClient) -> None:
    # A brand-new signup also has consent_seen_at NULL — same gate.
    resp = await client.post(
        "/auth/signup",
        data={"username": "freshuser", "password": "hunter2hunter2", "consent": "on"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303)
    # The signup flow set a session cookie on the client.
    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/welcome-sharing"


async def test_welcome_sharing_screen_renders_for_gated_user(client: AsyncClient) -> None:
    _login_as(client, _make_real_user())

    resp = await client.get("/welcome-sharing")

    assert resp.status_code == 200
    body = resp.text
    assert 'value="private"' in body
    assert 'value="public"' in body
    # The forward action is the submit button (no skip affordance in the form).
    assert 'type="submit"' in body
    assert "skip" not in body.lower()
    # The masthead logo links to /home, but the gate bounces it straight back —
    # it is not an escape hatch. There is no <a> link out of the consent form
    # itself other than the privacy policy.


async def test_welcome_sharing_private_radio_preselected(client: AsyncClient) -> None:
    _login_as(client, _make_real_user())

    resp = await client.get("/welcome-sharing")

    body = resp.text
    # The private radio carries `checked`; public does not.
    private_idx = body.index('value="private"')
    public_idx = body.index('value="public"')
    # `checked` appears within the private input block, before the public one.
    assert "checked" in body[private_idx : private_idx + 120]
    assert "checked" not in body[public_idx : public_idx + 120]


# ---------------------------------------------------------------------------
# Guests bypass the gate
# ---------------------------------------------------------------------------


async def test_guest_home_renders_directly(client: AsyncClient) -> None:
    await _make_guest(client)

    resp = await client.get("/home", follow_redirects=False)

    assert resp.status_code == 200


async def test_guest_welcome_sharing_bounces_to_home(client: AsyncClient) -> None:
    await _make_guest(client)

    resp = await client.get("/welcome-sharing", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/home"


# ---------------------------------------------------------------------------
# POST persists the choice and unblocks /home
# ---------------------------------------------------------------------------


async def test_submit_private_persists_and_unblocks_home(client: AsyncClient) -> None:
    user_id = _make_real_user()
    _login_as(client, user_id)

    resp = await client.post(
        "/welcome-sharing", data={"visibility": "private"}, follow_redirects=False
    )
    assert resp.status_code == 303
    # This screen is non-guest-only, so the fixture user has a username —
    # the post-consent destination is its canonical profile, not /home.
    assert resp.headers["location"] == "/@logger"

    row = users.get_user(user_id)
    assert row is not None
    assert row["visibility"] == "private"
    assert row["consent_seen_at"] is not None

    # Subsequent /home renders in place (no detour through /welcome-sharing
    # now that consent has been recorded).
    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 200


async def test_submit_public_persists_choice(client: AsyncClient) -> None:
    user_id = _make_real_user()
    _login_as(client, user_id)

    resp = await client.post(
        "/welcome-sharing", data={"visibility": "public"}, follow_redirects=False
    )
    assert resp.status_code == 303

    row = users.get_user(user_id)
    assert row is not None
    assert row["visibility"] == "public"
    assert row["consent_seen_at"] is not None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_submit_invalid_visibility_is_400(client: AsyncClient) -> None:
    user_id = _make_real_user()
    _login_as(client, user_id)

    resp = await client.post(
        "/welcome-sharing", data={"visibility": "everyone"}, follow_redirects=False
    )
    assert resp.status_code == 400

    # Nothing persisted — the user is still gated.
    row = users.get_user(user_id)
    assert row is not None
    assert row["consent_seen_at"] is None


async def test_submit_logged_out_redirects_to_entry(client: AsyncClient) -> None:
    resp = await client.post(
        "/welcome-sharing", data={"visibility": "private"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
