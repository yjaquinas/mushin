"""Match rows — DROPPED.

The match table has been removed. This module is kept as a stub.
"""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.models import db
from app.routes.web._shared import templates
from app.services import _db


def _require_match_list_field(
    conn: sqlite3.Connection, activity_id: int, field_def_id: int
) -> sqlite3.Row | None:
    """No-op: match_list removed."""
    return None


async def add_match_row_body(
    request: Request,
    activity_id: int,
    field_def_id: int,
    owner_id: int,
) -> HTMLResponse:
    """No-op: match rows removed."""
    return HTMLResponse(status_code=404)


async def remove_match_row_body(
    request: Request,
    activity_id: int,
    field_def_id: int,
    row_index: int,
    owner_id: int,
) -> HTMLResponse:
    """No-op: match rows removed."""
    return HTMLResponse(status_code=404)
