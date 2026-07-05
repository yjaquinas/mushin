"""Competition (match-list) service — DROPPED.

The ``match`` table has been removed from the schema (migration 0018).
This module is kept as a thin stub so import paths don't break.
All match-list functionality is removed.
"""

from __future__ import annotations

from typing import Any


class EntryNotFoundError(LookupError):
    """Raised when the parent entry doesn't exist for the given owner."""


class MatchPayloadError(ValueError):
    """Raised when a match row is malformed."""


def add_matches(owner_id: int, entry_id: int, rows: Any) -> list[dict[str, Any]]:
    """No-op: match table removed."""
    return []


def delete_matches(owner_id: int, entry_id: int) -> int:
    """No-op: match table removed."""
    return 0


def record(owner_id: int, activity_id: int) -> dict[str, Any]:
    """Empty record: match table removed."""
    return {"wins": 0, "losses": 0, "draws": 0, "total": 0, "decided": 0, "win_rate": None}


def results_timeline(owner_id: int, activity_id: int) -> list[dict[str, Any]]:
    """Empty timeline: match table removed."""
    return []


def head_to_head(owner_id: int, activity_id: int) -> list[dict[str, Any]]:
    """Empty H2H: match table removed."""
    return []
