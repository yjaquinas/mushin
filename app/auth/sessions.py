"""Signed-cookie sessions for Mushin.

A session is a tiny signed payload (``{"uid": <user_id>}``) carried in a single
cookie. We sign — not encrypt — with ``itsdangerous`` keyed on ``SESSION_SECRET``
from the environment; the cookie holds no secret, only an integer user id that
the signature makes unforgeable. There is **no token in localStorage**: the
browser never sees JavaScript-readable auth state, because the cookie is
``HttpOnly``.

Cookie flags (every session cookie, always):

* ``HttpOnly``  — JS cannot read it (XSS can't exfiltrate the session).
* ``Secure``    — sent only over HTTPS.
* ``SameSite=Lax`` — sent on top-level navigations, not on cross-site POSTs
  (CSRF mitigation that still allows the OAuth redirect-back GET).

The same mechanism backs both real and guest accounts — a guest session is just
a session whose ``uid`` happens to point at an ``auth_provider='guest'`` row.
"""

from __future__ import annotations

import os

from itsdangerous import BadSignature, URLSafeSerializer

COOKIE_NAME = "mushin_session"

# 30 days. Guests are reaped server-side well before this by the retention timer
# (Task 11); for real accounts this is the rolling login lifetime.
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

# Salt namespaces the signature so a leaked signer for one purpose can't be
# replayed against another. The secret itself is the real protection.
_SALT = "mushin.session.v1"


class SessionConfigError(RuntimeError):
    """Raised when SESSION_SECRET is missing — fail closed, never sign with a default."""


def _serializer() -> URLSafeSerializer:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        raise SessionConfigError(
            "SESSION_SECRET is not set; refusing to sign sessions with a default key"
        )
    return URLSafeSerializer(secret, salt=_SALT)


def sign_uid(user_id: int) -> str:
    """Return the signed cookie value for *user_id*."""
    return _serializer().dumps({"uid": int(user_id)})


def read_uid(cookie_value: str | None) -> int | None:
    """Return the user id from a signed cookie value, or ``None`` if absent/invalid.

    A tampered or stale-secret cookie returns ``None`` (treated as logged-out)
    rather than raising — the request simply proceeds unauthenticated.
    """
    if not cookie_value:
        return None
    try:
        data = _serializer().loads(cookie_value)
    except BadSignature:
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return int(uid) if isinstance(uid, int) else None


def cookie_kwargs(*, max_age: int = COOKIE_MAX_AGE) -> dict[str, object]:
    """Keyword args for ``Response.set_cookie`` enforcing the security flags.

    Centralised so no route can accidentally drop ``HttpOnly`` / ``Secure`` /
    ``SameSite``.
    """
    return {
        "key": COOKIE_NAME,
        "max_age": max_age,
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "path": "/",
    }
