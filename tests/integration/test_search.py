"""Integration tests for the people + tag search web routes (Tasks 9-10).

Covers:

1. ``GET /search`` requires a session (redirects when anonymous); ``GET
   /search/results`` requires a session (401 when anonymous).
2. People + tag results render as a grouped fragment, swapped via HTMX.
3. The people-result row's relationship control reflects the correct state
   (none/pending_outgoing/pending_incoming/fellow) and links to the
   profile — reusing ``components/relationship_affordance.html.jinja2``.
4. Both group empty states render with the exact centralized copy.
5. Privacy smoke test: a private account surfaces in people search (handle +
   display name only) but that account's tag does NOT surface in tag search
   (tag search is structurally public-only).

Fixture pattern mirrors ``tests/integration/test_fellows.py``: fresh migrated
temp SQLite DB per test, ``SESSION_SECRET`` set, HTTPS base URL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import ui_strings
from app.auth import users
from app.main import app
from app.models import db
from app.models.migrate import run_migrations

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def search_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client_a(search_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client_b(search_db: Path) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def anon_client(search_db: Path) -> AsyncClient:
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


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_tagged_activity(
    db_path: Path, owner_id: int, name: str, slug: str, tag_name: str
) -> None:
    """Create a category + activity + tag-group field_def + tag for *owner_id*."""
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO category (owner_id, name) VALUES (?, ?)", (owner_id, name + " cat")
    )
    category_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO activity (owner_id, category_id, name, count_mode, slug)"
        " VALUES (?, ?, ?, 'running', ?)",
        (owner_id, category_id, name, slug),
    )
    activity_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO field_def (activity_id, kind, label) VALUES (?, 'tag_group', 'Tags')",
        (activity_id,),
    )
    field_def_id = cur.lastrowid
    conn.execute(
        "INSERT INTO tag (owner_id, field_def_id, name) VALUES (?, ?, ?)",
        (owner_id, field_def_id, tag_name),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


async def test_search_page_requires_session(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/search", follow_redirects=False)
    assert resp.status_code == 303


async def test_search_results_requires_session(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/search/results", params={"q": "ali"})
    assert resp.status_code == 401


async def test_search_page_renders_for_logged_in_user(client_a: AsyncClient) -> None:
    await _signup(client_a, "alice")
    resp = await client_a.get("/search")
    assert resp.status_code == 200
    assert "<html" in resp.text
    assert ui_strings.SEARCH_TITLE in resp.text
    assert ui_strings.SEARCH_INPUT_LABEL in resp.text


# ---------------------------------------------------------------------------
# Results fragment: people + tags, empty states
# ---------------------------------------------------------------------------


async def test_blank_query_renders_calm_prompt_not_results(client_a: AsyncClient) -> None:
    await _signup(client_a, "alice")
    resp = await client_a.get("/search/results", params={"q": ""})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert ui_strings.SEARCH_PROMPT in resp.text
    assert ui_strings.SEARCH_PEOPLE_HEADING not in resp.text


async def test_people_empty_state_renders_calm_copy(client_a: AsyncClient) -> None:
    await _signup(client_a, "alice")
    resp = await client_a.get("/search/results", params={"q": "nobody-by-this-name"})
    assert resp.status_code == 200
    assert ui_strings.SEARCH_PEOPLE_EMPTY in resp.text
    assert ui_strings.SEARCH_TAGS_EMPTY in resp.text


async def test_people_result_renders_with_connect_control_and_profile_link(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice")
    await _signup(client_b, "bobalicious")

    resp = await client_a.get("/search/results", params={"q": "bob"})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert ui_strings.SEARCH_PEOPLE_HEADING in resp.text
    assert '/@bobalicious"' in resp.text
    assert "bobalicious" in resp.text
    # "none" state -> Connect control, scoped to this row's dom id.
    assert ui_strings.CONNECT_ACTION in resp.text
    assert 'id="relationship-affordance-bobalicious"' in resp.text
    assert "/fellows/bobalicious/connect-confirm?source=search" in resp.text


async def test_people_result_reflects_pending_outgoing_state(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice")
    await _signup(client_b, "bob")

    confirm = await client_a.get("/fellows/bob/connect-confirm", params={"source": "search"})
    assert confirm.status_code == 200
    sent = await client_a.post("/fellows/bob/connect", params={"source": "search"})
    assert sent.status_code == 200
    assert ui_strings.CONNECT_REQUESTED in sent.text

    resp = await client_a.get("/search/results", params={"q": "bob"})
    assert resp.status_code == 200
    assert ui_strings.CONNECT_REQUESTED in resp.text
    assert ui_strings.CONNECT_ACTION not in resp.text


async def test_people_result_reflects_pending_incoming_state_with_accept_decline(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice")
    await _signup(client_b, "bob")

    await client_a.get("/fellows/bob/connect-confirm")
    await client_a.post("/fellows/bob/connect")

    resp = await client_b.get("/search/results", params={"q": "alice"})
    assert resp.status_code == 200
    assert ui_strings.REQUESTS_ACCEPT in resp.text
    assert ui_strings.REQUESTS_DECLINE in resp.text
    assert "/fellows/requests/alice/accept-confirm?source=search" in resp.text


async def test_people_result_reflects_fellow_state(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    await _signup(client_a, "alice")
    await _signup(client_b, "bob")

    await client_a.get("/fellows/bob/connect-confirm")
    await client_a.post("/fellows/bob/connect")
    await client_b.get("/fellows/requests/alice/accept-confirm")
    await client_b.post("/fellows/requests/alice/accept")

    resp = await client_a.get("/search/results", params={"q": "bob"})
    assert resp.status_code == 200
    assert ui_strings.CONNECT_FELLOWS_LABEL in resp.text
    assert ui_strings.CONNECT_REMOVE in resp.text


async def test_accept_from_search_updates_only_that_row(
    client_a: AsyncClient, client_b: AsyncClient
) -> None:
    """Accepting a request from the search page swaps just that row, not a
    page-singleton #fellows-section (which doesn't exist on /search)."""
    await _signup(client_a, "alice")
    await _signup(client_b, "bob")

    await client_a.get("/fellows/bob/connect-confirm")
    await client_a.post("/fellows/bob/connect")

    resp = await client_b.post("/fellows/requests/alice/accept", params={"source": "search"})
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert 'id="relationship-affordance-alice"' in resp.text
    assert ui_strings.CONNECT_FELLOWS_LABEL in resp.text
    assert "fellows-section" not in resp.text


