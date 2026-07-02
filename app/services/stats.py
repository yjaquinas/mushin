"""Renderer-agnostic stats for the Mushin service layer.

No HTTP, no Jinja, no HXML. Every function takes ``owner_id`` as a required
argument (multi-user isolation is non-negotiable) and returns plain Python data
structures (dicts / lists of dicts) that either renderer can consume.

The user's local timezone is the calendar
------------------------------------------
Every "day", "week", "month", and "year" bucket is a calendar bucket **in the
caller-supplied timezone** (``tz: ZoneInfo`` — the web renderer passes the user's
``user.timezone``; this layer never looks it up). We reuse
``entries._local_day`` so the day a timestamp falls in agrees exactly with the
streak math in ``entries.py`` (same-day entries collapse, midnight boundaries
land on the same side). The "current period" boundaries are derived from the
**current wall-clock day in that timezone**, never cached, because a period
boundary moves with time and no new entry.

Scoping + batching
------------------
Counting / streak / heatmap functions read ``entry`` rows scoped to the owner.
Field-level functions (tag-group, scale, count) read ``entry_value`` / ``tag`` /
``entry_tag`` joined back through the owner-scoped ``entry`` table so a value
can never reach across tenants. ``counts_for_activities`` accepts a *list* of
activity ids and answers in **one** query (``WHERE activity_id IN (...)``) to
avoid N+1 fan-out when a category renders many activities at once.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.services import _db, entries
from app.services.entries import _local_day

# Trailing-window length for the contribution heatmap (inclusive of today).
HEATMAP_DAYS = 365


# ---------------------------------------------------------------------------
# Period boundaries (derived from the current wall clock in tz, never cached)
# ---------------------------------------------------------------------------


def _today_local(tz: ZoneInfo) -> date:
    """The current calendar day in the caller-supplied timezone *tz*."""
    return datetime.now(tz).date()


def _week_start(day: date) -> date:
    """Monday-anchored start of *day*'s ISO week."""
    return day - timedelta(days=day.weekday())


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _year_start(day: date) -> date:
    return day.replace(month=1, day=1)


def _add_month(day: date, n: int = 1) -> date:
    """First day of the month *n* months from *day*'s month.

    Day-of-month is normalized to 1 (the original semantics: used to build an
    exclusive month-end bound). *n* may be negative to step backward.
    """
    # 0-based month index from year 0, shifted by n, then split back out.
    total = (day.year * 12 + (day.month - 1)) + n
    year, month0 = divmod(total, 12)
    return date(year, month0 + 1, 1)


def _add_week(day: date, n: int) -> date:
    """The day *n* weeks from *day* (negative *n* steps backward)."""
    return day + timedelta(weeks=n)


def _add_year(day: date, n: int) -> date:
    """The day *n* years from *day*, clamping Feb 29 to Feb 28 on non-leap years."""
    try:
        return day.replace(year=day.year + n)
    except ValueError:
        # day is Feb 29 and the target year is not a leap year.
        return day.replace(year=day.year + n, day=28)


def _shift_period(anchor: date, kind: str, n: int) -> date:
    """Start date of the period *n* steps from the period containing *anchor*.

    *kind* is ``"week"``, ``"month"``, or ``"year"``. The anchor is first
    normalized to its period start (Monday / 1st / Jan 1), then shifted by *n*
    periods (negative goes back, positive goes forward). All dates are local
    calendar days (the caller decides the zone when it computes the anchor).
    """
    if kind == "week":
        return _add_week(_week_start(anchor), n)
    if kind == "month":
        return _add_month(_month_start(anchor), n)
    if kind == "year":
        return _add_year(_year_start(anchor), n)
    raise ValueError(f"unknown kind {kind!r}; expected week/month/year")


# ---------------------------------------------------------------------------
# Reading entry days (owner-scoped)
# ---------------------------------------------------------------------------


def _entry_days(
    conn: sqlite3.Connection, activity_id: int, owner_id: int, tz: ZoneInfo
) -> list[date]:
    """Every entry's local day (in *tz*) for an activity, newest day first, with
    repeats.

    Repeats are preserved so callers that count occurrences (heatmap, period
    counts) see them; callers that want distinct days dedupe themselves.
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
    return [_local_day(r["occurred_at"], tz) for r in rows]


# ---------------------------------------------------------------------------
# Counts: week / month / year / lifetime + average per week
# ---------------------------------------------------------------------------


def _count_buckets(days: Sequence[date], today: date) -> dict[str, Any]:
    """Build the count summary for a single activity from its entry days."""
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
    # measured in whole local weeks (min 1 so a single day isn't divided to zero).
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


def counts(activity_id: int, owner_id: int, *, tz: ZoneInfo) -> dict[str, Any]:
    """Count summary for one activity: this week/month/year, lifetime, avg/week.

    All windows are calendar windows in the caller-supplied timezone *tz*,
    anchored on the current local day.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, activity_id, owner_id, tz)
    return _count_buckets(days, _today_local(tz))


