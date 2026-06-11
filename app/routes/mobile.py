"""Mobile (Hyperview/HXML) routes for Mushin.

All mobile endpoints live under /m/. Responses must set
media_type="application/vnd.hyperview+xml" or the client silently ignores them.
See .claude/rules/mobile-templates.md and the hyperview-patterns skill.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/m")

# Register mobile routes here, e.g.:
#
# @router.get("/categories")
# async def list_categories(request: Request) -> Response:
#     return templates_mobile.TemplateResponse(
#         request=request,
#         name="index.hxml.jinja2",
#         context={...},
#         media_type="application/vnd.hyperview+xml",
#     )
