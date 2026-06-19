"""Integration tests for the data-portability export route.

``GET /export`` is a thin wrapper around
``app/services/portability.export_data`` — it resolves the current session
(real account or guest, same signed-cookie mechanism) and streams the
snapshot back as a downloadable JSON file.

Setup mirrors ``tests/integration/test_web.py``: a fresh migrated temp SQLite
DB per test, ``SESSION_SECRET`` set, and an HTTPS base URL so the ``Secure``
session cookie round-trips through httpx's cookie jar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import connections, portability

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


async def _guest_login(client: AsyncClient) -> int:
    """Mint a guest session and return its owner_id (user id)."""
    resp = await client.post("/auth/guest")
    assert resp.status_code == 200
    return int(resp.json()["user_id"])


async def _signup_login(client: AsyncClient, email: str, password: str) -> int:
    """Sign up a real account and return its owner_id (user id).

    Derives a valid ``username`` (``[a-z0-9_]{3,20}``) from *email*'s local
    part, since ``/auth/signup`` now requires ``username`` as the identity key
    and ``email`` is optional recovery metadata.
    """
    username = re.sub(r"[^a-z0-9_]", "_", email.split("@")[0].lower())[:20]
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "email": email, "password": password, "consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["user_id"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_export_for_logged_in_user_returns_attachment_json(client: AsyncClient) -> None:
    uid = await _signup_login(client, "export-user@example.com", "hunter2pw")

    resp = await client.get("/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["content-disposition"] == 'attachment; filename="mushin-export.json"'

    payload = json.loads(resp.text)
    expected = portability.export_data(uid)
    # exported_at varies by a few ms between calls; compare shape + data.
    assert payload["schema_version"] == expected["schema_version"]
    assert payload["data"] == expected["data"]


async def test_export_includes_social_graph_section_over_http(client: AsyncClient) -> None:
    """The `/export` HTTP response — not just the underlying service — carries
    the `social_graph` section (fellows/pending/blocked), social-graph Task 8's
    acceptance criterion checked at the route boundary."""
    username = "sg_export_user"
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "hunter2pw", "consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    uid = int(resp.json()["user_id"])

    fellow_uid = await _signup_login(client, "sg-export-fellow@example.com", "hunter2pw")
    # _signup_login's signup call left the fellow's session active; switch
    # back to the original user via a fresh login (their password is known).
    resp = await client.post("/auth/login", data={"username": username, "password": "hunter2pw"})
    assert resp.status_code == 200, resp.text

    connections.send_request(uid, fellow_uid)
    connections.accept(fellow_uid, uid)

    resp = await client.get("/export")
    assert resp.status_code == 200
    payload = json.loads(resp.text)

    assert "social_graph" in payload
    sg = payload["social_graph"]
    assert {"fellows", "pending_requests", "blocked"} == set(sg.keys())
    assert len(sg["fellows"]) == 1
    assert sg["fellows"][0]["connected_at"] is not None
    assert sg["pending_requests"] == []
    assert sg["blocked"] == []


async def test_export_works_for_guest_account(client: AsyncClient) -> None:
    uid = await _guest_login(client)

    resp = await client.get("/export")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="mushin-export.json"'

    payload = json.loads(resp.text)
    expected = portability.export_data(uid)
    assert payload["data"] == expected["data"]


async def test_export_with_no_session_redirects_to_entry_screen(client: AsyncClient) -> None:
    resp = await client.get("/export", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_export_isolates_two_users_data(client: AsyncClient) -> None:
    uid_a = await _signup_login(client, "user-a@example.com", "passsword1")
    resp_a = await client.get("/export")
    assert resp_a.status_code == 200
    payload_a = json.loads(resp_a.text)

    # Log out by clearing the session cookie, then sign up a second user.
    client.cookies.clear()
    uid_b = await _signup_login(client, "user-b@example.com", "passsword2")
    resp_b = await client.get("/export")
    assert resp_b.status_code == 200
    payload_b = json.loads(resp_b.text)

    assert uid_a != uid_b
    # Each export reflects only its own owner's snapshot.
    assert payload_a["data"] == portability.export_data(uid_a)["data"]
    assert payload_b["data"] == portability.export_data(uid_b)["data"]


# ---------------------------------------------------------------------------
# POST /import
# ---------------------------------------------------------------------------


async def test_import_replaces_account_data(client: AsyncClient) -> None:
    uid = await _signup_login(client, "import-user@example.com", "hunter2pw")

    # Export the freshly-seeded account, then re-import it. The round trip
    # should succeed and leave the export shape unchanged.
    resp = await client.get("/export")
    assert resp.status_code == 200
    snapshot = json.loads(resp.text)

    import_resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", json.dumps(snapshot), "application/json")},
    )
    assert import_resp.status_code == 200
    # A signed-up (named) account's destination is its canonical profile, not
    # the bare /home shim.
    assert import_resp.headers["hx-redirect"] == "/@import_user"

    # Data round-tripped: counts (and full data shape) match the original.
    after = portability.export_data(uid)
    assert after["data"] == snapshot["data"]


async def test_import_oversized_file_rejected(client: AsyncClient) -> None:
    uid = await _signup_login(client, "oversize-user@example.com", "hunter2pw")
    before = portability.export_data(uid)

    huge_payload = json.dumps({"padding": "x" * (2 * 1024 * 1024 + 100)})
    resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", huge_payload, "application/json")},
    )
    assert resp.status_code == 400
    assert "hx-redirect" not in resp.headers
    assert portability.export_data(uid)["data"] == before["data"]


async def test_import_rejects_non_json_content_type(client: AsyncClient) -> None:
    uid = await _signup_login(client, "wrongtype-user@example.com", "hunter2pw")
    before = portability.export_data(uid)

    resp = await client.post(
        "/import",
        files={"file": ("mushin-export.txt", b"not json", "text/plain")},
    )
    assert resp.status_code == 400
    assert "hx-redirect" not in resp.headers
    assert portability.export_data(uid)["data"] == before["data"]


async def test_import_rejects_malformed_json(client: AsyncClient) -> None:
    uid = await _signup_login(client, "malformed-user@example.com", "hunter2pw")
    before = portability.export_data(uid)

    resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", b"{not valid json", "application/json")},
    )
    assert resp.status_code == 400
    assert "hx-redirect" not in resp.headers
    assert portability.export_data(uid)["data"] == before["data"]


async def test_import_rejects_invalid_schema_version(client: AsyncClient) -> None:
    uid = await _signup_login(client, "badschema-user@example.com", "hunter2pw")
    before = portability.export_data(uid)

    bad_payload = {"schema_version": 999, "exported_at": "2026-01-01T00:00:00Z", "data": {}}
    resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", json.dumps(bad_payload), "application/json")},
    )
    assert resp.status_code == 400
    assert "hx-redirect" not in resp.headers
    # The validation message (table/version info, no row content) is surfaced.
    assert "schema_version" in resp.text
    assert portability.export_data(uid)["data"] == before["data"]


async def test_import_owner_id_comes_from_session_not_payload(client: AsyncClient) -> None:
    """A route-level smoke test: import only ever targets the session's owner.

    The export payload shape has no owner_id field at all, so there is no
    field in the file that could target another account — this just confirms
    the imported data lands under the session's own account.
    """
    uid_a = await _signup_login(client, "owner-a@example.com", "passsword1")
    resp_a = await client.get("/export")
    snapshot_a = json.loads(resp_a.text)

    client.cookies.clear()
    uid_b = await _signup_login(client, "owner-b@example.com", "passsword2")
    assert uid_a != uid_b

    import_resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", json.dumps(snapshot_a), "application/json")},
    )
    assert import_resp.status_code == 200
    # uid_b is the named account that's logged in for this import — its own
    # canonical profile, not /home.
    assert import_resp.headers["hx-redirect"] == "/@owner_b"

    # uid_b now has uid_a's data shape, but still scoped to uid_b.
    assert portability.export_data(uid_b)["data"] == snapshot_a["data"]
    # uid_a's own data is untouched.
    assert portability.export_data(uid_a)["data"] == snapshot_a["data"]


async def test_import_works_for_guest_account(client: AsyncClient) -> None:
    uid = await _guest_login(client)

    resp = await client.get("/export")
    snapshot = json.loads(resp.text)

    import_resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", json.dumps(snapshot), "application/json")},
    )
    assert import_resp.status_code == 200
    assert import_resp.headers["hx-redirect"] == "/home"
    assert portability.export_data(uid)["data"] == snapshot["data"]


async def test_import_with_no_session_redirects_to_entry_screen(client: AsyncClient) -> None:
    resp = await client.post(
        "/import",
        files={"file": ("mushin-export.json", b'{"schema_version": 1}', "application/json")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
