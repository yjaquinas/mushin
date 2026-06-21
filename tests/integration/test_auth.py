"""Integration tests for the auth layer (Task 4).

Covers every acceptance criterion:

1. Email signup/login end-to-end; password stored as an Argon2id encoded hash;
   wrong password rejected; plaintext never logged.
2. Google callbacks with userinfo **mocked** create/find a user by
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
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET.

    Sets ``OAUTH_ENABLED=true`` so the OAuth route tests exercise the (now
    flag-gated) provider handlers. The product default is ``false`` — that
    guest-only behavior is asserted separately by the OAuth-gate tests below,
    which clear the var explicitly.
    """
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    monkeypatch.setenv("OAUTH_ENABLED", "true")
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
    """Seed a category/activity/entries/match for an existing *owner_id* in raw SQL.

    Returns ids so a test can assert they survive an upgrade or vanish on delete.
    """
    conn = _raw(db_path)
    try:
        cat_id = conn.execute(
            "INSERT INTO category (owner_id, name) VALUES (?, 'Kendo')", (owner_id,)
        ).lastrowid
        st_id = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode)"
            " VALUES (?, ?, 'Practice', 'running')",
            (owner_id, cat_id),
        ).lastrowid
        entry_ids = []
        for i in range(n_entries):
            eid = conn.execute(
                "INSERT INTO entry (owner_id, activity_id, occurred_at, memo) VALUES (?, ?, ?, ?)",
                (owner_id, st_id, f"2026-01-0{i + 1}T09:00:00+09:00", f"memo {i}"),
            ).lastrowid
            entry_ids.append(eid)
        # one match hanging off the first entry
        conn.execute(
            "INSERT INTO match (entry_id, owner_id, opponent, score, result)"
            " VALUES (?, ?, 'Rival', '2-1', 'win')",
            (entry_ids[0], owner_id),
        )
        return {"owner_id": owner_id, "activity_id": st_id, "n_entries": n_entries}
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
        data={
            "username": "alice",
            "password": "hunter2pw",
            "email": "a@example.com",
            "consent": "true",
        },
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
    r2 = await client.post(
        "/auth/login", data={"username": "alice", "password": "hunter2pw"}
    )
    assert r2.status_code == 200
    assert r2.json()["user_id"] == uid


