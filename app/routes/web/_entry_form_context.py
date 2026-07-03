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
        },
        {
            "id": "num_value",
            "kind": "count",
            "label": "Value",
            "prefilled_value": entry.get("num_value") or "",
        },
    ]


def _build_log_sheet_fields(conn: sqlite3.Connection, activity_id: int) -> list[dict[str, Any]]:
    """Build log sheet fields — simplified, no field system."""
    return [
        {"id": "memo", "kind": "memo", "label": "Memo"},
    ]
