"""Web (HTMX) surface — router assembly only.

A surface directory's ``__init__.py`` is wiring only: it assembles one
``router`` from each leaf route-group module's own ``APIRouter`` so
``app/main.py``'s existing ``from app.routes.web import router as web_router``
keeps working unchanged. No handler bodies belong here.

Re-exports
----------
Several names are re-exported below — not for new call sites, but because
``app/routes/public/`` and the test suite already import them as
``app.routes.web.<name>`` (predating this package split); re-exporting here
keeps both working unchanged. New code within this package should import
from the owning leaf module directly (``app.routes.web._shared`` /
``app.routes.web._contexts``) rather than through this re-export surface.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routes.web._calendar_context import (
    _resolve_comment_deep_link as _resolve_comment_deep_link,
)
from app.routes.web._contexts import (
    _build_card_context as _build_card_context,
)
from app.routes.web._contexts import (
    _build_fellows_context as _build_fellows_context,
)
from app.routes.web._contexts import (
    _build_home_context as _build_home_context,
)
from app.routes.web._contexts import (
    _field_defs_for_activity as _field_defs_for_activity,
)
from app.routes.web._contexts import (
    _list_sub_tallies as _list_sub_tallies,
)
from app.routes.web._history_context import (
    _build_card_top_tags as _build_card_top_tags,
)
from app.routes.web._history_context import (
    _build_field_stats_context as _build_field_stats_context,
)
from app.routes.web._history_context import (
    _build_history_context as _build_history_context,
)
from app.routes.web._shared import (
    _clear_flash as _clear_flash,
)
from app.routes.web._shared import (
    _current_user as _current_user,
)
from app.routes.web._shared import (
    _format_count as _format_count,
)
from app.routes.web._shared import (
    _format_entry_time as _format_entry_time,
)
from app.routes.web._shared import (
    _format_streak_days as _format_streak_days,
)
from app.routes.web._shared import (
    _home_url_context as _home_url_context,
)
from app.routes.web._shared import (
    _home_url_for as _home_url_for,
)
from app.routes.web._shared import (
    _read_flash as _read_flash,
)
from app.routes.web._shared import (
    _theme_context as _theme_context,
)
from app.routes.web._shared import (
    consent_gate_redirect as consent_gate_redirect,
)
from app.routes.web._shared import (
    templates as templates,
)
from app.routes.web.account import router as _account_router
from app.routes.web.account_consent import router as _account_consent_router
from app.routes.web.activities import router as _activities_router
from app.routes.web.activity_admin import router as _activity_admin_router
from app.routes.web.comments import router as _comments_router
from app.routes.web.entries import router as _entries_router
from app.routes.web.fellows import router as _fellows_router
from app.routes.web.history import router as _history_router
from app.routes.web.home import router as _home_router
from app.routes.web.search import router as _search_router

router = APIRouter()
router.include_router(_home_router)
router.include_router(_comments_router)
router.include_router(_account_router)
router.include_router(_account_consent_router)
router.include_router(_activities_router)
router.include_router(_activity_admin_router)
router.include_router(_history_router)
router.include_router(_entries_router)
router.include_router(_search_router)
router.include_router(_fellows_router)
