"""Data-portability export/import for Mushin.

Simplified for the new flat schema: no field_defs, tags, entry_tags,
entry_values, or matches. Only activities, entries (with memo, num_value,
tags), and social graph metadata.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.models import db
from app.models.db import connect

SCHEMA_VERSION = 3


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_data(owner_id: int) -> dict:
    """Return the full snapshot for *owner_id*.

    Output shape::

        {
            "schema_version": 3,
            "exported_at": "<ISO 8601 UTC>",
            "data": {
                "activities": [...],
                "entries": [...],
            },
            "social_graph": {
                "fellows": [...],
                "pending_requests": [...],
                "blocked": [...],
            },
        }

    What is deliberately excluded:
    - ``owner_id`` on every row (implicit — belongs to one owner).
    - Everything in the ``user`` table (auth secrets, session tokens).
    - Derived/cached columns on ``activity`` (``count``, ``streak``,
      ``last_entry_at``) — rebuilt from truth on import.
    """
    with connect() as conn:
        conn.execute("BEGIN")
        activities = conn.execute(
            "SELECT id, name, slug, sort_order, archived_at, created_at, icon"
            " FROM activity WHERE owner_id = ? ORDER BY sort_order, id",
            (owner_id,),
        ).fetchall()

        activity_list: list[dict[str, Any]] = []
        for act in activities:
            entries = conn.execute(
                "SELECT occurred_at, memo, num_value, tags, time_known"
                " FROM entry"
                " WHERE owner_id = ? AND activity_id = ?"
                " ORDER BY occurred_at DESC",
                (owner_id, act["id"]),
            ).fetchall()

            activity_list.append({
                "name": act["name"],
                "slug": act["slug"],
                "icon": act["icon"],
                "entries": [
                    {
                        "occurred_at": e["occurred_at"],
                        "memo": e["memo"] or "",
                        "num_value": float(e["num_value"]) if e["num_value"] is not None else None,
                        "tags": e["tags"] or "",
                        "time_known": e["time_known"] == 1,
                    }
                    for e in entries
                ],
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "data": {
            "activities": activity_list,
        },
        "social_graph": {
            "fellows": [],
            "pending_requests": [],
            "blocked": [],
        },
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class ImportValidationError(ValueError):
    """Raised when the import payload is invalid."""


def import_data(owner_id: int, payload: dict) -> dict[str, int]:
    """Validate and import a data-portability payload.

    Wipes *owner_id*'s existing data and re-inserts from the payload.
    Returns a per-table count summary.
    """
    if not isinstance(payload, dict):
        raise ImportValidationError("Payload must be a JSON object.")

    data = payload.get("data", {})
    activities_data = data.get("activities", [])
    if not isinstance(activities_data, list):
        raise ImportValidationError("Payload must contain a 'data.activities' list.")

    for i, act in enumerate(activities_data):
        if not isinstance(act, dict):
            raise ImportValidationError(f"Activity {i} is not an object.")
        if "name" not in act or not isinstance(act["name"], str) or not act["name"].strip():
            raise ImportValidationError(f"Activity {i} has invalid name.")
        entries = act.get("entries", [])
        if not isinstance(entries, list):
            raise ImportValidationError(f"Activity '{act['name']}' entries must be a list.")
        for j, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ImportValidationError(f"Entry {j} in activity '{act['name']}' is not an object.")
            if "occurred_at" not in entry or not isinstance(entry["occurred_at"], str) or not entry["occurred_at"].strip():
                raise ImportValidationError(f"Entry {j} in activity '{act['name']}' missing occurred_at.")

    now = _now_iso_utc()

    with connect() as conn:
        conn.execute("BEGIN")

        # Wipe existing data.
        conn.execute("DELETE FROM entry WHERE owner_id = ?", (owner_id,))
        conn.execute("DELETE FROM activity WHERE owner_id = ?", (owner_id,))

        activities_created = 0
        entries_imported = 0
        entries_skipped = 0

        act_name_to_id: dict[str, int] = {}
        existing = conn.execute(
            "SELECT id, name FROM activity WHERE owner_id = ? AND archived_at IS NULL",
            (owner_id,),
        ).fetchall()
        for act in existing:
            act_name_to_id[act["name"]] = act["id"]

        for act in activities_data:
            act_name = str(act["name"]).strip()
            entries_data = act.get("entries", [])

            if act_name in act_name_to_id:
                act_id = act_name_to_id[act_name]
            else:
                cur = conn.execute(
                    "INSERT INTO activity (owner_id, name, slug, sort_order, created_at, icon)"
                    " VALUES (?, ?, ?, 0, ?, ?)",
                    (owner_id, act_name, act_name.replace(" ", "-").lower(), now, act.get("icon")),
                )
                act_id = cur.lastrowid
                activities_created += 1
                act_name_to_id[act_name] = act_id

            for entry in entries_data:
                occurred_at = str(entry["occurred_at"]).strip()
                memo = entry.get("memo", "") or ""
                num_value = entry.get("num_value")
                if num_value is not None:
                    try:
                        num_value = float(num_value)
                    except (TypeError, ValueError):
                        num_value = None
                tags = entry.get("tags", "") or ""
                time_known = entry.get("time_known", True)

                existing_entry = conn.execute(
                    "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? AND occurred_at = ?",
                    (owner_id, act_id, occurred_at),
                ).fetchone()

                if existing_entry:
                    entries_skipped += 1
                else:
                    conn.execute(
                        "INSERT INTO entry (owner_id, activity_id, occurred_at, memo, num_value, tags, time_known, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (owner_id, act_id, occurred_at, memo, num_value, tags, 1 if time_known else 0, now, now),
                    )
                    entries_imported += 1

        conn.execute("COMMIT")

    return {
        "activities_created": activities_created,
        "entries_imported": entries_imported,
        "entries_skipped": entries_skipped,
    }


def _now_iso_utc() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Simple entry import (flat: activities + entries only)
# ---------------------------------------------------------------------------


class EntryImportError(ValueError):
    """Raised when an entry import payload is invalid."""


def export_entries(owner_id: int) -> dict:
    """Simple export: activities + entries (memo only)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        activities = conn.execute(
            "SELECT name FROM activity WHERE owner_id = ? AND archived_at IS NULL ORDER BY sort_order",
            (owner_id,),
        ).fetchall()

        activity_list: list[dict[str, Any]] = []
        for act in activities:
            entries = conn.execute(
                "SELECT occurred_at, memo FROM entry"
                " WHERE owner_id = ? AND activity_id = (SELECT id FROM activity WHERE owner_id = ? AND name = ?)"
                " ORDER BY occurred_at DESC",
                (owner_id, owner_id, act["name"]),
            ).fetchall()

            activity_list.append({
                "name": act["name"],
                "entries": [
                    {"occurred_at": e["occurred_at"], "memo": e["memo"] or ""}
                    for e in entries
                ],
            })

    return {"activities": activity_list}


