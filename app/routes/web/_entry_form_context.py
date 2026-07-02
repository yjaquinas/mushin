"""Entry form context helpers shared by edit and log-sheet handlers."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.routes.web._context_cards import _EMPTY_MATCH_ROW, _field_defs_for_activity


def _build_edit_fields_context(conn: sqlite3.Connection, owner_id: int, activity_id: int, entry: dict[str, Any]) -> list[dict[str, Any]]:
    field_defs = _field_defs_for_activity(conn, activity_id)
    entry_values = {ev["field_def_id"]: ev for ev in entry.get("values") or []}
    fields: list[dict[str, Any]] = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {"id": fd["id"], "kind": fd["kind"], "label": fd["label"]}
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = entry.get("memo") or ""
        elif fd["kind"] in ("count", "scale"):
            ev = entry_values.get(fd["id"])
            field_ctx["prefilled_value"] = ev["num_value"] if ev is not None and ev.get("num_value") is not None else ""
        fields.append(field_ctx)
    return fields


def _build_log_sheet_fields(conn: sqlite3.Connection, activity_id: int) -> list[dict[str, Any]]:
    fields = []
    for fd in _field_defs_for_activity(conn, activity_id):
        field_ctx: dict[str, Any] = {"id": fd["id"], "kind": fd["kind"], "label": fd["label"]}
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = ""
        elif fd["kind"] == "match_list":
            field_ctx["rows"] = [dict(_EMPTY_MATCH_ROW)]
        fields.append(field_ctx)
    return fields