async def test_fresh_email_signup_seeds_starter_templates(client: AsyncClient, auth_db: Path):
    # A genuinely new (non-guest) username/password signup is seeded with the v1
    # starter templates — the regression guard for _lazy_seed being wired into
    # the fresh-signup path.
    r = await client.post(
        "/auth/signup",
        data={"username": "freshie", "password": "hunter2pw", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is False
    owner_id = r.json()["user_id"]

    assert _count(auth_db, "category", "owner_id = ?", (owner_id,)) > 0
    assert _count(auth_db, "activity", "owner_id = ?", (owner_id,)) > 0


async def test_email_login_rejects_wrong_password(client: AsyncClient):
    await client.post(
        "/auth/signup",
        data={"username": "bob", "password": "correct-horse", "consent": "true"},
    )
    r = await client.post(
        "/auth/login", data={"username": "bob", "password": "wrong-password"}
    )
    assert r.status_code == 401


async def test_email_login_unknown_user_rejected(client: AsyncClient):
    r = await client.post(
        "/auth/login", data={"username": "nobody", "password": "whatever123"}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 2. Mocked OAuth callbacks
# ---------------------------------------------------------------------------


async def test_google_callback_finds_existing_by_identity(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google", provider_id="google-9001", display_name="Casey"
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "fake-code"})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]

    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "google"
    assert row["provider_id"] == "google-9001"
    assert _session_cookie_from(r) is not None

    # Second callback with the same identity finds (not duplicates) the user.
    r2 = await client.get("/auth/google/callback", params={"code": "fake-code-2"})
    assert r2.json()["user_id"] == uid
    assert _count(auth_db, "user", "auth_provider = 'google'") == 1


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


def test_normalize_google_payload():
    g = oauth.normalize("google", {"sub": "abc", "name": "Jane", "email": "jane@example.com"})
    assert g.auth_provider == "google"
    assert g.provider_id == "abc"
    assert g.display_name == "Jane"
    assert g.email == "jane@example.com"


# ---------------------------------------------------------------------------
# 2b. OAUTH_ENABLED flag gates the OAuth routes (guest-only by default)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["google"])
async def test_oauth_authorize_404_when_disabled_by_default(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, provider: str
):
    # The product default is guest-only: with OAUTH_ENABLED unset, the authorize
    # route is indistinguishable from an unknown provider (404).
    monkeypatch.delenv("OAUTH_ENABLED", raising=False)
    r = await client.get(f"/auth/{provider}/authorize")
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown provider"


@pytest.mark.parametrize("provider", ["google"])
async def test_oauth_callback_404_when_disabled_by_default(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, provider: str
):
    monkeypatch.delenv("OAUTH_ENABLED", raising=False)
    r = await client.get(f"/auth/{provider}/callback", params={"code": "x"})
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown provider"


@pytest.mark.parametrize("flag", ["false", "False", "0", "no", ""])
async def test_oauth_authorize_404_for_non_true_flag_values(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, flag: str
):
    # Only an explicit "true" (case-insensitive) opens the routes.
    monkeypatch.setenv("OAUTH_ENABLED", flag)
    r = await client.get("/auth/google/authorize")
    assert r.status_code == 404


async def test_oauth_authorize_redirects_when_enabled(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    # auth_db sets OAUTH_ENABLED=true; the authorize route then redirects to the
    # provider with a CSRF state cookie set.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id")
    r = await client.get("/auth/google/authorize", follow_redirects=False)
    assert r.status_code == 302
    assert any(c.startswith("oauth_state=") for c in r.headers.get_list("set-cookie"))


# ---------------------------------------------------------------------------
# 3. Consent gate (signup + upgrade)
# ---------------------------------------------------------------------------


async def test_signup_requires_consent(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"username": "charlie", "password": "passsword1", "consent": "false"},
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
        data={"username": "upgrader", "password": "passsword1", "consent": "false"},
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


async def test_guest_start_seeds_starter_templates(client: AsyncClient, auth_db: Path):
    # A genuinely new account is seeded with the v1 starter templates on
    # creation (onboarding promise). A brand-new guest lands with the seeded
    # categories + activities, not an empty account.
    g = await client.post("/auth/guest")
    assert g.json()["created"] is True
    owner_id = g.json()["user_id"]

    assert _count(auth_db, "category", "owner_id = ?", (owner_id,)) > 0
    assert _count(auth_db, "activity", "owner_id = ?", (owner_id,)) > 0

    # Idempotent: hitting /auth/guest again for the same session returns the same
    # row without minting a duplicate, and seeding does NOT run again (the count
    # stays exactly what the first seed produced).
    seeded_categories = _count(auth_db, "category", "owner_id = ?", (owner_id,))
    again = await client.post("/auth/guest")
    assert again.json()["created"] is False
    assert _count(auth_db, "category", "owner_id = ?", (owner_id,)) == seeded_categories


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
        data={
            "username": "grew",
            "password": "newpass123",
            "email": "grew@example.com",
            "consent": "true",
        },
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
    assert row["display_name"] == "grew"

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
    assert _count(auth_db, "activity") == 0
    assert _count(auth_db, "entry") == 0
    assert _count(auth_db, "match") == 0
    # session cookie cleared
    cleared = _session_cookie_from(r)
    assert cleared is not None and ("Max-Age=0" in cleared or "01 Jan 1970" in cleared)


async def test_delete_email_account_cascades(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"username": "deleteme", "password": "passsword1", "consent": "true"},
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
        data={"username": "secuser", "password": "passsword1", "consent": "true"},
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


# ---------------------------------------------------------------------------
# 8. "Switch account" flow — guest logs out/deletes, then logs into an
#    existing real account (web-renderer's switch-confirmation dialog on
#    /account: "그대로 두기" -> /auth/logout, "삭제하기" -> /auth/delete, both
#    followed by an OAuth login that should take the plain-login branch, not
#    the guest-upgrade-collision branch).
# ---------------------------------------------------------------------------


async def test_guest_logout_then_login_to_existing_account_uses_plain_login(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    # An existing real Google account, created directly (no session held for it).
    conn = _raw(auth_db)
    try:
        real_uid = conn.execute(
            "INSERT INTO user (auth_provider, provider_id, display_name)"
            " VALUES ('google', 'switch-sub', 'Real')"
        ).lastrowid
    finally:
        conn.close()

    # Become a guest with data.
    g = await client.post("/auth/guest")
    guest_uid = g.json()["user_id"]
    _seed_entries_for(auth_db, guest_uid, n_entries=3)
    guest_entries_before = _count(auth_db, "entry", "owner_id = ?", (guest_uid,))
    assert guest_entries_before == 3

    # "그대로 두기" -> logout only, guest data left for the reaper.
    out = await client.post("/auth/logout")
    assert out.status_code == 200, out.text
    cleared = _session_cookie_from(out)
    assert cleared is not None and ("Max-Age=0" in cleared or "01 Jan 1970" in cleared)

    # No active session now.
    me = await client.get("/auth/me")
    assert me.json()["user_id"] is None

    # Log into the existing real account via Google OAuth.
    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google", provider_id="switch-sub", display_name="Real"
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "switch-code"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upgraded"] is False
    assert body["user_id"] == real_uid

    # The guest row and its data still exist, untouched, left for the reaper.
    assert _count(auth_db, "user", "id = ?", (guest_uid,)) == 1
    assert _count(auth_db, "entry", "owner_id = ?", (guest_uid,)) == guest_entries_before
    # Both accounts exist independently; no merge happened.
    assert _count(auth_db, "user") == 2


async def test_guest_delete_then_login_to_existing_account_removes_guest_data(
    client: AsyncClient, auth_db: Path, monkeypatch: pytest.MonkeyPatch
):
    # An existing real Google account, created directly (no session held for it).
    conn = _raw(auth_db)
    try:
        real_uid = conn.execute(
            "INSERT INTO user (auth_provider, provider_id, display_name)"
            " VALUES ('google', 'switch-sub-2', 'Real2')"
        ).lastrowid
    finally:
        conn.close()

    # Become a guest with data.
    g = await client.post("/auth/guest")
    guest_uid = g.json()["user_id"]
    _seed_entries_for(auth_db, guest_uid, n_entries=2)

    # "삭제하기" -> full cascade delete of the guest.
    d = await client.post("/auth/delete")
    assert d.status_code == 200, d.text
    assert d.json()["deleted"] is True
    assert _count(auth_db, "user", "id = ?", (guest_uid,)) == 0
    assert _count(auth_db, "entry", "owner_id = ?", (guest_uid,)) == 0

    # Log into the existing real account via Google OAuth.
    monkeypatch.setattr(
        oauth,
        "fetch_userinfo",
        lambda provider, code, redirect_uri: oauth.OAuthIdentity(
            auth_provider="google", provider_id="switch-sub-2", display_name="Real2"
        ),
    )
    r = await client.get("/auth/google/callback", params={"code": "switch-code-2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upgraded"] is False
    assert body["user_id"] == real_uid

    # Only the real account remains; no leftover guest data.
    assert _count(auth_db, "user") == 1


async def test_old_guest_session_cookie_does_not_resolve_after_logout(
    client: AsyncClient, auth_db: Path
):
    """Document the actual guarantee of /auth/logout for a replayed cookie.

    ``/auth/logout`` calls ``delete_cookie``, which is an instruction to the
    *browser* to stop sending the cookie (Set-Cookie with Max-Age=0). It does
    not invalidate the signed cookie value server-side — ``itsdangerous``
    signatures aren't revocable without a server-side blacklist or rotating
    ``SESSION_SECRET``. So if the old signed value is replayed *explicitly*
    (bypassing the browser's cookie jar), it still verifies and resolves to
    the guest's uid.

    The real guarantee is browser-side: a normal browser honors the
    Set-Cookie/Max-Age=0 instruction and will not resend the old cookie, so
    the guest has no recoverable handle once it's gone from the browser. This
    test documents that guarantee rather than asserting a server-side
    revocation that doesn't exist.
    """
    g = await client.post("/auth/guest")
    guest_uid = g.json()["user_id"]
    old_cookie_value = client.cookies.get("mushin_session")
    assert old_cookie_value is not None

    out = await client.post("/auth/logout")
    assert out.status_code == 200

    # A normal browser no longer sends the cookie -> no active session.
    me = await client.get("/auth/me")
    assert me.json()["user_id"] is None

    # Replaying the old signed cookie value explicitly still verifies the
    # signature and resolves to the guest's uid -- this is expected given a
    # stateless signed-cookie scheme, not a server-side bug. `delete_cookie`
    # only stops the browser from resending it.
    client.cookies.set("mushin_session", old_cookie_value)
    replayed = await client.get("/auth/me")
    assert replayed.json()["user_id"] == guest_uid


# ---------------------------------------------------------------------------
# 8. Username/password signup + login gap-fill (Task 6)
# ---------------------------------------------------------------------------


async def test_signup_username_password_only_succeeds(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/signup",
        data={"username": "noemail", "password": "passsword1", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is False
    # Real-user-only route: the JSON success body always carries the
    # canonical-profile redirect destination.
    assert r.json()["redirect_url"] == "/@noemail"
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT email, username FROM user WHERE id = ?", (r.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["username"] == "noemail"
    assert row["email"] is None


async def test_signup_username_password_email_succeeds_and_stores_email(
    client: AsyncClient, auth_db: Path
):
    r = await client.post(
        "/auth/signup",
        data={
            "username": "withemail",
            "password": "passsword1",
            "email": "withemail@example.com",
            "consent": "true",
        },
    )
    assert r.status_code == 200, r.text
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT email FROM user WHERE id = ?", (r.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["email"] == "withemail@example.com"


async def test_signup_duplicate_username_returns_409_generic_message(
    client: AsyncClient, auth_db: Path
):
    first = await client.post(
        "/auth/signup",
        data={"username": "dupuser", "password": "passsword1", "consent": "true"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/signup",
        data={"username": "dupuser", "password": "differentpw", "consent": "true"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "That username is already taken."
    # No field-leak: message doesn't reveal whether it was username or email.
    assert "email" not in second.json()["detail"].lower()
    assert _count(auth_db, "user") == 1


async def test_signup_duplicate_email_different_username_returns_409(
    client: AsyncClient, auth_db: Path
):
    first = await client.post(
        "/auth/signup",
        data={
            "username": "firstuser",
            "password": "passsword1",
            "email": "shared@example.com",
            "consent": "true",
        },
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/signup",
        data={
            "username": "seconduser",
            "password": "passsword2",
            "email": "shared@example.com",
            "consent": "true",
        },
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "That username is already taken."
    assert _count(auth_db, "user") == 1


@pytest.mark.parametrize(
    "bad_username",
    ["ab", "foo-bar", "foo bar", "foo@bar", "x" * 21],
)
async def test_signup_invalid_username_shape_returns_400(
    client: AsyncClient, auth_db: Path, bad_username: str
):
    r = await client.post(
        "/auth/signup",
        data={"username": bad_username, "password": "passsword1", "consent": "true"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == (
        "Username must be 3-20 characters: lowercase letters, numbers, "
        "and underscores only."
    )
    assert _count(auth_db, "user") == 0


async def test_login_with_correct_username_password_sets_session(
    client: AsyncClient, auth_db: Path
):
    signup = await client.post(
        "/auth/signup",
        data={"username": "loginok", "password": "passsword1", "consent": "true"},
    )
    assert signup.status_code == 200
    uid = signup.json()["user_id"]
    await client.post("/auth/logout")
    client.cookies.clear()

    r = await client.post(
        "/auth/login", data={"username": "loginok", "password": "passsword1"}
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == uid
    assert r.json()["redirect_url"] == "/@loginok"
    assert _session_cookie_from(r) is not None


async def test_login_wrong_password_generic_401(client: AsyncClient, auth_db: Path):
    await client.post(
        "/auth/signup",
        data={"username": "wrongpw", "password": "passsword1", "consent": "true"},
    )
    r = await client.post(
        "/auth/login", data={"username": "wrongpw", "password": "totallywrong"}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "That username or password isn't right."


async def test_login_unknown_username_same_generic_401(client: AsyncClient, auth_db: Path):
    r = await client.post(
        "/auth/login", data={"username": "ghostuser", "password": "whatever1"}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "That username or password isn't right."


# ---------------------------------------------------------------------------
# 9. Timezone capture on signup / guest creation (hidden form field)
# ---------------------------------------------------------------------------


async def test_signup_captures_timezone_from_form_field(
    client: AsyncClient, auth_db: Path
):
    # The JS stamps a hidden `timezone` field; simulate it on the signup POST.
    r = await client.post(
        "/auth/signup",
        data={
            "username": "tzsignup",
            "password": "passsword1",
            "consent": "true",
            "timezone": "America/New_York",
        },
    )
    assert r.status_code == 200, r.text
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (r.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "America/New_York"


async def test_signup_without_timezone_defaults_to_utc(
    client: AsyncClient, auth_db: Path
):
    # No JS / no field at all -> server stores 'UTC'.
    r = await client.post(
        "/auth/signup",
        data={"username": "notz", "password": "passsword1", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (r.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "UTC"


async def test_signup_garbage_timezone_falls_back_to_utc_no_500(
    client: AsyncClient, auth_db: Path
):
    # A bogus timezone string must never 500; it's rejected -> 'UTC'.
    r = await client.post(
        "/auth/signup",
        data={
            "username": "badtz",
            "password": "passsword1",
            "consent": "true",
            "timezone": "Totally/Bogus",
        },
    )
    assert r.status_code == 200, r.text
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (r.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "UTC"


async def test_guest_creation_captures_timezone_from_form_field(
    client: AsyncClient, auth_db: Path
):
    g = await client.post("/auth/guest", data={"timezone": "Asia/Tokyo"})
    assert g.status_code == 200, g.text
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (g.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "Asia/Tokyo"


async def test_guest_creation_without_timezone_defaults_to_utc(
    client: AsyncClient, auth_db: Path
):
    g = await client.post("/auth/guest")
    assert g.status_code == 200
    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (g.json()["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "UTC"


async def test_guest_upgrade_keeps_guest_timezone_not_resubmitted(
    client: AsyncClient, auth_db: Path
):
    # Timezone is stored at row creation only: a guest created with a timezone
    # keeps it through an upgrade even if the signup form omits/changes it.
    g = await client.post("/auth/guest", data={"timezone": "Europe/Berlin"})
    owner_id = g.json()["user_id"]

    r = await client.post(
        "/auth/signup",
        data={
            "username": "tzupgrade",
            "password": "passsword1",
            "consent": "true",
            "timezone": "America/Los_Angeles",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is True
    assert r.json()["user_id"] == owner_id

    conn = _raw(auth_db)
    try:
        row = conn.execute(
            "SELECT timezone FROM user WHERE id = ?", (owner_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["timezone"] == "Europe/Berlin"


async def test_guest_upgrade_via_signup_returns_upgraded_true_and_display_name(
    client: AsyncClient, auth_db: Path
):
    """Guest-upgrade-in-place via /auth/signup: same row, prior data preserved,
    ``upgraded: true``, and ``display_name`` becomes the new username."""
    g = await client.post("/auth/guest")
    owner_id = g.json()["user_id"]
    _seed_entries_for(auth_db, owner_id, n_entries=2)

    r = await client.post(
        "/auth/signup",
        data={"username": "upgradeduser", "password": "passsword1", "consent": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["upgraded"] is True
    assert r.json()["user_id"] == owner_id
    assert r.json()["redirect_url"] == "/@upgradeduser"

    conn = _raw(auth_db)
    try:
        row = conn.execute("SELECT * FROM user WHERE id = ?", (owner_id,)).fetchone()
    finally:
        conn.close()
    assert row["auth_provider"] == "email"
    assert row["username"] == "upgradeduser"
    assert row["display_name"] == "upgradeduser"
    assert _count(auth_db, "user") == 1
    assert _count(auth_db, "entry", "owner_id = ?", (owner_id,)) == 2
