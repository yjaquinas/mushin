"""Shared template environment, icons, and formatting helpers."""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app import ui_strings

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
_ICONS_DIR = _STATIC_DIR / "icons"
THEME_COOKIE = "mushin_theme"
THEME_VALUES = ("light", "dark")
THEME_CYCLE = {"light": "dark", "dark": "light"}


@lru_cache(maxsize=None)
def _load_icon_raw(name: str) -> str:
    path = _ICONS_DIR / f"{name}.svg"
    return (path if path.exists() else _ICONS_DIR / "circle-dot.svg").read_text()


def _icon(name: str, size: int = 20) -> Markup:
    content = _load_icon_raw(name)
    return Markup(re.sub(r'height="\d+"', f'height="{size}"', re.sub(r'width="\d+"', f'width="{size}"', content, count=1), count=1))


@lru_cache(maxsize=None)
def _asset_version(path: str) -> str:
    target = _STATIC_DIR / path.removeprefix("/static/").lstrip("/")
    return str(target.stat().st_mtime_ns) if target.exists() else "0"


def _static_asset(path: str) -> str:
    return f"{path}?v={_asset_version(path)}" if path.startswith("/static/") else path


def _theme_from_cookie(value: str | None) -> str:
    return value if value in THEME_VALUES else "light"


def _theme_context(request: Request) -> dict[str, str]:
    return {"theme": _theme_from_cookie(request.cookies.get(THEME_COOKIE))}


templates = Jinja2Templates(directory="app/templates", context_processors=[_theme_context])
templates.env.globals["strings"] = ui_strings
templates.env.globals["icon"] = _icon
templates.env.globals["static_asset"] = _static_asset


def _format_entry_time(occurred_at: str) -> str:
    try:
        dt = datetime.fromisoformat(occurred_at)
        return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    except (ValueError, AttributeError):
        return ""


def _format_comment_timestamp(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
        return f"{dt.strftime('%Y-%m-%d')} {dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    except (ValueError, AttributeError):
        return ""


def _format_count(n: int) -> str:
    if n < 1000:
        return str(n)
    whole, remainder, suffix, divisor = (
        (*divmod(n, 1000), "k", 1000) if n < 1_000_000 else (*divmod(n, 1_000_000), "m", 1_000_000)
    )
    tenths = (remainder * 10) // divisor
    return f"{whole}{suffix}" if tenths == 0 else f"{whole}.{tenths}{suffix}"


def _format_streak_days(n: int) -> str:
    return f"{n}{ui_strings.STREAK_DAY_UNIT if n == 1 else ui_strings.STREAK_DAYS_UNIT}"


templates.env.filters["format_entry_time"] = _format_entry_time
templates.env.filters["format_comment_timestamp"] = _format_comment_timestamp
templates.env.filters["format_count"] = _format_count
templates.env.filters["streak_days"] = _format_streak_days
