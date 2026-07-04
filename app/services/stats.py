"""Renderer-agnostic stats for the Mushin service layer.

No HTTP, no Jinja, no HXML. Every function takes ``owner_id`` as a required
argument (multi-user isolation is non-negotiable) and returns plain Python data
structures (dicts / lists of dicts) that either renderer can consume.

The user's local timezone is the calendar
------------------------------------------
Every "day", "week", "month", and "year" bucket is a calendar bucket **in the
caller-supplied timezone** (``tz: ZoneInfo`` — the web renderer passes the user's
stored timezone; this layer never looks it up). We reuse
``entries._local_day`` so the day a timestamp falls in agrees exactly with the
streak math in ``entries.py``.

Scoping + batching
------------------
Counting / streak / heatmap functions read ``entry`` rows scoped to the owner.
All queries join through the owner-scoped ``entry`` table so data can never
reach across tenants.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.services import _db, entries
from app.services.entries import _local_day

QUARTER_START_MONTHS = (1, 4, 7, 10)


# ---------------------------------------------------------------------------
# Period boundaries
# ---------------------------------------------------------------------------


def _today_local(tz: ZoneInfo) -> date:
    """The current calendar day in the caller-supplied timezone *tz*."""
    return datetime.now(tz).date()


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _sunday_week_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _year_start(day: date) -> date:
    return day.replace(month=1, day=1)


def _add_month(day: date, n: int = 1) -> date:
    total = (day.year * 12 + (day.month - 1)) + n
    year, month0 = divmod(total, 12)
    return date(year, month0 + 1, 1)


def _add_week(day: date, n: int) -> date:
    return day + timedelta(weeks=n)


def _add_year(day: date, n: int) -> date:
    try:
        return day.replace(year=day.year + n)
    except ValueError:
        return day.replace(year=day.year + n, day=28)


def _shift_period(anchor: date, kind: str, n: int) -> date:
    if kind == "week":
        return _add_week(_sunday_week_start(anchor), n)
    if kind == "month":
        return _add_month(_month_start(anchor), n)
    if kind == "year":
        return _add_year(_month_start(anchor), n)
    raise ValueError(f"unknown kind {kind!r}; expected week/month/year")


def _period_bounds(today: date, period: str) -> tuple[date, date, date]:
    this_start = _shift_period(today, period, 0)
    last_start = _shift_period(today, period, -1)
    this_end = _shift_period(today, period, 1)
    return this_start, last_start, this_end


# ---------------------------------------------------------------------------
# Reading entry days (owner-scoped)
# ---------------------------------------------------------------------------


def _entry_days(
    conn: sqlite3.Connection, activity_id: int, owner_id: int, tz: ZoneInfo
) -> list[date]:
    """Every entry's local day (in *tz*) for an activity, newest day first."""
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
# Card stats (count, streak, heatmap)
# ---------------------------------------------------------------------------


