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
``activity`` carries ``cached_count``, ``cached_streak`` and ``last_entry_at``.
On every create/delete we rewrite all three **in the same transaction** as the
entry write (explicit BEGIN/COMMIT; ``db.py`` opens with
``isolation_level=None``). ``recompute()`` rebuilds the identical values from the
actual entries as a drift guard.

Streak rule
-----------
``cached_streak`` is the length of the run of **consecutive calendar days in the
caller-supplied timezone** that ends on the most-recent entry's day. Multiple
entries on the same local day count once. The streak is defined purely from
stored entry timestamps — not from the current wall clock — so the
incrementally-maintained value and ``recompute()`` always agree regardless of
when either runs. (A renderer that wants "is the streak still live today?"
derives that at read time by comparing ``last_entry_at``'s local day to today;
it is never cached, because a time-relative boolean would drift with no new
entry.)

Timezone
--------
Functions that key off a calendar day take a ``tz: ZoneInfo`` argument supplied
explicitly by the caller (the web renderer looks up ``user.timezone``; this
layer never does a DB lookup of its own). The day arithmetic is identical
regardless of zone — only *which* zone defines "the day" changes.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.models import db
from app.services import _db, competition

log = structlog.get_logger()

# Default timezone for cache rebuilds invoked without a user-timezone context
# (e.g. data import). The public mutators take ``tz`` explicitly; this is only
# the bare-call fallback for the internal cache helpers.
_DEFAULT_TZ = ZoneInfo("UTC")

# Field kinds whose values live in entry_value (scalars), and which slot each
# uses. Tag selections (kind 'tag_group') go to entry_tag instead; 'memo' lives
# on the entry row; 'match_list' is its own table, out of scope for this task.
_NUM_KINDS = frozenset({"count", "scale"})
_TEXT_KINDS = frozenset({"level", "result"})
_SCALAR_KINDS = _NUM_KINDS | _TEXT_KINDS
_MEMO_MAX_CHARS = 1000
_MEMO_MAX_LINES = 10


class EntryNotFoundError(LookupError):
    """Raised when an entry doesn't exist for the given owner."""


class SubTallyNotFoundError(LookupError):
    """Raised when a sub-tally doesn't exist for the given owner."""


class PayloadError(ValueError):
    """Raised when a payload references field_defs/tags outside the sub-tally."""


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


def _local_day(occurred_at: str, tz: ZoneInfo) -> date:
    """Return the calendar day of an ISO8601 timestamp in *tz*.

    Naive timestamps (no offset) are interpreted as already being wall-clock time
    in *tz* — entries logged through the app store a tz-aware UTC instant, but a
    backfill or test may pass a naive local string, and treating it as local to
    the caller's zone is the least-surprising rule.
    """
    dt = datetime.fromisoformat(occurred_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).date()


# ---------------------------------------------------------------------------
# Cache maintenance (all run inside the caller's open transaction)
# ---------------------------------------------------------------------------


def _compute_cache(
    conn: sqlite3.Connection,
    activity_id: int,
    owner_id: int,
    tz: ZoneInfo = _DEFAULT_TZ,
) -> dict[str, Any]:
    """Compute count / streak / last_entry_at from the actual entries.

    This is the single source of truth used by both ``recompute()`` and the
    post-write cache refresh, so maintained values and recomputed values are
    computed by the same code and cannot drift. *tz* defines which calendar day a
    timestamp falls in for the streak run.
    """
    rows = _db.fetch_all(
        conn,
        "entry",
        owner_id,
        where="activity_id = ?",
        params=(activity_id,),
        columns="occurred_at",
        order_by="occurred_at DESC",
    )
    count = len(rows)
    if count == 0:
        return {"cached_count": 0, "cached_streak": 0, "last_entry_at": None}

    last_entry_at = rows[0]["occurred_at"]
    # Distinct local days, newest-first.
    distinct_days = sorted({_local_day(r["occurred_at"], tz) for r in rows}, reverse=True)
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


