"""Entry create / read / update / delete for the Mushin service layer.

Renderer-agnostic: no HTTP, no Jinja, no HXML. Functions take ``owner_id`` as a
required argument and return plain Python data structures (dicts) that either
renderer can consume.

An *entry* belongs to a sub-tally and is recipe-driven: its values are written
to ``entry_value`` (scalar count/scale/level/result fields) and ``entry_tag``
(tag-group selections), plus a free-text ``memo`` on the entry row itself. The
recipe is the set of ``field_def`` rows on the sub-tally; we validate every
referenced field_def / tag actually belongs to that sub-tally and owner before
writing, so a payload can't reach across sub-tallies or tenants.

Cache discipline
----------------
``sub_tally`` carries ``cached_count``, ``cached_streak`` and ``last_entry_at``.
On every create/delete we rewrite all three **in the same transaction** as the
entry write (explicit BEGIN/COMMIT; ``db.py`` opens with
``isolation_level=None``). ``recompute()`` rebuilds the identical values from the
actual entries as a drift guard.

Streak rule
-----------
``cached_streak`` is the length of the run of **consecutive KST (Asia/Seoul)
calendar days** that ends on the most-recent entry's day. Multiple entries on
the same KST day count once. The streak is defined purely from stored entry
timestamps — not from the current wall clock — so the incrementally-maintained
value and ``recompute()`` always agree regardless of when either runs. (A
renderer that wants "is the streak still live today?" derives that at read time
by comparing ``last_entry_at``'s KST day to today; it is never cached, because a
time-relative boolean would drift with no new entry.)
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.services import _db

KST = ZoneInfo("Asia/Seoul")

# Field kinds whose values live in entry_value (scalars), and which slot each
# uses. Tag selections (kind 'tag_group') go to entry_tag instead; 'memo' lives
# on the entry row; 'match_list' is its own table, out of scope for this task.
_NUM_KINDS = frozenset({"count", "scale"})
_TEXT_KINDS = frozenset({"level", "result"})
_SCALAR_KINDS = _NUM_KINDS | _TEXT_KINDS


class EntryNotFoundError(LookupError):
    """Raised when an entry doesn't exist for the given owner."""


class SubTallyNotFoundError(LookupError):
    """Raised when a sub-tally doesn't exist for the given owner."""


