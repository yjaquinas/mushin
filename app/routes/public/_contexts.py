"""Shared template setup for the ``public`` surface.

Both ``profile.py`` and ``comments.py`` render through the same
``Jinja2Templates`` instance (so ``request.app`` context processors and
``strings``/``format_entry_time`` globals stay identical across both route
groups) — kept here once rather than duplicated.
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app import ui_strings
from app.routes.web import _format_entry_time, _home_url_context, _theme_context

templates = Jinja2Templates(
    directory="app/templates", context_processors=[_theme_context, _home_url_context]
)
templates.env.globals["strings"] = ui_strings
templates.env.filters["format_entry_time"] = _format_entry_time
