"""Integration tests for the private-redefinition re-consent gate (Task 4).

The meaning of ``visibility='private'`` changed (three-tier model): a private
page now shows the character sheet to visitors, where it used to show nothing.
Pre-existing private accounts get a one-time "what Private means has changed"
interstitial at ``/visibility-update``; brand-new accounts (and public
accounts) never see it.

Covers:

1. A pre-existing private user (``consent_seen_at`` set,
   ``private_redefinition_seen_at`` NULL) is redirected to
   ``/visibility-update`` on ``GET /home``.
2. Acknowledging stamps the flag, and the gate then fires exactly once — a
   second ``GET /home`` renders in place.
3. A brand-new user who picks ``private`` via ``/welcome-sharing`` never sees
   the interstitial (no double-prompt), because the same write stamps the
   redefinition flag.
4. A public user is unaffected by the gate.

Setup mirrors ``tests/integration/test_web.py``: a fresh migrated temp SQLite
DB per test, ``SESSION_SECRET`` set, and an HTTPS base URL so the ``Secure``
session cookie round-trips through httpx's cookie jar.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

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


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def _signup(client: AsyncClient, username: str) -> int:
    """Create an email account and return its id; opens a session on *client*.

    Signup records the privacy-policy ``consent`` checkbox, but the *visibility*
    consent (``user.consent_seen_at``) is stamped separately by
    ``/welcome-sharing`` — so a fresh signup still has ``consent_seen_at`` NULL.
    Callers set up the exact consent state they need.
    """
    r = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse-battery", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    return int(r.json()["user_id"])


def _force_preexisting_private(db_path: Path, owner_id: int) -> None:
    """Mark *owner_id* as a pre-existing private account.

    Simulates an account that chose ``private`` under the old "nothing shown"
    copy: ``consent_seen_at`` set (they passed first-run consent) but
    ``private_redefinition_seen_at`` still NULL (they never saw the new copy).
    """
    conn = _raw(db_path)
    try:
        conn.execute(
            "UPDATE user SET visibility = 'private', consent_seen_at = '2026-01-01T00:00:00+00:00',"
            " private_redefinition_seen_at = NULL WHERE id = ?",
            (owner_id,),
        )
    finally:
        conn.close()


def _redefinition_seen_at(db_path: Path, owner_id: int) -> str | None:
    conn = _raw(db_path)
    try:
        row = conn.execute(
            "SELECT private_redefinition_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()
        return row["private_redefinition_seen_at"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1 + 2. Pre-existing private user: gated once, then never again
# ---------------------------------------------------------------------------


async def test_preexisting_private_user_redirected_to_visibility_update(
    client: AsyncClient, web_db: Path
) -> None:
    owner_id = await _signup(client, "olduser")
    _force_preexisting_private(web_db, owner_id)

    r = await client.get("/home", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/visibility-update"

    # The interstitial itself renders for this user (not bounced away).
    r2 = await client.get("/visibility-update")
    assert r2.status_code == 200


async def test_acknowledging_stamps_flag_and_gate_fires_exactly_once(
    client: AsyncClient, web_db: Path
) -> None:
    owner_id = await _signup(client, "olduser2")
    _force_preexisting_private(web_db, owner_id)

    # Gate fires before acknowledgement.
    r = await client.get("/home", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/visibility-update"
    assert _redefinition_seen_at(web_db, owner_id) is None

    # Acknowledge → flag stamped, redirected home.
    ack = await client.post("/visibility-update", follow_redirects=False)
    assert ack.status_code == 303
    assert _redefinition_seen_at(web_db, owner_id) is not None

    # Gate no longer fires: /home renders in place (no redirect to the interstitial).
    r2 = await client.get("/home", follow_redirects=False)
    assert r2.status_code == 200

    # A direct revisit to the interstitial is bounced away (one-time).
    r3 = await client.get("/visibility-update", follow_redirects=False)
    assert r3.status_code == 303
    assert r3.headers["location"] != "/visibility-update"


# ---------------------------------------------------------------------------
# 3. Brand-new user picking private via welcome-sharing: no double-prompt
# ---------------------------------------------------------------------------


async def test_new_user_choosing_private_never_sees_interstitial(
    client: AsyncClient, web_db: Path
) -> None:
    owner_id = await _signup(client, "newuser")

    # Brand-new account: first-run gate sends them to welcome-sharing.
    r = await client.get("/home", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/welcome-sharing"

    # They pick private under the *new* copy.
    choose = await client.post(
        "/welcome-sharing", data={"visibility": "private"}, follow_redirects=False
    )
    assert choose.status_code == 303
    # The same write stamped the redefinition flag, so no re-consent is owed.
    assert _redefinition_seen_at(web_db, owner_id) is not None

    # /home now renders in place — never the redefinition interstitial.
    r2 = await client.get("/home", follow_redirects=False)
    assert r2.status_code == 200

    # And the interstitial bounces them away if visited directly.
    r3 = await client.get("/visibility-update", follow_redirects=False)
    assert r3.status_code == 303
    assert r3.headers["location"] != "/visibility-update"


# ---------------------------------------------------------------------------
# 4. Public user is unaffected
# ---------------------------------------------------------------------------


async def test_public_user_unaffected_by_redefinition_gate(
    client: AsyncClient, web_db: Path
) -> None:
    await _signup(client, "publicuser")

    # Choose public via welcome-sharing.
    choose = await client.post(
        "/welcome-sharing", data={"visibility": "public"}, follow_redirects=False
    )
    assert choose.status_code == 303

    # /home renders in place; the private-redefinition gate never applies.
    r = await client.get("/home", follow_redirects=False)
    assert r.status_code == 200


async def test_public_preexisting_user_unaffected_even_without_flag(
    client: AsyncClient, web_db: Path
) -> None:
    """A pre-existing *public* account (consent set, redefinition flag NULL) is
    not gated — the redefinition only concerns the meaning of ``private``."""
    owner_id = await _signup(client, "oldpublic")
    conn = _raw(web_db)
    try:
        conn.execute(
            "UPDATE user SET visibility = 'public', consent_seen_at = '2026-01-01T00:00:00+00:00',"
            " private_redefinition_seen_at = NULL WHERE id = ?",
            (owner_id,),
        )
    finally:
        conn.close()

    r = await client.get("/home", follow_redirects=False)
    assert r.status_code == 200
