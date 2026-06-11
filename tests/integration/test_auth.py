"""Integration tests for the auth layer (Task 4).

Covers every acceptance criterion:

1. Email signup/login end-to-end; password stored as an Argon2id encoded hash;
   wrong password rejected; plaintext never logged.
2. Kakao + Google callbacks with userinfo **mocked** create/find a user by
   ``(auth_provider, provider_id)`` and set a session.
3. Signup AND guest upgrade require explicit unbundled consent.
4. Guest-create-on-interaction: the POST endpoint creates a guest + session and
   the user can act immediately; a bare page GET creates no guest row.
5. Upgrade preserves data: a guest with entries who signs in keeps every owned
   row under the same ``owner_id`` (counts identical before/after).
6. Full-cascade deletion (account + guest) leaves no orphaned data.
7. Session cookie carries ``HttpOnly; Secure; SameSite=Lax``.

Setup: each test gets its own freshly-migrated temp SQLite file (never the dev
DB), ``db.DATABASE_PATH`` is pointed at it, and ``SESSION_SECRET`` is set. The
client uses an ``https://`` base URL so httpx's cookie jar round-trips the
``Secure`` session cookie. OAuth userinfo is monkeypatched on
``app.auth.oauth.fetch_userinfo`` so no live credentials or network are used.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import oauth
from app.main import app
from app.models import db
from app.models.migrate import run_migrations

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(auth_db: Path) -> AsyncClient:
    """Async client with an HTTPS base URL so the Secure session cookie persists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _count(db_path: Path, table: str, where: str = "", params: tuple = ()) -> int:
    conn = _raw(db_path)
    try:
        sql = f"SELECT COUNT(*) AS n FROM {table}"  # noqa: S608 - test-only, fixed names
        if where:
            sql += f" WHERE {where}"
        return conn.execute(sql, params).fetchone()["n"]
    finally:
        conn.close()


def _seed_entries_for(db_path: Path, owner_id: int, n_entries: int = 3) -> dict[str, int]:
    """Seed a category/sub_tally/entries/match for an existing *owner_id* in raw SQL.

    Returns ids so a test can assert they survive an upgrade or vanish on delete.
    """
    conn = _raw(db_path)
    try:
        cat_id = conn.execute(
            "INSERT INTO category (owner_id, name) VALUES (?, 'Kendo')", (owner_id,)
        ).lastrowid
        st_id = conn.execute(
            "INSERT INTO sub_tally (owner_id, category_id, name, count_mode)"
            " VALUES (?, ?, 'Practice', 'running')",
            (owner_id, cat_id),
        ).lastrowid
        entry_ids = []
        for i in range(n_entries):
            eid = conn.execute(
                "INSERT INTO entry (owner_id, sub_tally_id, occurred_at, memo) VALUES (?, ?, ?, ?)",
                (owner_id, st_id, f"2026-01-0{i + 1}T09:00:00+09:00", f"memo {i}"),
            ).lastrowid
            entry_ids.append(eid)
        # one match hanging off the first entry
        conn.execute(
            "INSERT INTO match (entry_id, owner_id, opponent, score, result)"
            " VALUES (?, ?, 'Rival', '2-1', 'win')",
            (entry_ids[0], owner_id),
        )
        return {"owner_id": owner_id, "sub_tally_id": st_id, "n_entries": n_entries}
    finally:
        conn.close()


def _session_cookie_from(response) -> str | None:
    for cookie in response.headers.get_list("set-cookie"):
        if cookie.startswith("mushin_session="):
            return cookie
    return None


# ---------------------------------------------------------------------------
# 1. Email auth
# ---------------------------------------------------------------------------


async def test_email_signup_then_login_succeeds(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"email": "a@example.com", "password": "hunter2pw", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]

    # Password is stored as an Argon2id encoded hash — never plaintext.
    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT password_hash FROM user WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()
    assert row["password_hash"].startswith("$argon2id$")
    assert "hunter2pw" not in row["password_hash"]

    # Login with the right password.
    r2 = await client.post("/auth/login", data={"email": "a@example.com", "password": "hunter2pw"})
    assert r2.status_code == 200
    assert r2.json()["user_id"] == uid


async def test_email_login_rejects_wrong_password(client: AsyncClient):
    await client.post(
        "/auth/signup",
        data={"email": "b@example.com", "password": "correct-horse", "consent": "true"},
    )
    r = await client.post(
        "/auth/login", data={"email": "b@example.com", "password": "wrong-password"}
    )
    assert r.status_code == 401


