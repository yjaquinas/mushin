"""Public (unauthenticated) surface — router assembly only.

A surface directory's ``__init__.py`` is wiring only: it assembles one
``router`` from each leaf route-group module's own ``APIRouter`` so
``app/main.py``'s existing ``from app.routes.public import router as
public_router`` keeps working unchanged. No handler bodies belong here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routes.public.common.contexts import templates as templates
from app.routes.public.activity.routes import router as _activity_detail_router
from app.routes.public.comments.routes import router as _comments_router
from app.routes.public.profile.routes import router as _profile_router

# ``templates`` is re-exported above so existing call sites (e.g. a test
# monkeypatching ``app.routes.public.templates.TemplateResponse``) keep
# working unchanged after the module split — it's the single shared
# Jinja2Templates instance every leaf module in this package renders
# through (see ``_contexts.py``).

router = APIRouter()
router.include_router(_profile_router)
router.include_router(_activity_detail_router)
router.include_router(_comments_router)
