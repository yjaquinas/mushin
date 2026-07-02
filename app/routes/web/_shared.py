"""Re-export shared web helpers from focused companion modules."""

from app.routes.web._shared_auth import _current_user, _home_url_context, _home_url_for, consent_gate_redirect
from app.routes.web._shared_flash import _clear_flash, _read_flash, _set_flash
from app.routes.web._shared_templates import (
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
