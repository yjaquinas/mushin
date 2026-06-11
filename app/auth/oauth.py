"""Kakao + Google OAuth — authorization-code flow, userinfo normalization.

Two real providers:

* **Kakao** — scope ``profile_nickname`` only. We deliberately request *no*
  email or phone (less personal data collected = less PIPA surface). Identity is
  the Kakao numeric user id; the nickname becomes ``display_name``.
* **Google** — scope ``openid email profile``. Identity is the OIDC ``sub``
  claim; ``name`` becomes ``display_name``; ``email`` is captured as the email.

All client ids/secrets come from ``os.getenv`` (never hardcoded):
``KAKAO_REST_API_KEY``, ``KAKAO_CLIENT_SECRET``, ``GOOGLE_CLIENT_ID``,
``GOOGLE_CLIENT_SECRET``.

Testability seam
----------------
``fetch_userinfo(provider, code, redirect_uri)`` is the single function the
routes call. It performs the token exchange and the userinfo request over the
network. Tests monkeypatch *this* function (or the lower-level
``_exchange_code`` / ``_get_userinfo``) so no live credentials or HTTP are
needed — the callback logic (find-or-create / upgrade by ``(auth_provider,
provider_id)``) is exercised against a mocked provider response.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USERINFO_URL = "https://kapi.kakao.com/v2/user/me"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

KAKAO_SCOPE = "profile_nickname"
GOOGLE_SCOPE = "openid email profile"


class OAuthError(Exception):
    """Raised when an OAuth provider exchange or userinfo call fails."""


@dataclass(frozen=True)
class OAuthIdentity:
    """Normalized identity from any provider.

    ``provider_id`` is the stable per-provider subject (Kakao id / Google sub),
    used for ``(auth_provider, provider_id)`` lookup. ``email`` is ``None`` for
    Kakao by design.
    """

    auth_provider: str
    provider_id: str
    display_name: str | None
    email: str | None = None


# ---------------------------------------------------------------------------
# Authorize URL construction (no secrets leak into the URL — only the public id)
# ---------------------------------------------------------------------------


def authorize_url(provider: str, redirect_uri: str, state: str) -> str:
    """Build the provider authorize URL the browser is redirected to."""
    if provider == "kakao":
        client_id = _require_env("KAKAO_REST_API_KEY")
        return (
            f"{KAKAO_AUTHORIZE_URL}?response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_uri}&scope={KAKAO_SCOPE}&state={state}"
        )
    if provider == "google":
        client_id = _require_env("GOOGLE_CLIENT_ID")
        return (
            f"{GOOGLE_AUTHORIZE_URL}?response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_uri}&scope={GOOGLE_SCOPE.replace(' ', '%20')}"
            f"&state={state}"
        )
    raise OAuthError(f"unknown provider {provider!r}")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise OAuthError(f"{name} is not configured")
    return value


# ---------------------------------------------------------------------------
# Token exchange + userinfo (the network seam — monkeypatched in tests)
# ---------------------------------------------------------------------------


def _exchange_code(provider: str, code: str, redirect_uri: str) -> str:
    """Exchange an authorization *code* for an access token. Returns the token."""
    if provider == "kakao":
        data = {
            "grant_type": "authorization_code",
            "client_id": _require_env("KAKAO_REST_API_KEY"),
            "client_secret": _require_env("KAKAO_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        }
        token_url = KAKAO_TOKEN_URL
    elif provider == "google":
        data = {
            "grant_type": "authorization_code",
            "client_id": _require_env("GOOGLE_CLIENT_ID"),
            "client_secret": _require_env("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        }
        token_url = GOOGLE_TOKEN_URL
    else:
        raise OAuthError(f"unknown provider {provider!r}")

    resp = httpx.post(token_url, data=data, timeout=10.0)
    if resp.status_code != 200:
        raise OAuthError(f"{provider} token exchange failed: {resp.status_code}")
    token = resp.json().get("access_token")
    if not token:
        raise OAuthError(f"{provider} token response had no access_token")
    return token


def _get_userinfo(provider: str, access_token: str) -> dict[str, Any]:
    """Fetch the raw userinfo payload for *provider* using *access_token*."""
    url = KAKAO_USERINFO_URL if provider == "kakao" else GOOGLE_USERINFO_URL
    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    if resp.status_code != 200:
        raise OAuthError(f"{provider} userinfo failed: {resp.status_code}")
    return resp.json()


def fetch_userinfo(provider: str, code: str, redirect_uri: str) -> OAuthIdentity:
    """End-to-end: exchange *code*, fetch userinfo, return a normalized identity.

    This is the function the callback route calls and the function tests mock.
    """
    access_token = _exchange_code(provider, code, redirect_uri)
    raw = _get_userinfo(provider, access_token)
    return normalize(provider, raw)


def normalize(provider: str, raw: dict[str, Any]) -> OAuthIdentity:
    """Map a raw provider userinfo payload to an ``OAuthIdentity``.

    Kept separate from the network call so tests can verify normalization on
    canned payloads, and so a mocked ``_get_userinfo`` flows through the real
    mapping logic.
    """
    if provider == "kakao":
        # { "id": 12345, "kakao_account": {"profile": {"nickname": "철수"}}, ... }
        provider_id = raw.get("id")
        if provider_id is None:
            raise OAuthError("kakao userinfo missing id")
        nickname = raw.get("kakao_account", {}).get("profile", {}).get("nickname") or raw.get(
            "properties", {}
        ).get("nickname")
        return OAuthIdentity(
            auth_provider="kakao",
            provider_id=str(provider_id),
            display_name=nickname,
            email=None,
        )
    if provider == "google":
        # OIDC userinfo: { "sub": "1078...", "name": "...", "email": "..." }
        sub = raw.get("sub")
        if not sub:
            raise OAuthError("google userinfo missing sub")
        return OAuthIdentity(
            auth_provider="google",
            provider_id=str(sub),
            display_name=raw.get("name"),
            email=raw.get("email"),
        )
    raise OAuthError(f"unknown provider {provider!r}")
