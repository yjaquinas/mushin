"""Shared template setup for the ``public`` surface.

Both ``profile.py`` and ``comments.py`` render through the same
``Jinja2Templates`` instance — re-exported from ``app.routes.web.common``
so context processors, globals, and filters stay identical across surfaces
with a single source of truth.
"""

from __future__ import annotations

from app.routes.web.common import templates as templates  # noqa: F401

__all__ = ["templates"]