def _refresh_cache(
    conn: sqlite3.Connection,
    activity_id: int,
    owner_id: int,
    tz: ZoneInfo = _DEFAULT_TZ,
) -> dict[str, Any]:
    """Recompute and persist the sub-tally cache. Caller owns the transaction.

    *tz* defines the calendar day for the streak run (defaults to UTC for callers
    that rebuild caches without a user-timezone context, e.g. data import).
    """
    cache = _compute_cache(conn, activity_id, owner_id, tz)
    _db.update(
        conn,
        "activity",
        owner_id,
        assignments="cached_count = ?, cached_streak = ?, last_entry_at = ?",
        assignment_params=(
            cache["cached_count"],
            cache["cached_streak"],
            cache["last_entry_at"],
        ),
        where="id = ?",
        params=(activity_id,),
    )
    return cache


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


def _field_defs_for(conn: sqlite3.Connection, activity_id: int) -> dict[int, str]:
    """Map field_def id -> kind for a sub-tally (field_def has no owner_id column;
    ownership is enforced by joining through the owner-scoped activity)."""
    rows = conn.execute(
        "SELECT id, kind FROM field_def WHERE activity_id = ?",
        (activity_id,),
    ).fetchall()
    return {r["id"]: r["kind"] for r in rows}


def _validate_and_collect(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_id: int,
    payload: dict[str, Any],
) -> tuple[list[tuple[int, str]], list[tuple[int, float | None, str | None]]]:
    """Validate payload against the sub-tally recipe.

    Returns ``(tag_rows, value_rows)`` ready to insert: ``tag_rows`` is a list of
    ``(tag_id,)`` selections and ``value_rows`` is a list of
    ``(field_def_id, num_value, text_value)``.
    """
    field_kinds = _field_defs_for(conn, activity_id)

    # --- scalar values -----------------------------------------------------
    value_rows: list[tuple[int, float | None, str | None]] = []
    for raw_fid, raw_val in (payload.get("values") or {}).items():
        fid = int(raw_fid)
        kind = field_kinds.get(fid)
        if kind is None:
            raise PayloadError(f"field_def {fid} does not belong to activity {activity_id}")
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
                        AND fd.activity_id = ?
                        AND t.id IN ({placeholders})""",  # noqa: S608 - placeholders are '?'
                (owner_id, activity_id, *tag_ids),
            ).fetchall()
        }
        missing = set(tag_ids) - valid
        if missing:
            raise PayloadError(
                f"tags {sorted(missing)} do not belong to activity {activity_id} / owner {owner_id}"
            )

    tag_rows = [(tid,) for tid in tag_ids]
    return tag_rows, value_rows


def archive_tag(conn: sqlite3.Connection, *, owner_id: int, tag_id: int) -> bool:
    """Soft-delete (archive) a tag, scoped to *owner_id*. Returns whether it happened.

    Operates on an *already-open* connection — the caller owns the transaction
    boundary (same convention as ``rename_activity`` in ``categories.py`` and the
    ``_db`` helpers).

    Ownership is verified by walking the chain ``tag → field_def → activity`` and
    requiring ``activity.owner_id = owner_id``. A *tag_id* that doesn't exist, or
    whose owning activity isn't *owner_id*'s, updates zero rows and returns
    ``False`` without modifying anything. On a match, ``tag.archived_at`` is set to
    UTC now (ISO8601) and ``True`` is returned.
    """
    cur = conn.execute(
        """UPDATE tag
              SET archived_at = ?
            WHERE id = ?
              AND archived_at IS NULL
              AND field_def_id IN (
                  SELECT fd.id
                    FROM field_def fd
                    JOIN activity st ON st.id = fd.activity_id
                   WHERE st.owner_id = ?
              )""",
        (_now_iso(), tag_id, owner_id),
    )
    archived = cur.rowcount > 0

    log.info(
        "entries.archive_tag",
        owner_id=owner_id,
        tag_id=tag_id,
        archived=archived,
    )
    return archived


# ---------------------------------------------------------------------------
# Hashtag tag input (text -> resolved tag ids)
# ---------------------------------------------------------------------------

_HASHTAG_RE = re.compile(r"#([\w-]+)", re.UNICODE)


def parse_hashtags(text: str) -> list[str]:
    """Extract hashtag tokens from free text, normalized and de-duplicated.

    Pure function (no DB access). Tokens follow ``#`` and may contain letters,
    digits, underscores and hyphens — no spaces or other punctuation. Each token
    is lowercased and stripped; the first occurrence of each distinct token wins
    and subsequent duplicates are dropped (first-occurrence order preserved).
    Empty, whitespace-only, or ``None`` input yields ``[]``.
    """
    if not text:
        return []

    seen: set[str] = set()
    out: list[str] = []
    for raw in _HASHTAG_RE.findall(text):
        token = raw.lower().strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def find_or_create_tags(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    field_def_id: int,
    names: list[str],
) -> list[int]:
    """Resolve tag *names* to tag ids under *owner_id* / *field_def_id*.

    Operates on an *already-open* connection — the caller owns the transaction
    boundary (same convention as ``archive_tag`` and ``rename_activity``).

    For each name (case-insensitive) the lookup is three-phase, in order:

    1. An **active** tag (``archived_at IS NULL``) with that name -> reuse its id.
    2. Else an **archived** tag with that name -> revive it in place
       (``archived_at = NULL``) so its ``entry_tag`` history is preserved, and
       reuse its id.
    3. Else INSERT a fresh tag (next ``sort_order`` for the field) and use the
       new id.

    Returns a list of tag ids in the same order as *names*. An empty *names*
    list returns ``[]`` with no DB work.
    """
    if not names:
        return []

    ids: list[int] = []
    created_count = 0
    revived_count = 0
    for name in names:
        lowered = name.lower()

        active = conn.execute(
            "SELECT id FROM tag"
            " WHERE owner_id = ? AND field_def_id = ? AND lower(name) = ?"
            " AND archived_at IS NULL",
            (owner_id, field_def_id, lowered),
        ).fetchone()
        if active is not None:
            ids.append(active["id"])
            continue

        archived = conn.execute(
            "SELECT id FROM tag"
            " WHERE owner_id = ? AND field_def_id = ? AND lower(name) = ?"
            " AND archived_at IS NOT NULL"
            " ORDER BY id LIMIT 1",
            (owner_id, field_def_id, lowered),
        ).fetchone()
        if archived is not None:
            conn.execute(
                "UPDATE tag SET archived_at = NULL WHERE id = ?",
                (archived["id"],),
            )
            revived_count += 1
            ids.append(archived["id"])
            continue

        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order)"
            " VALUES (?, ?, ?,"
            " (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tag WHERE field_def_id = ?))",
            (owner_id, field_def_id, name, field_def_id),
        )
        created_count += 1
        ids.append(cur.lastrowid)

    log.info(
        "entries.find_or_create_tags",
        owner_id=owner_id,
        field_def_id=field_def_id,
        names_count=len(names),
        created_count=created_count,
        revived_count=revived_count,
    )
    return ids


def _require_activity(conn: sqlite3.Connection, owner_id: int, activity_id: int) -> None:
    if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
        raise SubTallyNotFoundError(f"activity {activity_id} not found for owner {owner_id}")


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
        "activity_id": entry_row["activity_id"],
        "occurred_at": entry_row["occurred_at"],
        "time_known": entry_row["time_known"],
        "memo": entry_row["memo"],
        "hidden_at": entry_row["hidden_at"],
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
    activity_id: int,
    payload: dict[str, Any] | None = None,
    occurred_at: str | datetime | None = None,
    *,
    tz: ZoneInfo,
    time_known: int = 1,
) -> dict[str, Any]:
    """Create an entry under *activity_id*, owned by *owner_id*.

    *payload* shape::

        {
            "memo": "optional free text",
            "tags": [tag_id, ...],                     # tag-group selections
            "values": {field_def_id: scalar, ...},     # count/scale/level/result
        }

    *occurred_at* defaults to now (UTC ISO8601) and accepts a backfilled past
    timestamp (ISO8601 string or ``datetime``). *tz* is the caller-supplied
    timezone whose calendar day the streak run is computed in. *time_known*
    is 1 when the caller supplied an exact time, 0 when only a date was given
    (the ``T00:00:00`` midnight sentinel). The entry write and the
    ``activity`` cache refresh happen in one transaction.

    Returns the hydrated entry dict.
    """
    payload = payload or {}
    payload = dict(payload)
    payload["memo"] = _normalize_memo(payload.get("memo"))
    occurred = _normalize_occurred_at(occurred_at)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_activity(conn, owner_id, activity_id)
        tag_rows, value_rows = _validate_and_collect(conn, owner_id, activity_id, payload)

        cur = conn.execute(
            "INSERT INTO entry (owner_id, activity_id, occurred_at, memo, time_known)"
            " VALUES (?, ?, ?, ?, ?)",
            (owner_id, activity_id, occurred, payload.get("memo"), time_known),
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

        _refresh_cache(conn, activity_id, owner_id, tz)

        entry_row = _db.fetch_one(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        return _hydrate(conn, owner_id, entry_row)


def get(owner_id: int, entry_id: int) -> dict[str, Any]:
    """Fetch one entry by id, scoped to *owner_id*. Raises if not found."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(
            conn,
            "entry",
            owner_id,
            where="id = ?",
            params=(entry_id,),
        )
        if row is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
        return _hydrate(conn, owner_id, row)


