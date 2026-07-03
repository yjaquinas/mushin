"""Entry create / read / update / delete for the Mushin service layer.

Renderer-agnostic: no HTTP, no Jinja, no HXML. Functions take ``owner_id`` as a
required argument and return plain Python data structures (dicts) that either
renderer can consume.

An *entry* belongs to an activity and carries flat columns:
``occurred_at``, ``memo``, ``num_value``, ``tags`` (comma-separated),
``time_known``, ``created_at``, ``updated_at``.

Cache discipline
----------------
``activity`` carries ``count``, ``streak`` and ``last_entry_at``. On every
create/delete we rewrite all three **in the same transaction** as the entry
write (explicit BEGIN/COMMIT; ``db.py`` opens with ``isolation_level=None``).
``recompute()`` rebuilds the identical values from the actual entries as a
drift guard.

Streak rule
-----------
Streak is the length of the run of **consecutive calendar days in the
caller-supplied timezone** that ends on the most-recent entry's day. Multiple
entries on the same local day count once. The streak is defined purely from
stored entry timestamps — not from the current wall clock — so the
incrementally-maintained value and ``recompute()`` always agree regardless of
when either runs.

Timezone
--------
Functions that key off a calendar day take a ``tz: ZoneInfo`` argument supplied
explicitly by the caller. The day arithmetic is identical regardless of zone —
only *which* zone defines "the day" changes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.models import db

log = structlog.get_logger()

_DEFAULT_TZ = ZoneInfo("UTC")

_MEMO_MAX_CHARS = 1000
_MEMO_MAX_LINES = 10
_TAGS_MAX = 20
_TAG_MAX_LEN = 50


class EntryNotFoundError(LookupError):
    """Raised when an entry doesn't exist for the given owner."""


class ActivityNotFoundError(LookupError):
    """Raised when an activity doesn't exist for the given owner."""


class PayloadError(ValueError):
    """Raised when a payload is invalid."""


def _normalize_memo(memo: str | None) -> str | None:
    """Validate and normalize free-text entry notes."""
    if memo is None:
        return None
    normalized = str(memo).strip()
    if not normalized:
        return None
    if len(normalized) > _MEMO_MAX_CHARS:
        raise PayloadError("memo exceeds max characters")
    if len(normalized.splitlines()) > _MEMO_MAX_LINES:
        raise PayloadError("memo exceeds max lines")
    return normalized


