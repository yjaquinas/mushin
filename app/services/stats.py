"""Renderer-agnostic stats for the Mushin service layer.

No HTTP, no Jinja, no HXML. Every function takes ``owner_id`` as a required
argument (multi-user isolation is non-negotiable) and returns plain Python data
structures (dicts / lists of dicts) that either renderer can consume.

KST is the calendar
-------------------
Mushin is a Korean-market app: every "day", "week", "month", and "year" bucket
is an **Asia/Seoul (KST) calendar** bucket. We reuse ``entries._kst_day`` so the
day a timestamp falls in agrees exactly with the streak math in ``entries.py``
(same-day entries collapse, midnight boundaries land on the same side). The
"current period" boundaries are derived from the **current KST wall-clock day**,
never cached, because a period boundary moves with time and no new entry.

Scoping + batching
------------------
Counting / streak / heatmap functions read ``entry`` rows scoped to the owner.
Field-level functions (tag-group, scale, count) read ``entry_value`` / ``tag`` /
``entry_tag`` joined back through the owner-scoped ``entry`` table so a value
can never reach across tenants. ``counts_for_sub_tallies`` accepts a *list* of
sub_tally ids and answers in **one** query (``WHERE sub_tally_id IN (...)``) to
avoid N+1 fan-out when a category renders many sub-tallies at once.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from app.models import db
from app.services import _db
from app.services.entries import KST, _kst_day

# Trailing-window length for the contribution heatmap (inclusive of today).
HEATMAP_DAYS = 365


# ---------------------------------------------------------------------------
# KST period boundaries (derived from the current wall clock, never cached)
# ---------------------------------------------------------------------------


def _today_kst() -> date:
    """The current Asia/Seoul calendar day."""
    return datetime.now(KST).date()


def _week_start(day: date) -> date:
    """Monday-anchored start of *day*'s ISO week (KST)."""
    return day - timedelta(days=day.weekday())


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _year_start(day: date) -> date:
    return day.replace(month=1, day=1)


def _add_month(day: date) -> date:
    """First day of the month after *day*'s month (for an exclusive upper bound)."""
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1, day=1)
    return day.replace(month=day.month + 1, day=1)


# ---------------------------------------------------------------------------
# Reading entry days (owner-scoped)
# ---------------------------------------------------------------------------


def _entry_days(conn: sqlite3.Connection, sub_tally_id: int, owner_id: int) -> list[date]:
    """Every entry's KST day for a sub-tally, newest day first, with repeats.

    Repeats are preserved so callers that count occurrences (heatmap, period
    counts) see them; callers that want distinct days dedupe themselves.
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
    return [_kst_day(r["occurred_at"]) for r in rows]


# ---------------------------------------------------------------------------
# Counts: week / month / year / lifetime + average per week
# ---------------------------------------------------------------------------


def _count_buckets(days: Sequence[date], today: date) -> dict[str, Any]:
    """Build the count summary for a single sub-tally from its entry days."""
    week0 = _week_start(today)
    month0 = _month_start(today)
    year0 = _year_start(today)

    this_week = this_month = this_year = 0
    for d in days:
        if d >= week0 and d <= today:
            this_week += 1
        if d >= month0 and d <= today:
            this_month += 1
        if d >= year0 and d <= today:
            this_year += 1

    lifetime = len(days)

    # Average per week over the span from the first entry to today (inclusive),
    # measured in whole KST weeks (min 1 so a single day isn't divided to zero).
    if lifetime:
        first_day = min(days)
        span_days = (today - first_day).days + 1
        weeks = max(1, span_days / 7.0)
        avg_per_week = lifetime / weeks
    else:
        avg_per_week = 0.0

    return {
        "this_week": this_week,
        "this_month": this_month,
        "this_year": this_year,
        "lifetime": lifetime,
        "avg_per_week": round(avg_per_week, 2),
    }


def counts(sub_tally_id: int, owner_id: int) -> dict[str, Any]:
    """Count summary for one sub-tally: this week/month/year, lifetime, avg/week.

    All windows are KST calendar windows anchored on the current KST day.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, sub_tally_id, owner_id)
    return _count_buckets(days, _today_kst())


def counts_for_sub_tallies(
    sub_tally_ids: Iterable[int], owner_id: int
) -> dict[int, dict[str, Any]]:
    """Batched count summaries for many sub-tallies in **one** query (no N+1).

    Returns ``{sub_tally_id: count_summary}`` for every requested id; ids with no
    entries get a zeroed summary so the caller can render every tile uniformly.
    """
    ids = list(dict.fromkeys(int(s) for s in sub_tally_ids))  # de-dupe, keep order
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    by_sub: dict[int, list[date]] = {sid: [] for sid in ids}
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT sub_tally_id, occurred_at FROM entry"  # noqa: S608 - placeholders are '?'
            f" WHERE owner_id = ? AND sub_tally_id IN ({placeholders})",
            (owner_id, *ids),
        ).fetchall()
    for r in rows:
        by_sub[r["sub_tally_id"]].append(_kst_day(r["occurred_at"]))

    today = _today_kst()
    return {sid: _count_buckets(days, today) for sid, days in by_sub.items()}


