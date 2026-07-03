"""Shared helpers for search services."""

from __future__ import annotations

MAX_LIMIT = 50
LIKE_ESCAPE = "\\"


def escape_like(text: str) -> str:
    """Escape SQLite LIKE wildcards and the escape char itself."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)