def counts_for_activities(
    activity_ids: Iterable[int], owner_id: int, *, tz: ZoneInfo
) -> dict[int, dict[str, Any]]:
    """Batched count summaries for many activities in **one** query (no N+1).

    Returns ``{activity_id: count_summary}`` for every requested id; ids with no
    entries get a zeroed summary so the caller can render every tile uniformly.
    All windows are anchored on the current local day in *tz*.
    """
    ids = list(dict.fromkeys(int(s) for s in activity_ids))  # de-dupe, keep order
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    by_sub: dict[int, list[date]] = {sid: [] for sid in ids}
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT activity_id, occurred_at FROM entry"  # noqa: S608 - placeholders are '?'
            f" WHERE owner_id = ? AND activity_id IN ({placeholders})",
            (owner_id, *ids),
        ).fetchall()
    for r in rows:
        by_sub[r["activity_id"]].append(_local_day(r["occurred_at"], tz))

    today = _today_local(tz)
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


def streaks(activity_id: int, owner_id: int, *, tz: ZoneInfo) -> dict[str, int]:
    """Current + longest streak for an activity.

    ``current`` matches ``entries.py``'s cached streak exactly when computed with
    the same *tz*: the run of consecutive local days ending on the most-recent
    entry day (defined purely from stored timestamps, not the wall clock).
    ``longest`` is the maximum such run over all history.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, activity_id, owner_id, tz)

    distinct_desc = sorted(set(days), reverse=True)
    return {
        "current": _current_run(distinct_desc),
        "longest": _longest_run(distinct_desc),
    }


# ---------------------------------------------------------------------------
# Heatmap: dense trailing-365-day series, zero-filled, keyed by local day
# ---------------------------------------------------------------------------


def _zero_fill(
    entry_days: Sequence[date], start: date, end: date
) -> list[dict[str, Any]]:
    """Bucket *entry_days* into a dense, zero-filled ``[start, end]`` day series.

    Pure (no query): takes already-read local days and returns one bucket **per
    day** in the inclusive range, oldest first, with every day present
    (zero-filled). Each bucket is ``{"date": "YYYY-MM-DD", "count": int}`` where
    ``count`` is how many of *entry_days* fell on that day. If ``end`` is before
    ``start`` the series is empty.
    """
    counts_by_day: dict[date, int] = defaultdict(int)
    for d in entry_days:
        if start <= d <= end:
            counts_by_day[d] += 1

    series: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        series.append({"date": cursor.isoformat(), "count": counts_by_day.get(cursor, 0)})
        cursor += timedelta(days=1)
    return series


# Quarter-start months labeled on the heatmap strip (Jan/Apr/Jul/Oct) — see
# ui_strings.HEATMAP_QUARTER_LABELS for the renderer-facing label text.
_HEATMAP_QUARTER_MONTHS = (1, 4, 7, 10)


def _calendar_year_active_days(entry_days: Sequence[date], *, year: int) -> list[dict[str, Any]]:
    """Bucket *entry_days* into a calendar-year active-day series for *year*.

    Pure (no query): takes already-read local days and returns one bucket **per
    ISO week** (Monday-anchored) from the week containing Jan 1 through the
    week containing Dec 31 of *year*, oldest first — a fixed-length series
    regardless of the current date, so weeks later in the year that haven't
    happened yet are zero-filled rather than omitted (the card's height never
    changes as the year progresses). Each bucket is ``{"week_start":
    "YYYY-MM-DD", "intensity": int, "quarter_month": int | None}`` where
    ``intensity`` is the number of *distinct* calendar days in that week that
    had at least one entry (not the raw entry count) — naturally bounded
    ``0..7`` since a week has 7 distinct days and same-day entries collapse via
    the set — and ``quarter_month`` is set to 1/4/7/10 on the one week whose
    span contains that quarter-start month's 1st, else ``None``.
    """
    start_week = _week_start(date(year, 1, 1))
    end_week = _week_start(date(year, 12, 31))
    quarter_starts = {date(year, m, 1): m for m in _HEATMAP_QUARTER_MONTHS}

    active_by_week: dict[date, set[date]] = defaultdict(set)
    for d in entry_days:
        wk = _week_start(d)
        if start_week <= wk <= end_week:
            active_by_week[wk].add(d)

    series: list[dict[str, Any]] = []
    cursor = start_week
    while cursor <= end_week:
        week_end = cursor + timedelta(days=6)
        quarter_month = next(
            (m for qd, m in quarter_starts.items() if cursor <= qd <= week_end), None
        )
        series.append(
            {
                "week_start": cursor.isoformat(),
                "intensity": len(active_by_week.get(cursor, ())),
                "quarter_month": quarter_month,
            }
        )
        cursor = _add_week(cursor, 1)
    return series


def heatmap_range(
    activity_id: int, owner_id: int, start: date, end: date, *, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """A dense, zero-filled day series over ``[start, end]`` inclusive.

    Returns one bucket **per local day** (in *tz*), oldest first, with *every*
    day in the range present (zero-filled), so a renderer can lay out a fixed
    grid without gap handling. Each bucket is ``{"date": "YYYY-MM-DD", "count":
    int}`` where ``count`` is the number of entries that fell on that local day.
    If ``end`` is before ``start`` the series is empty.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_days = _entry_days(conn, activity_id, owner_id, tz)

    return _zero_fill(entry_days, start, end)


