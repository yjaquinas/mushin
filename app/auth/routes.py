"""Auth / guest / upgrade routes for Mushin.

Exposed as an ``APIRouter`` (mounted at ``/auth`` from ``app.main``).
Deliberately separate from ``app/routes/web.py`` (the page-UI task owns that
file) so the two tasks don't collide on one module.

What lives here
---------------
* username + password signup + login (with an optional recovery email — no
  reset flow ships yet; email is never a login key)
* Google authorize-redirect + callback (userinfo is mocked in tests)
* guest creation on first interaction + a guest "log immediately" demo endpoint
* guest upgrade-in-place when a guest signs in
* account / guest deletion
* the consent gate (signup AND upgrade)

Consent
-------
Every account-*creating* and account-*attaching* path requires an explicit,
unbundled ``consent`` boolean that the caller must send ``true``. The form copy
links the privacy policy. Marketing-email consent, if ever added, is a
*separate* optional field — never bundled into this one. Without consent we
reject with 400 before any row is written/attached.

Sessions
--------
On success we set the signed session cookie via ``sessions.cookie_kwargs`` so
the ``HttpOnly; Secure; SameSite=Lax`` flags can't be dropped by a route.
"""

from __future__ import annotations

import os
import re
import secrets
import unicodedata
from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import oauth, passwords, sessions, users
from app.services import profiles

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# Placeholder privacy-policy link. The policy TEXT is the CEO's; this is the gate.
PRIVACY_POLICY_URL = "/privacy"

CONSENT_REQUIRED_MESSAGE = (
    f"Please agree to how we collect and use your data to continue. "
    f"(Privacy policy: {PRIVACY_POLICY_URL})"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_uid(cookie_value: str | None) -> int | None:
    """Resolve the signed session cookie to a user id (or None if logged out)."""
    return sessions.read_uid(cookie_value)


def _set_session(response: Response, user_id: int) -> None:
    """Attach the signed session cookie with the mandatory security flags."""
    response.set_cookie(value=sessions.sign_uid(user_id), **sessions.cookie_kwargs())


def _require_consent(consent: bool) -> None:
    if not consent:
        raise HTTPException(status_code=400, detail=CONSENT_REQUIRED_MESSAGE)


_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
_USERNAME_ERROR = (
    "Username must be 3-20 characters: lowercase letters, numbers, "
    "and underscores only."
)
# Loose x@y.z shape check — intentionally NOT a full RFC validator. Email is
# optional recovery metadata, never a login key.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_username(username: str) -> str:
    """Normalize a username to its canonical identity form.

    ``strip`` → NFKC (so visually-identical Unicode forms collapse) →
    ``casefold`` (aggressive lowercase). Validated against ``[a-z0-9_]{3,20}``
    after normalization; raises ``HTTPException(400)`` on any violation so
    ``foo``/``Foo``/``FOO`` all resolve to the one account ``foo``.
    """
    normalized = unicodedata.normalize("NFKC", username.strip()).casefold()
    if not _USERNAME_RE.match(normalized):
        raise HTTPException(status_code=400, detail=_USERNAME_ERROR)
    return normalized


def _normalize_email(email: str | None) -> str | None:
    """Lowercase + loose-shape-check an optional recovery email.

    Returns ``None`` for an absent/blank email (it's optional). Raises
    ``HTTPException(400)`` if a non-blank value isn't ``x@y.z``-shaped. This is
    recovery metadata only and is never used as a login key.
    """
    if email is None:
        return None
    cleaned = email.strip().lower()
    if not cleaned:
        return None
    if not _EMAIL_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="That email address looks malformed.")
    return cleaned


def _redirect_uri(provider: str) -> str:
    """The provider callback redirect URI (env-overridable for prod)."""
    env_key = f"{provider.upper()}_REDIRECT_URI"
    return os.getenv(env_key, f"https://mushin.aqnas.xyz/auth/{provider}/callback")


def _oauth_enabled() -> bool:
    """Whether the OAuth routes are exposed.

    The product is guest-only for now; Google sign-in is hidden behind
    this flag. The underlying OAuth code (provider-attach/upgrade logic) is kept
    intact for a future re-enable — only the route surface is gated. Default off
    so existing deployments that don't set the var stay guest-only with no
    regression.
    """
    return os.getenv("OAUTH_ENABLED", "false").lower() == "true"


def _known_provider(provider: str) -> bool:
    """True only when OAuth is enabled AND the provider is one we support.

    A disabled flag is deliberately indistinguishable from "provider doesn't
    exist": both paths raise the same 404, so a caller can't probe whether OAuth
    is merely turned off versus unimplemented.
    """
    return _oauth_enabled() and provider == "google"


