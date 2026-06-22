"""Shared template setup + preview-alias constants for the ``public`` surface.

Both ``profile.py`` and ``comments.py`` render through the same
``Jinja2Templates`` instance (so ``request.app`` context processors and
``strings``/``format_entry_time`` globals stay identical across both route
groups) and recognize the same ``?as=`` preview aliases — kept here once
rather than duplicated.
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

# Aliases accepted on the ``?as=`` preview query param. ``visitor`` is a
# legacy alias for ``stranger`` so existing links/strings/tests keep working.
_STRANGER_ALIASES = {"stranger", "visitor"}
_CONNECTION_ALIAS = "connection"
