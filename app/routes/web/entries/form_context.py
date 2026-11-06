"""Entry form context helpers shared by edit and log-sheet handlers."""

from __future__ import annotations

import sqlite3
from typing import Any


def _build_edit_fields_context(conn: sqlite3.Connection, owner_id: int, activity_id: int, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Build edit fields — simplified, no field system."""
    return [
        {
            "id": "memo",
            "kind": "memo",
            "label": "Memo",
            "prefilled_value": entry.get("memo") or "",
            "suggested_tags": suggestions(conn, owner_id, activity_id),
        },
    ]


def _build_log_sheet_fields(conn: sqlite3.Connection, activity_id: int, owner_id: int) -> list[dict[str, Any]]:
    """Build log sheet fields — simplified, no field system."""
    return [
        {"id": "memo", "kind": "memo", "label": "Memo", "suggested_tags": suggestions(conn, owner_id, activity_id)},
    ]


def suggestions(conn: sqlite3.Connection, owner_id: int, activity_id: int) -> list[str]:
    from app.services.entries.tag_suggestions import activity_tags
    return activity_tags(conn, owner_id, activity_id)