# ---------------------------------------------------------------------------
# Username / password (with optional recovery email)
# ---------------------------------------------------------------------------


@router.post("/signup")
async def username_signup(
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    consent: Annotated[bool, Form()] = False,
    timezone: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> JSONResponse:
    """Create a username/password account (or upgrade the current guest in place).

    Identity is the (normalized) ``username``; ``email`` is an optional recovery
    address only (never a login key). Requires explicit unbundled consent. The
    password is hashed with Argon2id; plaintext is never logged. If the caller
    already has a guest session, this upgrades that guest **in place** (zero data
    migration).
    """
    _require_consent(consent)
    if not password:
        raise HTTPException(status_code=400, detail="username and password are required")

    username = _normalize_username(username)
    email = _normalize_email(email)
    password_hash = passwords.hash_password(password)
    current = _current_uid(session)

    # Guest-upgrade-in-place path.
    if current is not None:
        guest = users.get_user(current)
        if guest is not None and guest["auth_provider"] == "guest":
            if users.find_by_username(username) is not None:
                # The username already maps to a real account: do not merge.
                raise HTTPException(
                    status_code=409,
                    detail="That username already has an account. "
                    "Choose whether to keep or discard your guest data.",
                )
            if email is not None and users.find_by_email(email) is not None:
                raise HTTPException(
                    status_code=409,
                    detail="That email already has an account. "
                    "Choose whether to keep or discard your guest data.",
                )
            user = users.attach_provider(
                current,
                "email",
                username=username,
                password_hash=password_hash,
                email=email,
            )
            resp = JSONResponse(
                {
                    "user_id": user["id"],
                    "upgraded": True,
                    "redirect_url": profiles.canonical_profile_url(username),
                }
            )
            _set_session(resp, user["id"])
            log.info("auth.upgrade.email", user_id=user["id"])
            return resp

    # Fresh signup. Timezone is stored at creation only (the guest-upgrade path
    # above keeps the timezone already stamped on the guest row at guest-create).
    try:
        user_id = users.create_username_user(username, password_hash, email, timezone)
    except users.IdentityTakenError as exc:
        # Generic message: don't leak whether the username or email collided.
        raise HTTPException(
            status_code=409, detail="That username is already taken."
        ) from exc

    resp = JSONResponse(
        {
            "user_id": user_id,
            "upgraded": False,
            "redirect_url": profiles.canonical_profile_url(username),
        }
    )
    _set_session(resp, user_id)
    log.info("auth.signup.email", user_id=user_id)
    return resp


@router.post("/login")
async def username_login(
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    timezone: Annotated[str | None, Form()] = None,  # noqa: ARG001 - form parity only
) -> JSONResponse:
    """Log in with username/password. Wrong username or password is 401.

    The username is normalized before lookup so ``Foo`` and ``foo`` resolve to
    the same account. Verification is constant-time Argon2id; plaintext is never
    logged.
    """
    username = _normalize_username(username)
    user = users.find_by_username(username)
    if user is None or not passwords.verify_password(user["password_hash"], password):
        # Same response whether the username is unknown or the password is wrong,
        # so we don't leak which usernames are registered.
        raise HTTPException(status_code=401, detail="That username or password isn't right.")

    resp = JSONResponse(
        {
            "user_id": user["id"],
            "redirect_url": profiles.canonical_profile_url(user["username"]),
        }
    )
    _set_session(resp, user["id"])
    log.info("auth.login.email", user_id=user["id"])
    return resp


# ---------------------------------------------------------------------------
# OAuth — Google
# ---------------------------------------------------------------------------


@router.get("/{provider}/authorize")
async def oauth_authorize(provider: str, response: Response) -> RedirectResponse:
    """Redirect the browser to the provider's consent screen.

    A random ``state`` is set in an HttpOnly cookie and echoed back on callback
    to defend against CSRF on the OAuth round-trip.
    """
    if not _known_provider(provider):
        raise HTTPException(status_code=404, detail="unknown provider")
    state = secrets.token_urlsafe(24)
    url = oauth.authorize_url(provider, _redirect_uri(provider), state)
    redirect = RedirectResponse(url, status_code=302)
    redirect.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return redirect


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str | None = None,
    oauth_state: Annotated[str | None, Cookie()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> JSONResponse:
    """Handle the OAuth redirect-back: exchange code, find/create/upgrade user.

    Identity is ``(auth_provider, provider_id)``. If the caller is currently a
    guest, the provider is **attached in place** (upgrade) unless that identity
    already maps to a different account — in which case we surface the
    replace/discard decision rather than merging.

    ``oauth.fetch_userinfo`` is monkeypatched in tests, so this whole path runs
    without live credentials or network.
    """
    if not _known_provider(provider):
        raise HTTPException(status_code=404, detail="unknown provider")
    # CSRF state check (skipped only when no state cookie was set, e.g. tests
    # hitting the callback directly with a mocked userinfo).
    if oauth_state is not None and state != oauth_state:
        raise HTTPException(status_code=400, detail="invalid oauth state")

    try:
        identity = oauth.fetch_userinfo(provider, code, _redirect_uri(provider))
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=502, detail="OAuth provider error") from exc

    existing = users.find_by_provider(identity.auth_provider, identity.provider_id)
    current = _current_uid(session)
    guest = None
    if current is not None:
        candidate = users.get_user(current)
        if candidate is not None and candidate["auth_provider"] == "guest":
            guest = candidate

    # --- Guest upgrade-in-place ------------------------------------------
    if guest is not None:
        if existing is not None:
            # OAuth identity already owns a real account. No merge. Surface the
            # decision: replace (keep this account, discard guest) or discard.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "identity_exists",
                    "message": "You already have an account with this login. "
                    "Keep or discard your guest data.",
                    "existing_user_id": existing["id"],
                    "guest_user_id": guest["id"],
                },
            )
        user = users.attach_provider(
            guest["id"],
            identity.auth_provider,
            provider_id=identity.provider_id,
            display_name=identity.display_name,
        )
        resp = JSONResponse({"user_id": user["id"], "upgraded": True})
        _set_session(resp, user["id"])
        log.info("auth.upgrade.oauth", provider=provider, user_id=user["id"])
        return resp

    # --- Plain login / fresh signup --------------------------------------
    if existing is not None:
        resp = JSONResponse({"user_id": existing["id"], "upgraded": False})
        _set_session(resp, existing["id"])
        log.info("auth.login.oauth", provider=provider, user_id=existing["id"])
        return resp

    user_id = users.create_oauth_user(
        identity.auth_provider, identity.provider_id, identity.display_name
    )
    resp = JSONResponse({"user_id": user_id, "upgraded": False})
    _set_session(resp, user_id)
    log.info("auth.signup.oauth", provider=provider, user_id=user_id)
    return resp