class PayloadError(ValueError):
    """Raised when a payload references field_defs/tags outside the sub-tally."""


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current instant as a UTC ISO8601 string (timezone-aware)."""
    return datetime.now(UTC).isoformat()


def _normalize_occurred_at(occurred_at: str | datetime | None) -> str:
    """Normalize *occurred_at* to an ISO8601 string.

    ``None`` -> now. A ``datetime`` is rendered with ``.isoformat()``. A string is
    accepted as-is (caller's responsibility to pass ISO8601); this is what lets a
    backfilled past timestamp flow straight through.
    """
    if occurred_at is None:
        return _now_iso()
    if isinstance(occurred_at, datetime):
        return occurred_at.isoformat()
    return occurred_at


def _kst_day(occurred_at: str) -> date:
    """Return the Asia/Seoul calendar day for an ISO8601 timestamp.

    Naive timestamps (no offset) are interpreted as already being KST wall-clock
    time — entries logged through the app store a tz-aware UTC instant, but a
    backfill or test may pass a naive local string, and treating it as KST is the
    least-surprising rule for a Korean-market app.
    """
    dt = datetime.fromisoformat(occurred_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST).date()


# ---------------------------------------------------------------------------
# Cache maintenance (all run inside the caller's open transaction)
# ---------------------------------------------------------------------------


def _compute_cache(conn: sqlite3.Connection, sub_tally_id: int, owner_id: int) -> dict[str, Any]:
    """Compute count / streak / last_entry_at from the actual entries.

    This is the single source of truth used by both ``recompute()`` and the
    post-write cache refresh, so maintained values and recomputed values are
    computed by the same code and cannot drift.
    """
    rows = _db.fetch_all(
        conn,
        "entry",
        owner_id,
        where="sub_tally_id = ?",
        params=(sub_tally_id,),
        columns="occurred_at",
        order_by="occurred_at DESC",
    )
    count = len(rows)
    if count == 0:
        return {"cached_count": 0, "cached_streak": 0, "last_entry_at": None}

    last_entry_at = rows[0]["occurred_at"]
    # Distinct KST days, newest-first.
    distinct_days = sorted({_kst_day(r["occurred_at"]) for r in rows}, reverse=True)
    streak = 1
    for earlier, later in zip(distinct_days[1:], distinct_days, strict=False):
        if (later - earlier).days == 1:
            streak += 1
        else:
            break

    return {
        "cached_count": count,
        "cached_streak": streak,
        "last_entry_at": last_entry_at,
    }


def _refresh_cache(conn: sqlite3.Connection, sub_tally_id: int, owner_id: int) -> dict[str, Any]:
    """Recompute and persist the sub-tally cache. Caller owns the transaction."""
    cache = _compute_cache(conn, sub_tally_id, owner_id)
    _db.update(
        conn,
        "sub_tally",
        owner_id,
        assignments="cached_count = ?, cached_streak = ?, last_entry_at = ?",
        assignment_params=(
            cache["cached_count"],
            cache["cached_streak"],
            cache["last_entry_at"],
        ),
        where="id = ?",
        params=(sub_tally_id,),
    )
    return cache


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


def _field_defs_for(conn: sqlite3.Connection, sub_tally_id: int) -> dict[int, str]:
    """Map field_def id -> kind for a sub-tally (field_def has no owner_id column;
    ownership is enforced by joining through the owner-scoped sub_tally)."""
    rows = conn.execute(
        "SELECT id, kind FROM field_def WHERE sub_tally_id = ?",
        (sub_tally_id,),
    ).fetchall()
    return {r["id"]: r["kind"] for r in rows}


def _validate_and_collect(
    conn: sqlite3.Connection,
    owner_id: int,
    sub_tally_id: int,
    payload: dict[str, Any],
) -> tuple[list[tuple[int, str]], list[tuple[int, float | None, str | None]]]:
    """Validate payload against the sub-tally recipe.

    Returns ``(tag_rows, value_rows)`` ready to insert: ``tag_rows`` is a list of
    ``(tag_id,)`` selections and ``value_rows`` is a list of
    ``(field_def_id, num_value, text_value)``.
    """
    field_kinds = _field_defs_for(conn, sub_tally_id)

    # --- scalar values -----------------------------------------------------
    value_rows: list[tuple[int, float | None, str | None]] = []
    for raw_fid, raw_val in (payload.get("values") or {}).items():
        fid = int(raw_fid)
        kind = field_kinds.get(fid)
        if kind is None:
            raise PayloadError(f"field_def {fid} does not belong to sub_tally {sub_tally_id}")
        if kind not in _SCALAR_KINDS:
            raise PayloadError(
                f"field_def {fid} has kind {kind!r}, which is not a scalar value field"
            )
        if raw_val is None:
            continue
        if kind in _NUM_KINDS:
            value_rows.append((fid, float(raw_val), None))
        else:  # level / result -> text
            value_rows.append((fid, None, str(raw_val)))

    # --- tag selections ----------------------------------------------------
    tag_ids = [int(t) for t in (payload.get("tags") or [])]
    if tag_ids:
        placeholders = ",".join("?" for _ in tag_ids)
        # Tags are owner-scoped AND must hang off a field_def on this sub-tally.
        valid = {
            r["id"]
            for r in conn.execute(
                f"""SELECT t.id FROM tag t
                       JOIN field_def fd ON fd.id = t.field_def_id
                      WHERE t.owner_id = ?
                        AND fd.sub_tally_id = ?
                        AND t.id IN ({placeholders})""",  # noqa: S608 - placeholders are '?'
                (owner_id, sub_tally_id, *tag_ids),
            ).fetchall()
        }
        missing = set(tag_ids) - valid
        if missing:
            raise PayloadError(
                f"tags {sorted(missing)} do not belong to sub_tally {sub_tally_id} / owner {owner_id}"
            )

    tag_rows = [(tid,) for tid in tag_ids]
    return tag_rows, value_rows


def _require_sub_tally(conn: sqlite3.Connection, owner_id: int, sub_tally_id: int) -> None:
    if not _db.exists(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,)):
        raise SubTallyNotFoundError(f"sub_tally {sub_tally_id} not found for owner {owner_id}")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _hydrate(conn: sqlite3.Connection, owner_id: int, entry_row: sqlite3.Row) -> dict[str, Any]:
    """Turn an entry row + its values/tags into a plain dict."""
    entry_id = entry_row["id"]
    values = [
        {
            "field_def_id": r["field_def_id"],
            "num_value": r["num_value"],
            "text_value": r["text_value"],
        }
        for r in conn.execute(
            "SELECT field_def_id, num_value, text_value FROM entry_value WHERE entry_id = ?",
            (entry_id,),
        ).fetchall()
    ]
    tags = [
        r["tag_id"]
        for r in conn.execute(
            "SELECT tag_id FROM entry_tag WHERE entry_id = ?",
            (entry_id,),
        ).fetchall()
    ]
    return {
        "id": entry_id,
        "owner_id": entry_row["owner_id"],
        "sub_tally_id": entry_row["sub_tally_id"],
        "occurred_at": entry_row["occurred_at"],
        "memo": entry_row["memo"],
        "created_at": entry_row["created_at"],
        "updated_at": entry_row["updated_at"],
        "values": values,
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create(
    owner_id: int,
    sub_tally_id: int,
    payload: dict[str, Any] | None = None,
    occurred_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Create an entry under *sub_tally_id*, owned by *owner_id*.

    *payload* shape::

        {
            "memo": "optional free text",
            "tags": [tag_id, ...],                     # tag-group selections
            "values": {field_def_id: scalar, ...},     # count/scale/level/result
        }

    *occurred_at* defaults to now (UTC ISO8601) and accepts a backfilled past
    timestamp (ISO8601 string or ``datetime``). The entry write and the
    ``sub_tally`` cache refresh happen in one transaction.

    Returns the hydrated entry dict.
    """
    payload = payload or {}
    occurred = _normalize_occurred_at(occurred_at)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_sub_tally(conn, owner_id, sub_tally_id)
        tag_rows, value_rows = _validate_and_collect(conn, owner_id, sub_tally_id, payload)

        cur = conn.execute(
            "INSERT INTO entry (owner_id, sub_tally_id, occurred_at, memo) VALUES (?, ?, ?, ?)",
            (owner_id, sub_tally_id, occurred, payload.get("memo")),
        )
        entry_id = cur.lastrowid

        for (tag_id,) in tag_rows:
            conn.execute(
                "INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)",
                (entry_id, tag_id),
            )
        for fid, num_value, text_value in value_rows:
            conn.execute(
                "INSERT INTO entry_value (entry_id, field_def_id, num_value, text_value)"
                " VALUES (?, ?, ?, ?)",
                (entry_id, fid, num_value, text_value),
            )

        _refresh_cache(conn, sub_tally_id, owner_id)

        entry_row = _db.fetch_one(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        return _hydrate(conn, owner_id, entry_row)


def get(owner_id: int, entry_id: int) -> dict[str, Any]:
    """Fetch one entry by id, scoped to *owner_id*. Raises if not found."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        if row is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
        return _hydrate(conn, owner_id, row)


def list_for_sub_tally(
    owner_id: int,
    sub_tally_id: int,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List a sub-tally's entries newest-first, scoped to *owner_id*.

    Uses ``ORDER BY occurred_at DESC`` so the ``idx_entry_subtally_time`` index
    serves the scan.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = _db.fetch_all(
            conn,
            "entry",
            owner_id,
            where="sub_tally_id = ?",
            params=(sub_tally_id,),
            order_by="occurred_at DESC, id DESC",
            limit=limit,
        )
        return [_hydrate(conn, owner_id, r) for r in rows]


def update(
    owner_id: int,
    entry_id: int,
    *,
    memo: str | None = None,
    occurred_at: str | datetime | None = None,
    values: dict[int, Any] | None = None,
    tags: list[int] | None = None,
) -> dict[str, Any]:
    """Update an entry, scoped to *owner_id*. Bumps ``updated_at``.

    Only the provided pieces change:

    * ``memo`` / ``occurred_at`` — set when passed (pass ``occurred_at`` to
      re-backfill; ``memo`` is always applied as given, including ``None`` to
      clear).
    * ``values`` / ``tags`` — when provided, fully replace that entry's scalar
      values / tag selections (after the same recipe validation as create). When
      ``None``, they are left untouched.

    If ``occurred_at`` changes, the owning sub-tally's cache is refreshed in the
    same transaction (the entry's KST day may shift, moving count/streak).
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        if row is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
        sub_tally_id = row["sub_tally_id"]

        assignments = ["memo = ?", "updated_at = ?"]
        assignment_params: list[Any] = [memo, _now_iso()]
        occurred_changed = False
        if occurred_at is not None:
            assignments.insert(0, "occurred_at = ?")
            assignment_params.insert(0, _normalize_occurred_at(occurred_at))
            occurred_changed = True

        _db.update(
            conn,
            "entry",
            owner_id,
            assignments=", ".join(assignments),
            assignment_params=assignment_params,
            where="id = ?",
            params=(entry_id,),
        )

        if values is not None or tags is not None:
            sub_payload = {"values": values or {}, "tags": tags or []}
            tag_rows, value_rows = _validate_and_collect(conn, owner_id, sub_tally_id, sub_payload)
            if values is not None:
                conn.execute("DELETE FROM entry_value WHERE entry_id = ?", (entry_id,))
                for fid, num_value, text_value in value_rows:
                    conn.execute(
                        "INSERT INTO entry_value"
                        " (entry_id, field_def_id, num_value, text_value)"
                        " VALUES (?, ?, ?, ?)",
                        (entry_id, fid, num_value, text_value),
                    )
            if tags is not None:
                conn.execute("DELETE FROM entry_tag WHERE entry_id = ?", (entry_id,))
                for (tag_id,) in tag_rows:
                    conn.execute(
                        "INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)",
                        (entry_id, tag_id),
                    )

        if occurred_changed:
            _refresh_cache(conn, sub_tally_id, owner_id)

        fresh = _db.fetch_one(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        return _hydrate(conn, owner_id, fresh)


def delete(owner_id: int, entry_id: int) -> bool:
    """Delete an entry, scoped to *owner_id*. Returns True if a row was removed.

    The delete and the sub-tally cache refresh happen in one transaction.
    entry_tag / entry_value rows cascade via FK.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(
            conn, "entry", owner_id, where="id = ?", params=(entry_id,), columns="sub_tally_id"
        )
        if row is None:
            return False
        sub_tally_id = row["sub_tally_id"]

        removed = _db.delete(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        _refresh_cache(conn, sub_tally_id, owner_id)
        return removed > 0


def recompute(sub_tally_id: int, owner_id: int) -> dict[str, Any]:
    """Rebuild ``cached_count`` / ``cached_streak`` / ``last_entry_at`` from the
    actual entries (drift guard). Returns the rebuilt values. Scoped to *owner_id*.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_sub_tally(conn, owner_id, sub_tally_id)
        return _refresh_cache(conn, sub_tally_id, owner_id)