async def test_email_login_unknown_user_rejected(client: AsyncClient):
    r = await client.post(
        "/auth/login", data={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 2. Mocked OAuth callbacks
# ---------------------------------------------------------------------------


async def test_kakao_callback_creates_user_by_identity(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="kakao", provider_id="kakao-9001", display_name="철수"
        ),
    )
    r = await client.get("/auth/kakao/callback", params={"code": "fake-code"})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]

    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "kakao"
    assert row["provider_id"] == "kakao-9001"
    assert _session_cookie_from(r) is not None

    # Second callback with the same identity finds (not duplicates) the user.
    r2 = await client.get("/auth/kakao/callback", params={"code": "fake-code-2"})
    assert r2.json()["user_id"] == uid
    assert _count(auth_db, "user", "auth_provider = 'kakao'") == 1


async def test_google_callback_creates_user_by_sub(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google",
            provider_id="google-sub-123",
            display_name="Soomin",
            email="soomin@example.com",
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "g-code"})
    assert r.status_code == 200, r.text
    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (r.json()["user_id"],)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "google"
    assert row["provider_id"] == "google-sub-123"


def test_normalize_kakao_and_google_payloads():
    k = oauth.normalize(
        "kakao",
        {"id": 555, "kakao_account": {"profile": {"nickname": "민수"}}},
    )
    assert k.auth_provider == "kakao"
    assert k.provider_id == "555"
    assert k.display_name == "민수"
    assert k.email is None  # Kakao gives no email by design

    g = oauth.normalize("google", {"sub": "abc", "name": "Jane", "email": "jane@example.com"})
    assert g.provider_id == "abc"
    assert g.email == "jane@example.com"


# ---------------------------------------------------------------------------
# 3. Consent gate (signup + upgrade)
# ---------------------------------------------------------------------------


async def test_signup_requires_consent(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"email": "c@example.com", "password": "passsword1", "consent": "false"},
    )
    assert r.status_code == 400
    assert _count(auth_db, "user") == 0  # nothing created


async def test_guest_upgrade_requires_consent(client: AsyncClient, auth_db: Path):
    # Start as a guest.
    g = await client.post("/auth/guest")
    assert g.status_code == 200
    guest_uid = g.json()["user_id"]

    # Attempt upgrade without consent -> rejected, still a guest, no new row.
    r = await client.post(
        "/auth/signup",
        data={"email": "up@example.com", "password": "passsword1", "consent": "false"},
    )
    assert r.status_code == 400
    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT auth_provider FROM user WHERE id = ?", (guest_uid,)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "guest"
    assert _count(auth_db, "user") == 1


# ---------------------------------------------------------------------------
# 4. Guest create on interaction, not on bare GET
# ---------------------------------------------------------------------------


async def test_guest_created_on_interaction(client: AsyncClient, auth_db: Path):
    r = await client.post("/auth/guest")
    assert r.status_code == 200
    assert r.json()["created"] is True
    assert _count(auth_db, "user", "auth_provider = 'guest'") == 1
    assert _session_cookie_from(r) is not None

    # The guest can act immediately: /auth/me resolves the session.
    me = await client.get("/auth/me")
    assert me.json()["auth_provider"] == "guest"


async def test_bare_page_get_creates_no_guest(client: AsyncClient, auth_db: Path):
    # A plain GET of the index (and /health) must NOT mint a guest row.
    await client.get("/")
    await client.get("/health")
    await client.get("/auth/me")
    assert _count(auth_db, "user") == 0


async def test_guest_start_is_idempotent(client: AsyncClient, auth_db: Path):
    first = await client.post("/auth/guest")
    uid = first.json()["user_id"]
    second = await client.post("/auth/guest")
    assert second.json()["created"] is False
    assert second.json()["user_id"] == uid
    assert _count(auth_db, "user") == 1


# ---------------------------------------------------------------------------
# 5. Upgrade preserves ALL data (same owner_id)
# ---------------------------------------------------------------------------