def heatmap(
    activity_id: int, owner_id: int, *, tz: ZoneInfo, days: int = HEATMAP_DAYS
) -> list[dict[str, Any]]:
    """A dense trailing-*days*-day series for a contribution heatmap.

    The window is the *days* calendar days ending on (and including) today
    in *tz*. Thin wrapper over :func:`heatmap_range`.
    """
    today = _today_local(tz)
    return heatmap_range(
        activity_id, owner_id, today - timedelta(days=days - 1), today, tz=tz
    )


def card_stats(activity_id: int, owner_id: int, *, tz: ZoneInfo) -> dict[str, Any]:
    """Counts + streaks + heatmap for the activity-detail summary card in **one read**.

    The summary card re-renders on every ``log-saved`` HTMX event (the hottest
    action in the app). Rather than call :func:`counts`, :func:`streaks`, and the
    heatmap helper separately — three independent owner-scoped scans of the same
    ``entry`` rows — this opens **one** ``db.connect()`` and does **one**
    :func:`_entry_days` read, then derives all three views from the days held in
    memory via the same pure helpers those functions use. The counts and streaks
    values are identical to calling ``counts()`` and ``streaks()`` on the same
    data.

    Returns ``{"counts": ..., "streaks": ..., "heatmap": ...}``. The heatmap
    covers the **current calendar year** (in *tz*) — see
    :func:`_calendar_year_active_days` for the bucket shape.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, activity_id, owner_id, tz)

    today = _today_local(tz)
    distinct_desc = sorted(set(days), reverse=True)
    return {
        "counts": _count_buckets(days, today),
        "streaks": {
            "current": _current_run(distinct_desc),
            "longest": _longest_run(distinct_desc),
        },
        "heatmap": _calendar_year_active_days(days, year=today.year),
    }


def period_entries(
    activity_id: int, owner_id: int, start: date, end: date, *, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """Hydrated entries whose local day (in *tz*) falls in ``[start, end]``,
    newest-first.

    Owner-scoped via :func:`entries.list_for_activity` (which only reads rows
    for *owner_id*). Filtering is done in Python on the local day so the boundary
    rule matches the rest of this module exactly. Sorted by ``occurred_at``
    descending (newest first).
    """
    rows = entries.list_for_activity(owner_id, activity_id)
    selected = [r for r in rows if start <= _local_day(r["occurred_at"], tz) <= end]
    selected.sort(key=lambda r: r["occurred_at"], reverse=True)
    return selected


# ---------------------------------------------------------------------------
# Per-field stats (joined back through the owner-scoped entry table)
# ---------------------------------------------------------------------------


def _assert_field_kind(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_id: int,
    field_def_id: int,
    expected: Iterable[str],
) -> str:
    """Validate that *field_def_id* belongs to *activity_id* (owned) and has an
    expected kind. Returns the kind. ``field_def`` has no owner_id column, so we
    join through the owner-scoped activity.
    """
    row = conn.execute(
        """SELECT fd.kind AS kind
             FROM field_def fd
             JOIN activity st ON st.id = fd.activity_id
            WHERE fd.id = ? AND fd.activity_id = ? AND st.owner_id = ?""",
        (field_def_id, activity_id, owner_id),
    ).fetchone()
    if row is None:
        raise FieldNotFoundError(
            f"field_def {field_def_id} not found on activity {activity_id} for owner {owner_id}"
        )
    kind = row["kind"]
    expected_set = set(expected)
    if kind not in expected_set:
        raise FieldKindError(
            f"field_def {field_def_id} has kind {kind!r}, expected one of {sorted(expected_set)}"
        )
    return kind


class FieldNotFoundError(LookupError):
    """Raised when a field_def doesn't belong to the activity/owner."""


