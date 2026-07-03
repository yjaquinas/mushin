"""OAuth — REMOVED.

Simple username/password auth only. This module is kept as a stub
so import paths don't break.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OAuthIdentity:
    """Stub — OAuth removed."""
    auth_provider: str
    provider_id: str
    display_name: str | None
    email: str | None = None


def authorize_url(provider: str, redirect_uri: str, state: str) -> str:
    raise RuntimeError("OAuth is disabled")


def fetch_userinfo(provider: str, code: str, redirect_uri: str) -> OAuthIdentity:
    raise RuntimeError("OAuth is disabled")


def normalize(provider: str, raw: dict[str, Any]) -> OAuthIdentity:
    raise RuntimeError("OAuth is disabled")
