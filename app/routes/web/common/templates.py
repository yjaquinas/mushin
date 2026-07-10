"""Shared template environment, icons, and formatting helpers."""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from app import ui_strings
from app.services.entries import entries

_STATIC_DIR = Path(__file__).resolve().parents[3] / "static"
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


def _entry_tags_csv(memo: str | None) -> str:
    return ",".join(entries.parse_hashtags(memo or ""))


def _theme_from_cookie(value: str | None) -> str:
    return value if value in THEME_VALUES else "light"


def _theme_context(request: Request) -> dict[str, str]:
    return {"theme": _theme_from_cookie(request.cookies.get(THEME_COOKIE))}


def _canonical_url(request: Request) -> str:
    url = str(request.url)
    qs = url.find("?")
    return url[:qs] if qs != -1 else url


def _og_image_url(path: str | None = None) -> str:
    return path or ui_strings.OG_IMAGE_URL


_env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
templates = Jinja2Templates(env=_env, context_processors=[_theme_context])
templates.env.globals["strings"] = ui_strings
templates.env.globals["icon"] = _icon
templates.env.globals["static_asset"] = _static_asset
templates.env.globals["canonical_url"] = _canonical_url
templates.env.globals["og_image_url"] = _og_image_url
templates.env.filters["entry_tags_csv"] = _entry_tags_csv


def _format_occurred_at(occurred_at: str, time_known: bool = True) -> str:
    try:
        dt = datetime.fromisoformat(occurred_at)
        if not time_known:
            return dt.strftime("%Y-%m-%d")
        return f"{dt.strftime('%Y-%m-%d')} {dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    except (ValueError, AttributeError):
        return occurred_at


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


def _format_average_weekly_count(n: float) -> str:
    rounded = round(n, 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _format_streak_days(n: int) -> str:
    return f"{n}{ui_strings.STREAK_DAY_UNIT if n == 1 else ui_strings.STREAK_DAYS_UNIT}"


templates.env.filters["format_occurred_at"] = _format_occurred_at
templates.env.filters["format_entry_time"] = _format_entry_time
templates.env.filters["format_comment_timestamp"] = _format_comment_timestamp
templates.env.filters["format_count"] = _format_count
templates.env.filters["format_average_weekly_count"] = _format_average_weekly_count
templates.env.filters["streak_days"] = _format_streak_days