class FieldKindError(ValueError):
    """Raised when a field_def's kind doesn't match the requested stat."""


def _period_bounds(today: date, period: str) -> tuple[date, date, date]:
    """Return ``(this_start, last_start, this_end_exclusive)`` for a period.

    ``period`` is ``"week"``, ``"month"``, or ``"year"``. The "last" period is the
    immediately preceding one of the same kind. All bounds are local calendar
    days (the caller's *today* fixes the zone); the upper bound is exclusive
    (``this_end_exclusive`` = start of the next period).
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
    activity_id: int,
    owner_id: int,
    field_def_id: int,
    *,
    tz: ZoneInfo,
    period: str = "month",
    top: int | None = None,
) -> dict[str, Any]:
    """Top tags for a tag-group field, with this-period-vs-last-period trend.

    Returns ``{"tags": [{tag_id, name, total, this_period, last_period, delta}, ...]}``
    sorted by lifetime ``total`` descending. *period* is week/month/year in the
    caller-supplied timezone *tz*; *top* truncates the list if given. Counts are
    entries (an entry tagged with a tag counts once for that tag).
    """
    today = _today_local(tz)
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _assert_field_kind(conn, owner_id, activity_id, field_def_id, ("tag_group",))
        rows = conn.execute(
            """SELECT t.id AS tag_id, t.name AS name, e.occurred_at AS occurred_at
                 FROM entry_tag et
                 JOIN entry e ON e.id = et.entry_id
                 JOIN tag t   ON t.id = et.tag_id
                WHERE e.owner_id = ?
                  AND e.activity_id = ?
                  AND t.field_def_id = ?""",
            (owner_id, activity_id, field_def_id),
        ).fetchall()

    agg: dict[int, dict[str, Any]] = {}
    for r in rows:
        d = _local_day(r["occurred_at"], tz)
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
    activity_id: int,
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
        _assert_field_kind(conn, owner_id, activity_id, field_def_id, ("scale",))
        rows = conn.execute(
            """SELECT ev.num_value AS num_value
                 FROM entry_value ev
                 JOIN entry e ON e.id = ev.entry_id
                WHERE e.owner_id = ?
                  AND e.activity_id = ?
                  AND ev.field_def_id = ?
                  AND ev.num_value IS NOT NULL""",
            (owner_id, activity_id, field_def_id),
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
    activity_id: int,
    owner_id: int,
    field_def_id: int,
    *,
    tz: ZoneInfo,
    period: str = "month",
) -> dict[str, Any]:
    """Totals + period trend for a count field.

    Returns ``{"lifetime": x, "this_period": y, "last_period": z, "delta": y-z,
    "entries": n}`` where the totals **sum** the count field's values (not entry
    counts), ``entries`` is how many entries recorded the field, and the period
    is week/month/year in the caller-supplied timezone *tz*.
    """
    today = _today_local(tz)
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _assert_field_kind(conn, owner_id, activity_id, field_def_id, ("count",))
        rows = conn.execute(
            """SELECT ev.num_value AS num_value, e.occurred_at AS occurred_at
                 FROM entry_value ev
                 JOIN entry e ON e.id = ev.entry_id
                WHERE e.owner_id = ?
                  AND e.activity_id = ?
                  AND ev.field_def_id = ?
                  AND ev.num_value IS NOT NULL""",
            (owner_id, activity_id, field_def_id),
        ).fetchall()

    lifetime = 0.0
    this_period = 0.0
    last_period = 0.0
    n = 0
    for r in rows:
        v = r["num_value"]
        d = _local_day(r["occurred_at"], tz)
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
