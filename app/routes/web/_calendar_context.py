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

    Weeks are Sunday-first, padded with adjacent-month day cells so the grid
    stays a regular table. Marked days are derived from the activity's entry
    days across the calendar's full visible range, including adjacent-month
    padding cells.

    *selected*, when given, flags the matching cell's ``selected`` key so the
    template can render ``.cal-day--selected`` on it. Defaults to ``None``
    (no cell selected) for callers that don't track a tapped day.
    """
    first, last = _month_bounds(year, month)
    today = datetime.now(UTC).date()
    leading_pad = (first.weekday() + 1) % 7
    trailing_pad = (7 - ((leading_pad + last.day) % 7)) % 7
    visible_start = first - timedelta(days=leading_pad)
    visible_end = last + timedelta(days=trailing_pad)
    # Reuse stats._entry_days via the public heatmap when possible would be
    # awkward for arbitrary months, so read entry days directly (owner-scoped).
    rows = entries.list_for_activity(owner_id, activity_id)
    marked_days: set[date] = set()
    for e in rows:
        d = entries._local_day(e["occurred_at"], tz)
        if visible_start <= d <= visible_end:
            marked_days.add(d)

    weeks: list[list[dict[str, Any]]] = []
    week: list[dict[str, Any]] = []
    # Sunday-first padding before the first day of the month.
    for offset in range(leading_pad, 0, -1):
        cursor = first - timedelta(days=offset)
        week.append(
            {
                "date": cursor.isoformat(),
                "day": cursor.day,
                "marked": cursor in marked_days,
                "today": cursor == today,
                "selected": cursor == selected,
                "current_month": False,
            }
        )
    cursor = first
    while cursor <= last:
        week.append(
            {
                "date": cursor.isoformat(),
                "day": cursor.day,
                "marked": cursor in marked_days,
                "today": cursor == today,
                "selected": cursor == selected,
                "current_month": True,
            }
        )
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor = cursor + timedelta(days=1)
    if week:
        trailing_cursor = last + timedelta(days=1)
        while len(week) < 7:
            week.append(
                {
                    "date": trailing_cursor.isoformat(),
                    "day": trailing_cursor.day,
                    "marked": trailing_cursor in marked_days,
                    "today": trailing_cursor == today,
                    "selected": trailing_cursor == selected,
                    "current_month": False,
                }
            )
            trailing_cursor = trailing_cursor + timedelta(days=1)
        weeks.append(week)

    for week in weeks:
        for idx, cell in enumerate(week):
            prev_current = week[idx - 1]["current_month"] if idx > 0 else True
            next_current = week[idx + 1]["current_month"] if idx < len(week) - 1 else True
            cell["adjacent_group_start"] = not cell["current_month"] and prev_current
            cell["adjacent_group_end"] = not cell["current_month"] and next_current

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