def _normalize_tags(tags: list[int] | None) -> str | None:
    """Normalize a list of tag ids into a comma-separated string.

    Returns ``None`` when there are no tags, or a comma-separated string of
    sorted tag ids.
    """
    if not tags:
        return None
    return ",".join(str(t) for t in sorted(tags))


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current instant as a UTC ISO8601 string (timezone-aware)."""
    return datetime.now(UTC).isoformat()


def _normalize_occurred_at(occurred_at: str | datetime | None) -> str:
    """Normalize *occurred_at* to an ISO8601 string."""
    if occurred_at is None:
        return _now_iso()
    if isinstance(occurred_at, datetime):
        return occurred_at.isoformat()
    return occurred_at


def _local_day(occurred_at: str, tz: ZoneInfo) -> date:
    """Return the calendar day of an ISO8601 timestamp in *tz*."""
    if not occurred_at:
        return date.today(tz)
    try:
        dt = datetime.fromisoformat(occurred_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz).date()
    except (ValueError, TypeError):
        return date.today(tz)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _refresh_cache(conn: sqlite3.Connection, activity_id: int, owner_id: int, tz: ZoneInfo) -> None:
    """Rebuild count, streak, and last_entry_at from actual entries."""
    row = conn.execute(
        "SELECT occurred_at FROM entry"
        " WHERE owner_id = ? AND activity_id = ?"
        " ORDER BY occurred_at DESC",
        (owner_id, activity_id),
    ).fetchall()

    count = len(row)
    last_entry_at = row[0]["occurred_at"] if row else None

    # Compute streak from distinct local days.
    days: list[date] = []
    for r in row:
        d = _local_day(r["occurred_at"], tz)
        if not days or d != days[-1]:
            days.append(d)
    days.sort(reverse=True)

    streak = 0
    if days:
        streak = 1
        for i in range(1, len(days)):
            expected = (days[i - 1] - __import__("datetime").timedelta(days=1))
            if days[i] == expected:
                streak += 1
            else:
                break

    conn.execute(
        "UPDATE activity SET count = ?, streak = ?, last_entry_at = ?"
        " WHERE id = ? AND owner_id = ?",
        (count, streak, last_entry_at, activity_id, owner_id),
    )


def recompute(owner_id: int, activity_id: int, tz: ZoneInfo | None = None) -> dict:
    """Rebuild cache from actual entries; returns the new values."""
    if tz is None:
        tz = _DEFAULT_TZ
    with db.connect() as conn:
        conn.execute("BEGIN")
        _refresh_cache(conn, activity_id, owner_id, tz)
        row = conn.execute(
            "SELECT count, streak, last_entry_at FROM activity"
            " WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
    return {"count": row["count"], "streak": row["streak"], "last_entry_at": row["last_entry_at"]}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create(
    owner_id: int,
    activity_id: int,
    payload: dict[str, Any],
    *,
    occurred_at: str | None = None,
    tz: ZoneInfo | None = None,
    time_known: bool = True,
) -> dict[str, Any]:
    """Create an entry for *activity_id*, owned by *owner_id*.

    *payload* is ``{"tags": [...], "values": {...}}`` — the legacy field-system
    payload shape. For the new flat schema we accept:
    ``{"tags": [...], "num_value": <float>, "memo": <str>}``.

    Returns the created entry as a dict.
    """
    if tz is None:
        tz = _DEFAULT_TZ

    occurred_at = _normalize_occurred_at(occurred_at)
    memo = payload.get("memo")
    memo = _normalize_memo(memo) if memo else None

    tags = payload.get("tags")
    tags_str = _normalize_tags(tags) if tags else None

    # Extract num_value from legacy payload shape.
    num_value = payload.get("num_value")
    if num_value is not None:
        try:
            num_value = float(num_value)
        except (TypeError, ValueError):
            num_value = None

    with db.connect() as conn:
        conn.execute("BEGIN")

        # Verify activity exists and is owned.
        act = conn.execute(
            "SELECT id FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
        if act is None:
            raise ActivityNotFoundError(f"activity {activity_id} not found for owner {owner_id}")

        now = _now_iso()
        cur = conn.execute(
            """INSERT INTO entry
               (owner_id, activity_id, occurred_at, memo, num_value, tags, time_known, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (owner_id, activity_id, occurred_at, memo, num_value, tags_str, 1 if time_known else 0, now, now),
        )
        entry_id = cur.lastrowid

        _refresh_cache(conn, activity_id, owner_id, tz)

        entry = conn.execute(
            "SELECT * FROM entry WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return dict(entry)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get(owner_id: int, entry_id: int) -> dict[str, Any]:
    """Fetch an entry by id, scoped to *owner_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM entry WHERE id = ? AND owner_id = ? AND hidden_at IS NULL",
            (entry_id, owner_id),
        ).fetchone()
    if row is None:
        raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
    return dict(row)


def list_for_activity(owner_id: int, activity_id: int) -> list[dict[str, Any]]:
    """List all non-hidden entries for an activity, scoped to *owner_id*, newest first."""
    return list_entries(owner_id, activity_id, tz=ZoneInfo("UTC"))


def list_entries(
    owner_id: int,
    activity_id: int,
    *,
    tz: ZoneInfo,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List entries for an activity, scoped to *owner_id*, newest first."""
    where_parts = ["owner_id = ?", "activity_id = ?", "hidden_at IS NULL"]
    params: list[Any] = [owner_id, activity_id]

    if start is not None:
        where_parts.append("occurred_at >= ?")
        params.append(start.isoformat())
    if end is not None:
        where_parts.append("occurred_at < ?")
        # end is exclusive; add one day.
        end_exclusive = end + __import__("datetime").timedelta(days=1)
        params.append(end_exclusive.isoformat())

    where_clause = " AND ".join(where_parts)
    sql = f"SELECT * FROM entry WHERE {where_clause} ORDER BY occurred_at DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_entries_by_day(
    owner_id: int,
    activity_id: int,
    target_day: date,
    *,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """List entries for a specific local day."""
    start = target_day
    end = target_day + __import__("datetime").timedelta(days=1)
    return list_entries(owner_id, activity_id, tz=tz, start=start, end=end)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update(
    owner_id: int,
    entry_id: int,
    *,
    memo: str | None = None,
    occurred_at: str | None = None,
    time_known: bool | None = None,
    num_value: float | None = None,
    tags: list[int] | None = None,
    tz: ZoneInfo | None = None,
) -> dict[str, Any]:
    """Update an entry's fields. Returns the updated entry."""
    if tz is None:
        tz = _DEFAULT_TZ

    with db.connect() as conn:
        conn.execute("BEGIN")

        existing = conn.execute(
            "SELECT * FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        ).fetchone()
        if existing is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")

        updates: list[str] = []
        params: list[Any] = []

        if memo is not None:
            updates.append("memo = ?")
            params.append(_normalize_memo(memo))
        if occurred_at is not None:
            updates.append("occurred_at = ?")
            params.append(_normalize_occurred_at(occurred_at))
        if time_known is not None:
            updates.append("time_known = ?")
            params.append(1 if time_known else 0)
        if num_value is not None:
            updates.append("num_value = ?")
            params.append(float(num_value))
        if tags is not None:
            updates.append("tags = ?")
            params.append(_normalize_tags(tags))

        if updates:
            updates.append("updated_at = ?")
            params.append(_now_iso())
            params.append(entry_id)
            conn.execute(
                f"UPDATE entry SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        _refresh_cache(conn, existing["activity_id"], owner_id, tz)

        updated = conn.execute(
            "SELECT * FROM entry WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return dict(updated)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete(owner_id: int, entry_id: int, *, tz: ZoneInfo | None = None) -> None:
    """Delete an entry by id, scoped to *owner_id*."""
    if tz is None:
        tz = _DEFAULT_TZ

    with db.connect() as conn:
        conn.execute("BEGIN")

        existing = conn.execute(
            "SELECT activity_id FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        ).fetchone()
        if existing is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")

        conn.execute(
            "DELETE FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        )
        _refresh_cache(conn, existing["activity_id"], owner_id, tz)


# ---------------------------------------------------------------------------
# Tag helpers (for hashtag-based tag creation)
# ---------------------------------------------------------------------------


def parse_hashtags(text: str) -> list[str]:
    """Parse ``#tag`` text into a list of tag names."""
    if not text:
        return []
    import re
    return [name.strip().lower() for name in re.findall(r"#(\w+)", text) if name.strip()]


def find_or_create_tags(
    conn: sqlite3.Connection,
    owner_id: int,
    field_def_id: int,
    names: list[str],
) -> list[int]:
    """Find or create tags by name, scoped to *owner_id* and *field_def_id*.

    Note: with the new flat schema, tags are stored as comma-separated ids on
    the entry row itself, so this function is kept for backward compatibility
    but no longer used by the main entry flow.
    """
    result: list[int] = []
    for name in names:
        name = name.lower().strip()
        if not name:
            continue
        # Check for existing active tag.
        row = conn.execute(
            "SELECT id FROM tag WHERE owner_id = ? AND field_def_id = ? AND lower(name) = ? AND archived_at IS NULL",
            (owner_id, field_def_id, name),
        ).fetchone()
        if row is not None:
            result.append(row["id"])
            continue
        # Check if there's an archived tag with this name we can reuse.
        archived = conn.execute(
            "SELECT id FROM tag WHERE owner_id = ? AND field_def_id = ? AND lower(name) = ? AND archived_at IS NOT NULL",
            (owner_id, field_def_id, name),
        ).fetchone()
        if archived is not None:
            conn.execute(
                "UPDATE tag SET archived_at = NULL WHERE id = ?",
                (archived["id"],),
            )
            result.append(archived["id"])
            continue
        # Create new tag.
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name) VALUES (?, ?, ?)",
            (owner_id, field_def_id, name),
        )
        result.append(cur.lastrowid)
    return result


def resolve_occurred_at(
    date_str: str,
    time_str: str,
    *,
    tz: ZoneInfo,
    occurred_at_utc: str | None = None,
) -> tuple[str, bool]:
    """Resolve a date/time form submission to (iso_string, time_known).

    Returns ``(occurred_at_iso, time_known)`` where ``time_known`` is ``True``
    when the user supplied an explicit time, ``False`` when only a date was given.
    """
    time_known = bool(time_str)

    if occurred_at_utc:
        try:
            dt = datetime.fromisoformat(occurred_at_utc.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).isoformat(), time_known
        except (ValueError, TypeError):
            pass

    if not date_str:
        return _now_iso(), True

    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return _now_iso(), True

    if time_str:
        try:
            h, m = time_str.split(":")
            dt = datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=tz)
            return dt.astimezone(UTC).isoformat(), True
        except (ValueError, IndexError):
            pass

    # Date-only: midnight in the user's timezone.
    dt = datetime(d.year, d.month, d.day, tzinfo=tz)
    return dt.astimezone(UTC).isoformat(), False
