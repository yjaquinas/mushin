"""Shared helpers for the web route surface."""

from app.routes.web.common.auth import (
    _current_user,
    _home_url_context,
    _home_url_for,
    consent_gate_redirect,
)
from app.routes.web.common.flash import _clear_flash, _read_flash, _set_flash
from app.routes.web.common.templates import (
    THEME_COOKIE,
    THEME_CYCLE,
    _format_count,
    _format_entry_time,
    _format_streak_days,
    _theme_context,
    _theme_from_cookie,
    templates,
    ui_strings,
)

templates.context_processors = [_theme_context, _home_url_context]

__all__ = [
    "THEME_COOKIE",
    "THEME_CYCLE",
    "_clear_flash",
    "_current_user",
    "_format_count",
    "_format_entry_time",
    "_format_streak_days",
    "_home_url_context",
    "_home_url_for",
    "_read_flash",
    "_set_flash",
    "_theme_context",
    "_theme_from_cookie",
    "consent_gate_redirect",
    "templates",
    "ui_strings",
]
