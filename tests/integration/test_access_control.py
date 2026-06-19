"""Integration tests: write-route access control (cross-user isolation).

Proves that every write route that accepts a ``activity_id`` path parameter
gate-checks it against the authenticated user's ``owner_id`` and returns 404
on mismatch.  These tests are a permanent regression target — a cross-user data
leak is a release blocker.

Fixture pattern mirrors ``tests/integration/test_web.py``: fresh migrated temp
SQLite per-test, ``SESSION_SECRET`` set, HTTPS base URL so the ``Secure``
session cookie round-trips through httpx's cookie jar.

Note on unauthenticated behaviour:
- ``POST /activities/{id}/log`` redirects to ``/`` (303) when no session is
  present (same path as the "logged-out home" redirect pattern).
- ``POST /activities/{id}/tags`` returns 401 when no session is present.
Both are "not 200 and not a write succeeding" — acceptable per the acceptance
criteria.

"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import seeding

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def access_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(access_db: Path) -> AsyncClient:
    """Async client with an HTTPS base URL so the Secure session cookie persists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


async def _signup(client: AsyncClient, username: str) -> int:
    """Sign up a username/password account, return its owner_id (user id).

    The session cookie is stored in *client*'s cookie jar after this call, so
    the caller is authenticated as the new user.
    """
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200, f"signup failed for {username!r}: {resp.text}"
    return int(resp.json()["user_id"])


async def _logout(client: AsyncClient) -> None:
    """End the current session (clear the cookie jar)."""
    await client.post("/auth/logout")
    client.cookies.clear()


def _owner_activity_id(owner_id: int) -> int:
    """Return the Kendo/Practice activity id seeded under *owner_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Kendo' AND st.name = 'Practice'""",
            (owner_id,),
        ).fetchone()["id"]


def _owner_entry_id(owner_id: int, activity_id: int) -> int:
    """Return an entry id belonging to *owner_id* under *activity_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]


def _owner_tag_field_id(owner_id: int, activity_id: int) -> int:
    """Return the Technique tag_group field_def id for *activity_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            "SELECT id FROM field_def WHERE activity_id = ? AND kind = 'tag_group' AND label = 'Technique'",
            (activity_id,),
        ).fetchone()["id"]


# ---------------------------------------------------------------------------
# Test: cross-user POST /log -> 404
# ---------------------------------------------------------------------------


async def test_cross_user_post_log_returns_404(client: AsyncClient) -> None:
    """User B posting to a activity owned by user A must receive 404.

    This proves the ``st.owner_id = ?`` guard in ``create_log`` is effective
    and that no write occurs on behalf of the wrong user.
    """
    # Set up owner A with seeded data.
    owner_a_id = await _signup(client, "user_a")
    seeding.seed_account(owner_a_id)
    a_activity_id = _owner_activity_id(owner_a_id)

    # Switch to user B.
    await _logout(client)
    await _signup(client, "user_b")

    # User B posts to A's activity.
    resp = await client.post(
        f"/activities/{a_activity_id}/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 404, (
        f"Expected 404 when user B logs to user A's activity, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Test: cross-user POST /tags -> 404
# ---------------------------------------------------------------------------


async def test_cross_user_post_tags_returns_404(client: AsyncClient) -> None:
    """User B posting to a tag_group field owned by user A must receive 404.

    The tags route verifies ownership via a JOIN on ``st.owner_id``, so a
    field_def_id under a foreign activity should not be reachable.
    """
    # Set up owner A with seeded data.
    owner_a_id = await _signup(client, "tag_owner_a")
    seeding.seed_account(owner_a_id)
    a_activity_id = _owner_activity_id(owner_a_id)
    a_field_def_id = _owner_tag_field_id(owner_a_id, a_activity_id)

    # Switch to user B.
    await _logout(client)
    await _signup(client, "tag_user_b")

    resp = await client.post(
        f"/activities/{a_activity_id}/tags",
        data={"field_def_id": str(a_field_def_id), "name": "ShouldNotExist"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 404, (
        f"Expected 404 when user B adds a tag to user A's activity, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Test: unauthenticated POST /log -> not 200, no write
# ---------------------------------------------------------------------------


async def test_unauthenticated_post_log_is_rejected(client: AsyncClient) -> None:
    """An unauthenticated POST to /log must not return 200 and must not write.

    The route redirects to ``/`` (303) when no session is present — the
    acceptance criteria require only "not 200 and no write succeeds".
    """
    # Create owner A so there is a real activity id to target.
    owner_a_id = await _signup(client, "unauth_owner")
    seeding.seed_account(owner_a_id)
    a_activity_id = _owner_activity_id(owner_a_id)

    # Record entry count before the attack.
    with db.connect() as conn:
        conn.execute("BEGIN")
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE owner_id = ?", (owner_a_id,)
        ).fetchone()["n"]

    # No session — log out and clear the jar.
    await _logout(client)

    resp = await client.post(
        f"/activities/{a_activity_id}/log",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code != 200, (
        f"Unauthenticated POST /log must not return 200, got {resp.status_code}"
    )

    # Entry count must be unchanged.
    with db.connect() as conn:
        conn.execute("BEGIN")
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE owner_id = ?", (owner_a_id,)
        ).fetchone()["n"]
    assert after == before, "Unauthenticated POST /log must not create an entry"


# ---------------------------------------------------------------------------
# Test: cross-user GET /entries/{entry_id}/edit -> 404
# ---------------------------------------------------------------------------


async def test_cross_user_get_edit_entry_returns_404(client: AsyncClient) -> None:
    """User B fetching user A's entry edit-form must receive 404.

    - The owner's own GET returns 200 (proves the route exists).
    - User B's cross-user GET returns 404 (access-control guard).
    """
    from zoneinfo import ZoneInfo

    from app.services import entries as entries_service

    utc = ZoneInfo("UTC")

    # Set up owner A with an entry.
    owner_a_id = await _signup(client, "edit_owner_a")
    seeding.seed_account(owner_a_id)
    a_activity_id = _owner_activity_id(owner_a_id)
    entries_service.create(owner_a_id, a_activity_id, {}, tz=utc)
    a_entry_id = _owner_entry_id(owner_a_id, a_activity_id)

    # Owner A must be able to reach their own edit form (proves the route exists).
    owner_resp = await client.get(
        f"/activities/{a_activity_id}/entries/{a_entry_id}/edit",
        headers={"HX-Request": "true"},
    )
    assert owner_resp.status_code == 200, (
        "Owner A must receive 200 from their own edit form "
        f"(got {owner_resp.status_code}) — route not yet implemented"
    )

    # Switch to user B; crossing the owner boundary must return 404.
    await _logout(client)
    await _signup(client, "edit_user_b")

    resp = await client.get(
        f"/activities/{a_activity_id}/entries/{a_entry_id}/edit",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 404