# ---------------------------------------------------------------------------
# Streaks: current + longest
# ---------------------------------------------------------------------------


def _longest_run(distinct_days: Sequence[date]) -> int:
    """Longest run of consecutive days over a set of distinct days."""
    if not distinct_days:
        return 0
    ordered = sorted(distinct_days)
    longest = run = 1
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if (later - earlier).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def _current_run(distinct_days_desc: Sequence[date]) -> int:
    """Run of consecutive days ending on the most-recent day (matches entries.py)."""
    if not distinct_days_desc:
        return 0
    run = 1
    for later, earlier in zip(distinct_days_desc, distinct_days_desc[1:], strict=False):
        if (later - earlier).days == 1:
            run += 1
        else:
            break
    return run


def streaks(sub_tally_id: int, owner_id: int) -> dict[str, int]:
    """Current + longest streak for a sub-tally.

    ``current`` matches ``entries.py``'s cached streak exactly: the run of
    consecutive KST days ending on the most-recent entry day (defined purely from
    stored timestamps, not the wall clock). ``longest`` is the maximum such run
    over all history.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, sub_tally_id, owner_id)

    distinct_desc = sorted(set(days), reverse=True)
    return {
        "current": _current_run(distinct_desc),
        "longest": _longest_run(distinct_desc),
    }


# ---------------------------------------------------------------------------
# Heatmap: dense trailing-365-day series, zero-filled, keyed by KST day
# ---------------------------------------------------------------------------


def heatmap(sub_tally_id: int, owner_id: int, *, days: int = HEATMAP_DAYS) -> list[dict[str, Any]]:
    """A dense trailing-*days*-day series for a contribution heatmap.

    Returns one bucket **per KST day**, oldest first, with *every* day in the
    window present (zero-filled), so a renderer can lay out a fixed grid without
    gap handling. Each bucket is ``{"date": "YYYY-MM-DD", "count": int}`` where
    ``count`` is the number of entries that fell on that KST day. The window is
    the *days* calendar days ending on (and including) today (KST).
    """
    today = _today_kst()
    start = today - timedelta(days=days - 1)

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_days = _entry_days(conn, sub_tally_id, owner_id)

    counts_by_day: dict[date, int] = defaultdict(int)
    for d in entry_days:
        if start <= d <= today:
            counts_by_day[d] += 1

    series: list[dict[str, Any]] = []
    cursor = start
    while cursor <= today:
        series.append({"date": cursor.isoformat(), "count": counts_by_day.get(cursor, 0)})
        cursor += timedelta(days=1)
    return series


# ---------------------------------------------------------------------------
# Per-field stats (joined back through the owner-scoped entry table)
# ---------------------------------------------------------------------------


def _assert_field_kind(
    conn: sqlite3.Connection,
    owner_id: int,
    sub_tally_id: int,
    field_def_id: int,
    expected: Iterable[str],
) -> str:
    """Validate that *field_def_id* belongs to *sub_tally_id* (owned) and has an
    expected kind. Returns the kind. ``field_def`` has no owner_id column, so we
    join through the owner-scoped sub_tally.
    """
    row = conn.execute(
        """SELECT fd.kind AS kind
             FROM field_def fd
             JOIN sub_tally st ON st.id = fd.sub_tally_id
            WHERE fd.id = ? AND fd.sub_tally_id = ? AND st.owner_id = ?""",
        (field_def_id, sub_tally_id, owner_id),
    ).fetchone()
    if row is None:
        raise FieldNotFoundError(
            f"field_def {field_def_id} not found on sub_tally {sub_tally_id} for owner {owner_id}"
        )
    kind = row["kind"]
    expected_set = set(expected)
    if kind not in expected_set:
        raise FieldKindError(
            f"field_def {field_def_id} has kind {kind!r}, expected one of {sorted(expected_set)}"
        )
    return kind


class FieldNotFoundError(LookupError):
    """Raised when a field_def doesn't belong to the sub-tally/owner."""


class FieldKindError(ValueError):
    """Raised when a field_def's kind doesn't match the requested stat."""


def _period_bounds(today: date, period: str) -> tuple[date, date, date]:
    """Return ``(this_start, last_start, this_end_exclusive)`` for a period.

    ``period`` is ``"week"``, ``"month"``, or ``"year"``. The "last" period is the
    immediately preceding one of the same kind. All bounds are KST days; the
    upper bound is exclusive (``this_end_exclusive`` = start of the next period).
    """
    if period == "week":
        this_start = _week_start(today)
        last_start = this_start - timedelta(days=7)
        this_end = this_start + timedelta(days=7)
    elif period == "month":
        this_start = _month_start(today)
        last_start = _month_start(this_start - timedelta(days=1))
        this_end = _add_month(this_start)
    elif period == "year":
        this_start = _year_start(today)
        last_start = this_start.replace(year=this_start.year - 1)
        this_end = this_start.replace(year=this_start.year + 1)
    else:
        raise ValueError(f"unknown period {period!r}; expected week/month/year")
    return this_start, last_start, this_end