def period_entries(
    activity_id: int,
    owner_id: int,
    start: date,
    end: date,
    *,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Return entries for *activity_id* in the date range [start, end)."""
    return entries.list_entries(owner_id, activity_id, tz=tz, start=start, end=end)


def heatmap_range(
    activity_id: int,
    owner_id: int,
    start: date,
    end: date,
    *,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Return daily entry counts for the range [start, end]."""
    rows = entries.list_entries(owner_id, activity_id, tz=tz, start=start, end=end + __import__("datetime").timedelta(days=1))
    counts: dict[str, int] = {}
    for r in rows:
        d = entries._local_day(r["occurred_at"], tz).isoformat()
        counts[d] = counts.get(d, 0) + 1
    result = []
    cursor = start
    while cursor <= end:
        result.append({"date": cursor.isoformat(), "count": counts.get(cursor.isoformat(), 0)})
        cursor += __import__("datetime").timedelta(days=1)
    return result


def card_stats(
    activity_id: int,
    owner_id: int,
    *,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """Count, streak, and heatmap for a single activity."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        days = _entry_days(conn, activity_id, owner_id, tz)
        entry_count = conn.execute(
            "SELECT COUNT(*) AS n FROM entry WHERE owner_id = ? AND activity_id = ?",
            (owner_id, activity_id),
        ).fetchone()["n"]

    # Distinct days for streak/heatmap.
    distinct_days = []
    seen: set[date] = set()
    for d in days:
        if d not in seen:
            distinct_days.append(d)
            seen.add(d)

    # Streak: consecutive days from most recent.
    distinct_days.sort(reverse=True)
    streak = 0
    if distinct_days:
        streak = 1
        for i in range(1, len(distinct_days)):
            expected = distinct_days[i - 1] - timedelta(days=1)
            if distinct_days[i] == expected:
                streak += 1
            else:
                break

    average_weekly = 0.0
    if distinct_days:
        span_days = (distinct_days[0] - distinct_days[-1]).days + 1
        span_weeks = max(1, ceil(span_days / 7))
        average_weekly = entry_count / span_weeks

    # Heatmap: current calendar year, grouped into Sunday-starting week buckets.
    today = _today_local(tz)
    heatmap_start = _year_start(today)
    heatmap_end = date(today.year, 12, 31)
    day_counts: dict[date, int] = {}
    for d in distinct_days:
        if heatmap_start <= d <= today:
            day_counts[d] = day_counts.get(d, 0) + 1

    heatmap = _build_heatmap_weeks(heatmap_start, heatmap_end, day_counts)

    # Period counts.
    this_start, last_start, this_end = _period_bounds(today, "month")
    this_month = sum(1 for d in distinct_days if this_start <= d < this_end)
    last_month = sum(1 for d in distinct_days if last_start <= d < this_start)

    # Year counts.
    year_start = _year_start(today)
    this_year = sum(1 for d in distinct_days if d >= year_start)
    last_year_start = year_start.replace(year=year_start.year - 1)
    last_year = sum(1 for d in distinct_days if last_year_start <= d < year_start)

    return {
        "counts": {
            "lifetime": len(distinct_days),
            "this_month": this_month,
            "last_month": last_month,
            "month_delta": this_month - last_month,
            "this_year": this_year,
            "last_year": last_year,
            "year_delta": this_year - last_year,
        },
        "streaks": {
            "current": streak,
            "best": _best_streak(distinct_days),
        },
        "average_weekly_count": average_weekly,
        "heatmap": heatmap,
    }


def _build_heatmap_weeks(
    start: date, end: date, day_counts: dict[date, int]
) -> list[dict[str, Any]]:
    heatmap_weeks: list[dict[str, Any]] = []
    cursor = _sunday_week_start(start)
    week_days: list[date] = []
    while cursor <= end:
        week_days.append(cursor)
        if len(week_days) == 7 or cursor == end:
            heatmap_weeks.append(
                {
                    "intensity": sum(day_counts.get(d, 0) for d in week_days),
                    "quarter_month": _quarter_month_for_bucket(week_days),
                }
            )
            week_days = []
        cursor += timedelta(days=1)
    if week_days:
        while len(week_days) < 7:
            week_days.append(cursor)
            cursor += timedelta(days=1)
        heatmap_weeks.append(
            {
                "intensity": sum(day_counts.get(d, 0) for d in week_days),
                "quarter_month": _quarter_month_for_bucket(week_days),
            }
        )
    return heatmap_weeks


def _quarter_month_for_bucket(days: list[date]) -> int | None:
    for day in days:
        if day.day == 1 and day.month in QUARTER_START_MONTHS:
            return day.month
    return None


def _best_streak(days: list[date]) -> int:
    """Best streak from a sorted (newest-first) list of distinct days."""
    if not days:
        return 0
    best = 1
    current = 1
    for i in range(1, len(days)):
        expected = days[i - 1] - timedelta(days=1)
        if days[i] == expected:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


# ---------------------------------------------------------------------------
# Tag frequency (uses entry.tags column — comma-separated tag ids)
# ---------------------------------------------------------------------------


def tag_frequency(
    activity_id: int,
    owner_id: int,
    field_def_id: int,
    *,
    tz: ZoneInfo,
    period: str = "month",
    top: int | None = None,
) -> dict[str, Any]:
    """Tag frequency for an activity.

    Returns ``{"tags": [{tag_id, name, total, this_period, last_period, delta}, ...]}``.
    Note: with the new flat schema, tags are stored as comma-separated ids on
    the entry row. This function reads the raw entry.tags column and parses
    it client-side.
    """
    today = _today_local(tz)
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT e.occurred_at AS occurred_at, e.tags AS tags
                 FROM entry e
                WHERE e.owner_id = ?
                  AND e.activity_id = ?
                  AND e.tags IS NOT NULL""",
            (owner_id, activity_id),
        ).fetchall()

    # Parse tag ids from comma-separated strings.
    agg: dict[int, dict[str, Any]] = {}
    for r in rows:
        d = _local_day(r["occurred_at"], tz)
        tag_ids = [int(t) for t in str(r["tags"]).split(",") if t.strip()]
        for tid in tag_ids:
            entry = agg.setdefault(
                tid,
                {
                    "tag_id": tid,
                    "name": f"tag-{tid}",  # Name resolved at render time via lookup
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

    tags = sorted(agg.values(), key=lambda t: (-t["total"], t["tag_id"]))
    for t in tags:
        t["delta"] = t["this_period"] - t["last_period"]
    if top is not None:
        tags = tags[:top]
    return {"period": period, "tags": tags}


# ---------------------------------------------------------------------------
# Scale / count distribution (reads entry.num_value)
# ---------------------------------------------------------------------------


def scale_distribution(
    activity_id: int,
    owner_id: int,
) -> dict[str, Any]:
    """Distribution of num_value across all history."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT num_value AS num_value
                 FROM entry
                WHERE owner_id = ?
                  AND activity_id = ?
                  AND num_value IS NOT NULL""",
            (owner_id, activity_id),
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
    *,
    tz: ZoneInfo,
    period: str = "month",
) -> dict[str, Any]:
    """Totals + period trend for num_value field."""
    today = _today_local(tz)
    this_start, last_start, this_end = _period_bounds(today, period)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT num_value AS num_value, occurred_at AS occurred_at
                 FROM entry
                WHERE owner_id = ?
                  AND activity_id = ?
                  AND num_value IS NOT NULL""",
            (owner_id, activity_id),
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