def list_for_activity(
    owner_id: int,
    activity_id: int,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List a sub-tally's entries newest-first, scoped to *owner_id*.

    Uses ``ORDER BY occurred_at DESC`` so the ``idx_entry_activity_time`` index
    serves the scan.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = _db.fetch_all(
            conn,
            "entry",
            owner_id,
            where="activity_id = ?",
            params=(activity_id,),
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
    time_known: int | None = None,
    values: dict[int, Any] | None = None,
    tags: list[int] | None = None,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """Update an entry, scoped to *owner_id*. Bumps ``updated_at``.

    Only the provided pieces change:

    * ``memo`` / ``occurred_at`` — set when passed (pass ``occurred_at`` to
      re-backfill; ``memo`` is always applied as given, including ``None`` to
      clear).
    * ``time_known`` — when provided (0 or 1), updates the time-precision flag
      in the same write as ``occurred_at``.
    * ``values`` / ``tags`` — when provided, fully replace that entry's scalar
      values / tag selections (after the same recipe validation as create). When
      ``None``, they are left untouched.

    If ``occurred_at`` changes, the owning sub-tally's cache is refreshed in the
    same transaction (the entry's local calendar day, in *tz*, may shift, moving
    count/streak).
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(
            conn,
            "entry",
            owner_id,
            where="id = ?",
            params=(entry_id,),
        )
        if row is None:
            raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
        activity_id = row["activity_id"]
        memo = _normalize_memo(memo)

        assignments = ["memo = ?", "updated_at = ?"]
        assignment_params: list[Any] = [memo, _now_iso()]
        occurred_changed = False
        if occurred_at is not None:
            assignments.insert(0, "occurred_at = ?")
            assignment_params.insert(0, _normalize_occurred_at(occurred_at))
            occurred_changed = True
        if time_known is not None:
            assignments.insert(0, "time_known = ?")
            assignment_params.insert(0, time_known)

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
            tag_rows, value_rows = _validate_and_collect(conn, owner_id, activity_id, sub_payload)
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
            _refresh_cache(conn, activity_id, owner_id, tz)

        fresh = _db.fetch_one(
            conn,
            "entry",
            owner_id,
            where="id = ?",
            params=(entry_id,),
        )
        return _hydrate(conn, owner_id, fresh)


def delete(owner_id: int, entry_id: int, *, tz: ZoneInfo) -> bool:
    """Delete an entry, scoped to *owner_id*. Returns True if a row was removed.

    The delete and the sub-tally cache refresh happen in one transaction (the
    streak is recomputed in the caller-supplied timezone *tz*). entry_tag /
    entry_value rows cascade via FK.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(
            conn,
            "entry",
            owner_id,
            where="id = ?",
            params=(entry_id,),
            columns="activity_id",
        )
        if row is None:
            return False
        activity_id = row["activity_id"]

        removed = _db.delete(conn, "entry", owner_id, where="id = ?", params=(entry_id,))
        _refresh_cache(conn, activity_id, owner_id, tz)
        return removed > 0


def recompute(activity_id: int, owner_id: int, *, tz: ZoneInfo) -> dict[str, Any]:
    """Rebuild ``cached_count`` / ``cached_streak`` / ``last_entry_at`` from the
    actual entries (drift guard). Returns the rebuilt values. Scoped to *owner_id*.

    The streak run is computed in the caller-supplied timezone *tz*.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_activity(conn, owner_id, activity_id)
        return _refresh_cache(conn, activity_id, owner_id, tz)


# ---------------------------------------------------------------------------
# Form -> payload transforms (renderer-agnostic; consume a mapping-like ``form``)
# ---------------------------------------------------------------------------
#
# ``form`` here is any mapping with the ``starlette`` ``FormData`` interface
# (``in`` membership and ``.get(key)``) — these helpers never touch ``Request``
# or any HTTP type, so they are pure data transforms the route layer wires up.

EMPTY_MATCH_ROW: dict[str, str] = {"opponent": "", "score": "", "result": ""}


def resolve_occurred_at(
    raw_date: str | None,
    raw_time: str | None = None,
    *,
    tz: ZoneInfo,
) -> tuple[str | None, int]:
    """Turn the log sheet's date + optional time fields into (occurred_at, time_known).

    *raw_date* is the ``type="date"`` value (``YYYY-MM-DD``) in the owner's
    local timezone; *raw_time* is the optional ``type="time"`` value (``HH:MM``).

    When *raw_time* is provided and non-empty:
    - Returns an explicit ``YYYY-MM-DDTHH:MM:00`` timestamp with ``time_known=1``.

    When *raw_time* is absent or empty:
    - If *raw_date* is empty or today's date (in *tz*): returns ``(None, 1)``
      so ``create`` defaults to "now" (time still known).
    - If *raw_date* is a past date (backfill, no time supplied): returns
      ``YYYY-MM-DDT00:00:00`` sentinel with ``time_known=0``.
    """
    raw_time = (raw_time or "").strip()
    if not raw_date:
        raw_date = datetime.now(tz).strftime("%Y-%m-%d")
    if "T" in raw_date:
        # Defensive: a full timestamp slipped through (e.g. an old client).
        return raw_date, 1
    if raw_time:
        return f"{raw_date}T{raw_time}:00", 1
    # No time given: always date-only, time_known=0.
    return f"{raw_date}T00:00:00", 0


def parse_match_rows(form: Any, field_def_id: int) -> list[dict[str, str]]:
    """Read submitted match-list rows for *field_def_id* from form data.

    Rows are indexed 0..n contiguously as ``match_opponent_{field_id}_{i}`` /
    ``match_score_{field_id}_{i}`` / ``match_result_{field_id}_{i}``; reading
    stops at the first missing index.
    """
    rows: list[dict[str, str]] = []
    i = 0
    while True:
        opponent_key = f"match_opponent_{field_def_id}_{i}"
        if opponent_key not in form:
            break
        rows.append(
            {
                "opponent": str(form.get(opponent_key) or ""),
                "score": str(form.get(f"match_score_{field_def_id}_{i}") or ""),
                "result": str(form.get(f"match_result_{field_def_id}_{i}") or ""),
            }
        )
        i += 1
    return rows


def matches_payload_from_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Filter parsed match rows down to ones ready for ``competition.add_matches``.

    A row is persisted only when it has both an opponent and a result —
    incomplete trailing rows (e.g. an empty row left over from the sub-form)
    are silently dropped rather than raising ``MatchPayloadError``.
    """
    payload: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        opponent = row["opponent"].strip()
        result = row["result"].strip()
        if not opponent or result not in {"win", "loss", "draw"}:
            continue
        payload.append(
            {
                "opponent": opponent,
                "score": row["score"].strip(),
                "result": result,
                "sort_order": index,
            }
        )
    return payload


def payload_from_form(form: Any, field_defs: list[sqlite3.Row]) -> tuple[dict[str, Any], set[int]]:
    """Build a ``create`` payload from submitted form fields.

    Returns ``(payload, selected_tag_ids)`` — the selected tags are returned
    separately so the swapped card can echo the just-used selection.
    """
    values: dict[str, Any] = {}
    selected_tags: set[int] = set()
    memo: str | None = None

    for fd in field_defs:
        fid = fd["id"]
        kind = fd["kind"]
        if kind in {"count", "scale"}:
            raw_val = form.get(f"value_{fid}")
            if raw_val not in (None, ""):
                values[fid] = raw_val
        elif kind == "memo":
            raw_memo = form.get(f"value_{fid}")
            if raw_memo:
                memo = _normalize_memo(str(raw_memo))
        # 'level' / 'result' / 'match_list' fields are not part of quick-add v1.

    payload: dict[str, Any] = {"tags": sorted(selected_tags), "values": values}
    if memo is not None:
        payload["memo"] = memo
    return payload, selected_tags


# ---------------------------------------------------------------------------
# Log orchestration (parse form -> persist entry + match rows)
# ---------------------------------------------------------------------------


def create_log_from_form(
    owner_id: int,
    activity_id: int,
    form: Any,
    field_defs: list[sqlite3.Row],
    *,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """Create an entry (and any match-list bouts) from a submitted log form.

    Orchestrates the end-to-end log write that the web ``create_log`` handler
    used to do inline: build the scalar/memo payload, resolve ``#hashtag`` text
    inputs to tag ids, resolve ``occurred_at`` / ``time_known``, create the
    entry, then persist any match-list bouts submitted alongside it. *form* is a
    mapping-like object (``in`` / ``.get``); no HTTP type is touched here. Every
    write is scoped to *owner_id*.

    Returns a dict the renderer consumes::

        {
            "entry": <hydrated entry dict>,
            "selected_tags": {tag_id, ...},   # echo the just-used selection
            "has_match_list": bool,           # drives the Record OOB swap
        }
    """
    payload, selected_tags = payload_from_form(form, field_defs)

    # Resolve #hashtag text inputs to tag IDs.
    all_tag_ids: list[int] = []
    hashtag_fids = [fd["id"] for fd in field_defs if fd["kind"] == "tag_group"]
    if hashtag_fids:
        with db.connect() as conn:
            conn.execute("BEGIN")
            for fid in hashtag_fids:
                raw = str(form.get(f"hashtags_{fid}", "")).strip()
                if raw:
                    payload["memo"] = raw  # combined text → also the memo
                names = parse_hashtags(raw)
                if names:
                    ids = find_or_create_tags(
                        conn, owner_id=owner_id, field_def_id=fid, names=names
                    )
                    all_tag_ids.extend(ids)
    payload["tags"] = all_tag_ids

    occurred_at, time_known = resolve_occurred_at(
        str(form.get("date") or "").strip(),
        str(form.get("time") or "").strip(),
        tz=tz,
    )

    created = create(
        owner_id, activity_id, payload, occurred_at=occurred_at, tz=tz, time_known=time_known
    )

    # Persist any match-list bouts submitted alongside the entry.
    has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
    for fd in field_defs:
        if fd["kind"] != "match_list":
            continue
        rows = matches_payload_from_rows(parse_match_rows(form, fd["id"]))
        if rows:
            competition.add_matches(owner_id, created["id"], rows)

    return {
        "entry": created,
        "selected_tags": selected_tags,
        "has_match_list": has_match_list,
    }
