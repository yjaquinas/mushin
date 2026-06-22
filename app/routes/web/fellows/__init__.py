"""Fellows (social graph) — router assembly only.

Per ``.claude/rules/route-structure.md``, this ``__init__.py`` is wiring
only: it assembles one ``router`` from each leaf route-group module's own
``APIRouter`` so ``app/routes/web/__init__.py`` can include it unchanged.
No handler bodies belong here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routes.web.fellows.block import router as _block_router
from app.routes.web.fellows.connection import router as _connection_router

router = APIRouter()
router.include_router(_connection_router)
router.include_router(_block_router)