# ---------------------------------------------------------------------------
# Guest mode
# ---------------------------------------------------------------------------


@router.post("/guest")
async def guest_start(
    response: Response,
    timezone: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> JSONResponse:
    """Mint a guest account on the user's *first interaction* and start a session.

    This is an explicit POST the UI calls when the user *acts* — never a
    middleware on GET — so a bare page load (or a bot crawling) creates no row.
    Idempotent for an existing valid session: if the caller already has a user
    (guest or real), we return it instead of minting a duplicate. *timezone* is
    the untrusted browser-detected IANA name, persisted on the guest row at
    creation only.
    """
    current = _current_uid(session)
    if current is not None and users.get_user(current) is not None:
        users.touch_last_active(current)
        return JSONResponse({"user_id": current, "created": False})

    user_id = users.create_guest(timezone)
    resp = JSONResponse({"user_id": user_id, "created": True})
    _set_session(resp, user_id)
    log.info("auth.guest.created", user_id=user_id)
    return resp


# ---------------------------------------------------------------------------
# Deletion (account + guest) — data-subject right
# ---------------------------------------------------------------------------


@router.post("/delete")
async def delete_account(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    """Delete the current account (real or guest) and ALL its data, then log out.

    Cookie-bound: a guest is a data subject and deletes via this same
    control. The cascade (schema ``ON DELETE CASCADE``) removes every owned row
    including memos. The session cookie is cleared on the response.
    """
    current = _current_uid(session)
    if current is None or users.get_user(current) is None:
        raise HTTPException(status_code=401, detail="no active session")

    users.delete_user(current)
    resp = JSONResponse({"deleted": True})
    resp.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    log.info("auth.account.deleted", user_id=current)
    return resp


@router.post("/logout")
async def logout() -> Response:
    """Clear the session cookie (does not delete data)."""
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------------------
# Session inspection (used by the UI / tests)
# ---------------------------------------------------------------------------


@router.get("/me")
async def whoami(
    request: Request,  # noqa: ARG001 - reserved for future per-request context
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> JSONResponse:
    """Return the current user's identity summary, or ``{"user_id": null}``."""
    current = _current_uid(session)
    if current is None:
        return JSONResponse({"user_id": None})
    user = users.get_user(current)
    if user is None:
        return JSONResponse({"user_id": None})
    return JSONResponse(
        {
            "user_id": user["id"],
            "auth_provider": user["auth_provider"],
            "display_name": user["display_name"],
        }
    )