def import_entries(owner_id: int, payload: dict[str, Any]) -> dict[str, int]:
    """Import activities and entries, merging with existing data."""
    if not isinstance(payload, dict):
        raise EntryImportError("Payload must be a JSON object.")

    activities_data = payload.get("activities", [])
    if not isinstance(activities_data, list):
        raise EntryImportError("Payload must contain an 'activities' list.")

    for i, act in enumerate(activities_data):
        if not isinstance(act, dict):
            raise EntryImportError(f"Activity {i} is not an object.")
        if "name" not in act or not isinstance(act["name"], str) or not act["name"].strip():
            raise EntryImportError(f"Activity {i} has invalid name.")
        entries = act.get("entries", [])
        if not isinstance(entries, list):
            raise EntryImportError(f"Activity '{act['name']}' entries must be a list.")
        for j, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise EntryImportError(f"Entry {j} in activity '{act['name']}' is not an object.")
            if "occurred_at" not in entry or not isinstance(entry["occurred_at"], str) or not entry["occurred_at"].strip():
                raise EntryImportError(f"Entry {j} in activity '{act['name']}' missing occurred_at.")

    now = _now_iso_utc()

    with connect() as conn:
        conn.execute("BEGIN")

        activities_created = 0
        entries_imported = 0
        entries_skipped = 0

        act_name_to_id: dict[str, int] = {}
        existing = conn.execute(
            "SELECT id, name FROM activity WHERE owner_id = ? AND archived_at IS NULL",
            (owner_id,),
        ).fetchall()
        for act in existing:
            act_name_to_id[act["name"]] = act["id"]

        for act in activities_data:
            act_name = str(act["name"]).strip()
            entries_data = act.get("entries", [])

            if act_name in act_name_to_id:
                act_id = act_name_to_id[act_name]
            else:
                cur = conn.execute(
                    "INSERT INTO activity (owner_id, name, slug, sort_order, created_at)"
                    " VALUES (?, ?, ?, 0, ?)",
                    (owner_id, act_name, act_name.replace(" ", "-").lower(), now),
                )
                act_id = cur.lastrowid
                activities_created += 1
                act_name_to_id[act_name] = act_id

            for entry in entries_data:
                occurred_at = str(entry["occurred_at"]).strip()
                memo = entry.get("memo", "") or ""

                existing_entry = conn.execute(
                    "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? AND occurred_at = ?",
                    (owner_id, act_id, occurred_at),
                ).fetchone()

                if existing_entry:
                    entries_skipped += 1
                else:
                    conn.execute(
                        "INSERT INTO entry (owner_id, activity_id, occurred_at, memo, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (owner_id, act_id, occurred_at, memo, now, now),
                    )
                    entries_imported += 1

        conn.execute("COMMIT")

    return {
        "activities_created": activities_created,
        "entries_imported": entries_imported,
        "entries_skipped": entries_skipped,
    }