# ---------------------------------------------------------------------------
# Tag search results
# ---------------------------------------------------------------------------


async def test_tag_result_renders_and_links_to_public_activity(
    client_a: AsyncClient, search_db: Path
) -> None:
    owner_id = await _signup(client_a, "alice", visibility="public")
    _make_tagged_activity(search_db, owner_id, "Running", "running", "5k")

    resp = await client_a.get("/search/results", params={"q": "5k"})
    assert resp.status_code == 200
    assert ui_strings.SEARCH_TAGS_HEADING in resp.text
    assert "#5k" in resp.text
    assert '/@alice/running"' in resp.text


# ---------------------------------------------------------------------------
# Privacy smoke test (the core guarantee from app.services.search)
# ---------------------------------------------------------------------------


async def test_private_account_findable_by_name_but_not_by_tag(
    client_a: AsyncClient, client_b: AsyncClient, search_db: Path
) -> None:
    """A private account surfaces in people search (handle + display name
    only) but its tags never surface in tag search — tag search is
    structurally public-only."""
    owner_id = await _signup(client_b, "privatebob", visibility="private")
    _make_tagged_activity(search_db, owner_id, "Knitting", "knitting", "scarves")
    await _signup(client_a, "alice")

    people_resp = await client_a.get("/search/results", params={"q": "privatebob"})
    assert people_resp.status_code == 200
    assert "privatebob" in people_resp.text
    # No activity/tag data ever appears in the people group.
    assert "Knitting" not in people_resp.text
    assert "scarves" not in people_resp.text

    tag_resp = await client_a.get("/search/results", params={"q": "scarves"})
    assert tag_resp.status_code == 200
    assert ui_strings.SEARCH_TAGS_EMPTY in tag_resp.text
    assert "scarves" not in tag_resp.text
    assert "privatebob" not in tag_resp.text
