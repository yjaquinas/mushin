"""Calendar-grid and comment-deep-link helpers used by ``_history_context.py``.

Split out (route-structure rule, option 2 applied to a non-route companion
module) so ``_history_context.py`` stays clear of the 300-line ceiling. Not
imported anywhere outside the ``web`` package's own context-assembly chain.
"""

from __future__ import annotations

import calendar as cal
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app import ui_strings
from app.services import entries
from app.services.entries import EntryNotFoundError


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last day of *year*-*month*."""
    first = date(year, month, 1)
    last_day = cal.monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _build_calendar_context(
    activity_id: int,
    owner_id: int,
    *,
    year: int,
    month: int,
    tz: ZoneInfo,
    selected: date | None = None,
) -> dict[str, Any]:
    """Month-grid context: weeks of ``.cal-day`` cells, marked + today flags.

    Weeks are Monday-first (matching ``stats._week_start``), padded with
    ``None`` cells for days outside *year*-*month* so the grid stays a regular
    table. Marked days are derived from the activity's entry days for that
    month (one query via ``entries.list_for_activity`` would over-fetch, so we
    use ``stats.heatmap`` only when the month is within the trailing 365 days;
    otherwise we read entries directly).

    *selected*, when given, flags the matching cell's ``selected`` key so the
    template can render ``.cal-day--selected`` on it. Defaults to ``None``
    (no cell selected) for callers that don't track a tapped day.
    """
    first, last = _month_bounds(year, month)
    today = datetime.now(UTC).date()
    # Reuse stats._entry_days via the public heatmap when possible would be
    # awkward for arbitrary months, so read entry days directly (owner-scoped).
    rows = entries.list_for_activity(owner_id, activity_id)
    marked_days: set[date] = set()
    for e in rows:
        d = entries._local_day(e["occurred_at"], tz)
        if first <= d <= last:
            marked_days.add(d)

    weeks: list[list[dict[str, Any] | None]] = []
    week: list[dict[str, Any] | None] = []
    # Monday-first padding before the first day of the month.
    for _ in range(first.weekday()):
        week.append(None)
    cursor = first
    while cursor <= last:
        week.append(
            {
                "date": cursor.isoformat(),
                "day": cursor.day,
                "marked": cursor in marked_days,
                "today": cursor == today,
                "selected": cursor == selected,
            }
        )
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor = cursor + timedelta(days=1)
    if week:
        while len(week) < 7:
            week.append(None)
        weeks.append(week)

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    return {
        "year": year,
        "month": month,
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "weekdays": ui_strings.CALENDAR_WEEKDAYS,
    }


def _entries_on_day(
    activity_id: int, owner_id: int, day: date, *, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """All of an activity's entries (hydrated) whose local day in *tz* is *day*."""
    rows = entries.list_for_activity(owner_id, activity_id)
    return [e for e in rows if entries._local_day(e["occurred_at"], tz) == day]


def _resolve_comment_deep_link(
    raw_c: str | None, *, activity_id: int, owner_id: int, tz: ZoneInfo
) -> tuple[int, date] | None:
    """Resolve a ``?c={entry_id}`` query param to ``(entry_id, local_day)``.

    Used by a notification click-through to land the viewer on the right
    calendar day with that entry's comment thread pre-expanded. Returns
    ``None`` — silently, no error — when *raw_c* is missing, non-numeric, or
    resolves to an entry that doesn't exist or belongs to a different
    activity/owner; the caller falls back to no day selected and no expand,
    matching the old flat-list ``?c=`` behavior this replaces.
    """
    if raw_c is None:
        return None
    try:
        entry_id = int(raw_c)
    except ValueError:
        return None
    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return None
    if entry["activity_id"] != activity_id:
        return None
    return entry_id, entries._local_day(entry["occurred_at"], tz)
