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
from the owning leaf module directly (``app.routes.web.common`` /
``app.routes.web.home.contexts``) rather than through this re-export surface.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routes.web.history.calendar import (
    _resolve_comment_deep_link as _resolve_comment_deep_link,
)
from app.routes.web.home.contexts import (
    _build_card_context as _build_card_context,
)
from app.routes.web.home.contexts import (
    _build_fellows_context as _build_fellows_context,
)
from app.routes.web.home.contexts import (
    _build_home_context as _build_home_context,
)
from app.routes.web.home.contexts import (
    _field_defs_for_activity as _field_defs_for_activity,
)
from app.routes.web.home.contexts import (
    _list_activities as _list_activities,
)
from app.routes.web.history.context import (
    _build_card_top_tags as _build_card_top_tags,
)
from app.routes.web.history.context import (
    _build_field_stats_context as _build_field_stats_context,
)
from app.routes.web.history.context import (
    _build_history_context as _build_history_context,
)
from app.routes.web.history.context import (
    _build_history_tags as _build_history_tags,
)
from app.routes.web.common import (
    _clear_flash as _clear_flash,
)
from app.routes.web.common import (
    _current_user as _current_user,
)
from app.routes.web.common import (
    _format_count as _format_count,
)
from app.routes.web.common import (
    _format_entry_time as _format_entry_time,
)
from app.routes.web.common import (
    _format_streak_days as _format_streak_days,
)
from app.routes.web.common import (
    _home_url_context as _home_url_context,
)
from app.routes.web.common import (
    _home_url_for as _home_url_for,
)
from app.routes.web.common import (
    _read_flash as _read_flash,
)
from app.routes.web.common import (
    _theme_context as _theme_context,
)
from app.routes.web.common import (
    consent_gate_redirect as consent_gate_redirect,
)
from app.routes.web.common import (
    templates as templates,
)
from app.routes.web.settings.routes import router as _settings_router
from app.routes.web.settings.consent_routes import router as _settings_consent_router
from app.routes.web.activities.routes import router as _activities_router
from app.routes.web.activities.admin_routes import router as _activity_admin_router
from app.routes.web.comments.routes import router as _comments_router
from app.routes.web.entries.routes import router as _entries_router
from app.routes.web.fellows import router as _fellows_router
from app.routes.web.history.routes import router as _history_router
from app.routes.web.home.routes import router as _home_router
from app.routes.web.guides.routes import router as _guides_router
from app.routes.web.social.routes import router as _social_router
from app.routes.web.legal.routes import router as _legal_router
from app.routes.web.notifications.routes import router as _notifications_router
from app.routes.web.profile.routes import router as _profile_router

router = APIRouter()
router.include_router(_home_router)
router.include_router(_guides_router)
router.include_router(_comments_router)
router.include_router(_notifications_router)
router.include_router(_settings_router)
router.include_router(_settings_consent_router)
router.include_router(_activities_router)
router.include_router(_activity_admin_router)
router.include_router(_history_router)
router.include_router(_entries_router)
router.include_router(_social_router)
router.include_router(_fellows_router)
router.include_router(_legal_router)
router.include_router(_profile_router)