async def test_guest_upgrade_preserves_all_data_email(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    # Become a guest through the real endpoint so httpx holds the session cookie.
    g = await client.post("/auth/guest")
    owner_id = g.json()["user_id"]
    _seed_entries_for(auth_db, owner_id, n_entries=3)

    entries_before = _count(auth_db, "entry", "owner_id = ?", (owner_id,))
    matches_before = _count(auth_db, "match", "owner_id = ?", (owner_id,))

    r = await client.post(
        "/auth/signup",
        data={"email": "grew@example.com", "password": "newpass123", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is True
    assert r.json()["user_id"] == owner_id  # same row, no new id

    # No new user row; the guest row is now an email account.
    assert _count(auth_db, "user") == 1
    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (owner_id,)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "email"
    assert row["display_name"] == "grew@example.com"

    # Every owned row preserved under the same owner_id.
    assert _count(auth_db, "entry", "owner_id = ?", (owner_id,)) == entries_before == 3
    assert _count(auth_db, "match", "owner_id = ?", (owner_id,)) == matches_before == 1


async def test_guest_upgrade_preserves_all_data_oauth(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    g = await client.post("/auth/guest")
    owner_id = g.json()["user_id"]
    _seed_entries_for(auth_db, owner_id, n_entries=4)

    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google", provider_id="g-upgrade", display_name="Up"
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "c"})
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is True
    assert r.json()["user_id"] == owner_id

    assert _count(auth_db, "user") == 1
    assert _count(auth_db, "entry", "owner_id = ?", (owner_id,)) == 4
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT auth_provider, provider_id FROM user WHERE id = ?", (owner_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "google"
    assert row["provider_id"] == "g-upgrade"


async def test_upgrade_to_existing_identity_does_not_merge(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    # A real Google account already exists (created directly so no session is set).
    conn = _raw(auth_db)
    try:
        real_uid = conn.execute(
            "INSERT INTO user (auth_provider, provider_id, display_name)"
            " VALUES ('google', 'dup-sub', 'Real')"
        ).lastrowid
    finally:
        conn.close()

    # Now a guest (via the real endpoint, so httpx holds its cookie) tries to
    # upgrade into that same identity.
    g = await client.post("/auth/guest")
    guest_uid = g.json()["user_id"]
    _seed_entries_for(auth_db, guest_uid, n_entries=2)

    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google", provider_id="dup-sub", display_name="Real"
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "c2"})
    assert r.status_code == 409  # replace-or-discard decision surfaced, no merge
    body = r.json()["detail"]
    assert body["existing_user_id"] == real_uid
    assert body["guest_user_id"] == guest_uid
    # Both rows still exist independently; no merge happened.
    assert _count(auth_db, "user") == 2


# ---------------------------------------------------------------------------
# 6. Full-cascade deletion (account + guest)
# ---------------------------------------------------------------------------


async def test_delete_guest_cascades_all_data(client: AsyncClient, auth_db: Path):
    g = await client.post("/auth/guest")
    owner_id = g.json()["user_id"]
    _seed_entries_for(auth_db, owner_id, n_entries=3)

    r = await client.post("/auth/delete")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # No orphaned data anywhere.
    assert _count(auth_db, "user") == 0
    assert _count(auth_db, "category") == 0
    assert _count(auth_db, "sub_tally") == 0
    assert _count(auth_db, "entry") == 0
    assert _count(auth_db, "match") == 0
    # session cookie cleared
    cleared = _session_cookie_from(r)
    assert cleared is not None and ("Max-Age=0" in cleared or "01 Jan 1970" in cleared)


async def test_delete_email_account_cascades(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"email": "del@example.com", "password": "passsword1", "consent": "true"},
    )
    uid = r.json()["user_id"]
    # add a category directly so there's owned data to cascade
    conn = _raw(auth_db)
    try:
        conn.execute("INSERT INTO category (owner_id, name) VALUES (?, 'X')", (uid,))
    finally:
        conn.close()

    d = await client.post("/auth/delete")
    assert d.status_code == 200
    assert _count(auth_db, "user") == 0
    assert _count(auth_db, "category") == 0


async def test_delete_without_session_rejected(client: AsyncClient):
    r = await client.post("/auth/delete")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 7. Session cookie security flags
# ---------------------------------------------------------------------------


async def test_session_cookie_has_security_flags(client: AsyncClient):
    r = await client.post(
        "/auth/signup",
        data={"email": "sec@example.com", "password": "passsword1", "consent": "true"},
    )
    cookie = _session_cookie_from(r)
    assert cookie is not None
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered


async def test_guest_cookie_has_security_flags(client: AsyncClient):
    r = await client.post("/auth/guest")
    cookie = _session_cookie_from(r)
    assert cookie is not None
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