def tag_frequency(
    sub_tally_id: int,
    owner_id: int,
    field_def_id: int,
    *,
    period: str = "month",
    top: int | None = None,
) -> dict[str, Any]:
    """Top tags for a tag-group field, with this-period-vs-last-period trend.

    Returns ``{"tags": [{tag_id, name, total, this_period, last_period, delta}, ...]}``
    sorted by lifetime ``total`` descending. *period* is week/month/year; *top*
    truncates the list if given. Counts are entries (an entry tagged with a tag
    counts once for that tag).
    """
    today = _today_kst()
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _assert_field_kind(conn, owner_id, sub_tally_id, field_def_id, ("tag_group",))
        rows = conn.execute(
            """SELECT t.id AS tag_id, t.name AS name, e.occurred_at AS occurred_at
                 FROM entry_tag et
                 JOIN entry e ON e.id = et.entry_id
                 JOIN tag t   ON t.id = et.tag_id
                WHERE e.owner_id = ?
                  AND e.sub_tally_id = ?
                  AND t.field_def_id = ?""",
            (owner_id, sub_tally_id, field_def_id),
        ).fetchall()

    agg: dict[int, dict[str, Any]] = {}
    for r in rows:
        d = _kst_day(r["occurred_at"])
        entry = agg.setdefault(
            r["tag_id"],
            {
                "tag_id": r["tag_id"],
                "name": r["name"],
                "total": 0,
                "this_period": 0,
                "last_period": 0,
            },
        )
        entry["total"] += 1
        if this_start <= d < this_end:
            entry["this_period"] += 1
        elif last_start <= d < this_start:
            entry["last_period"] += 1

    tags = sorted(agg.values(), key=lambda t: (-t["total"], t["name"]))
    for t in tags:
        t["delta"] = t["this_period"] - t["last_period"]
    if top is not None:
        tags = tags[:top]
    return {"period": period, "tags": tags}


def scale_distribution(
    sub_tally_id: int,
    owner_id: int,
    field_def_id: int,
) -> dict[str, Any]:
    """Distribution of a scale field's values across all history.

    Returns ``{"distribution": [{value, count}, ...], "count": n, "average": x}``.
    ``distribution`` is sorted by scale value ascending; ``count`` is the number
    of entries that recorded the field; ``average`` is the mean value (``None``
    when there are no values).
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _assert_field_kind(conn, owner_id, sub_tally_id, field_def_id, ("scale",))
        rows = conn.execute(
            """SELECT ev.num_value AS num_value
                 FROM entry_value ev
                 JOIN entry e ON e.id = ev.entry_id
                WHERE e.owner_id = ?
                  AND e.sub_tally_id = ?
                  AND ev.field_def_id = ?
                  AND ev.num_value IS NOT NULL""",
            (owner_id, sub_tally_id, field_def_id),
        ).fetchall()

    buckets: dict[float, int] = defaultdict(int)
    total = 0.0
    n = 0
    for r in rows:
        v = r["num_value"]
        buckets[v] += 1
        total += v
        n += 1

    distribution = [{"value": v, "count": c} for v, c in sorted(buckets.items())]
    average = round(total / n, 2) if n else None
    return {"distribution": distribution, "count": n, "average": average}


def count_totals(
    sub_tally_id: int,
    owner_id: int,
    field_def_id: int,
    *,
    period: str = "month",
) -> dict[str, Any]:
    """Totals + period trend for a count field.

    Returns ``{"lifetime": x, "this_period": y, "last_period": z, "delta": y-z,
    "entries": n}`` where the totals **sum** the count field's values (not entry
    counts), ``entries`` is how many entries recorded the field, and the period
    is week/month/year in KST.
    """
    today = _today_kst()
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _assert_field_kind(conn, owner_id, sub_tally_id, field_def_id, ("count",))
        rows = conn.execute(
            """SELECT ev.num_value AS num_value, e.occurred_at AS occurred_at
                 FROM entry_value ev
                 JOIN entry e ON e.id = ev.entry_id
                WHERE e.owner_id = ?
                  AND e.sub_tally_id = ?
                  AND ev.field_def_id = ?
                  AND ev.num_value IS NOT NULL""",
            (owner_id, sub_tally_id, field_def_id),
        ).fetchall()

    lifetime = 0.0
    this_period = 0.0
    last_period = 0.0
    n = 0
    for r in rows:
        v = r["num_value"]
        d = _kst_day(r["occurred_at"])
        lifetime += v
        n += 1
        if this_start <= d < this_end:
            this_period += v
        elif last_start <= d < this_start:
            last_period += v

    return {
        "period": period,
        "lifetime": lifetime,
        "this_period": this_period,
        "last_period": last_period,
        "delta": this_period - last_period,
        "entries": n,
    }
