"""Best-effort visitor analytics middleware."""

from __future__ import annotations

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.services import visitors

log = structlog.get_logger()


class VisitorTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        try:
            visitors.record_request(request)
        except Exception as exc:
            log.warning("visitor_tracking.failed", error=str(exc))
        return response
