"""Flash-cookie helpers for the web surface."""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from app import ui_strings

FLASH_COOKIE = "mushin_flash"
_FLASH_SALT = "mushin.flash.v1"
_FLASH_MAX_AGE = 30
_FLASH_MESSAGES: dict[str, str] = {
    "visibility_public": ui_strings.HOME_FLASH_VISIBILITY_PUBLIC,
    "visibility_private": ui_strings.HOME_FLASH_VISIBILITY_PRIVATE,
}


def _flash_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(os.getenv("SESSION_SECRET", ""), salt=_FLASH_SALT)


def _set_flash(response: RedirectResponse, key: str) -> None:
    response.set_cookie(
        key=FLASH_COOKIE,
        value=_flash_serializer().dumps({"key": key}),
        max_age=_FLASH_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _read_flash(request: Request) -> str | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    try:
        data = _flash_serializer().loads(raw)
    except BadSignature:
        return None
    key = data.get("key") if isinstance(data, dict) else None
    return _FLASH_MESSAGES.get(key) if isinstance(key, str) else None


def _clear_flash(response: HTMLResponse) -> None:
    response.delete_cookie(key=FLASH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")

