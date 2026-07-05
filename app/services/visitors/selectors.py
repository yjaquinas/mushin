"""Calendar selector contexts for visitor analytics."""

from __future__ import annotations

import calendar as cal
from datetime import date, datetime, timedelta

from app import ui_strings
from app.services.visitors import periods as visitor_periods


def selector_context(
    period: str,
    selected_value: str,
    *,
    calendar_month: str | None,
    calendar_year: str | None,
) -> dict[str, object] | None:
    if period == "daily":
        selected = date.fromisoformat(selected_value)
        display = _parse_calendar_month(calendar_month, selected.year, selected.month)
        return _month_grid("daily", display.year, display.month, selected, None)
    if period == "weekly":
        selected = date.fromisoformat(selected_value)
        display = _parse_calendar_month(calendar_month, selected.year, selected.month)
        return _month_grid("weekly", display.year, display.month, None, selected)
    if period == "monthly":
        selected = datetime.strptime(selected_value, "%Y-%m").date()
        display_year = _parse_calendar_year(calendar_year, selected.year)
        return _month_picker(display_year, selected.month)
    if period == "yearly":
        selected_year = int(selected_value)
        display_year = _parse_calendar_year(calendar_year, selected_year)
        return _year_picker(display_year, selected_year)
    return None


def _month_grid(
    period: str,
    year: int,
    month: int,
    selected_day: date | None,
    selected_week: date | None,
) -> dict[str, object]:
    first = date(year, month, 1)
    last = date(year, month, cal.monthrange(year, month)[1])
    weeks: list[list[dict[str, object] | None]] = []
    week: list[dict[str, object] | None] = []
    cursor = first - timedelta(days=first.weekday())
    end = last + timedelta(days=(6 - last.weekday()))
    while cursor <= end:
        week_start = cursor - timedelta(days=cursor.weekday())
        current_week = week_start == (date.today() - timedelta(days=date.today().weekday()))
        week.append(
            {
                "date": cursor.isoformat(),
                "day": cursor.day,
                "in_month": cursor.month == month,
                "selected": selected_day == cursor,
                "week_selected": selected_week == week_start,
                "today": cursor == date.today(),
                "current_week": current_week,
                "week_value": week_start.isoformat(),
            }
        )
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor += timedelta(days=1)
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    prev_month_value = f"{prev_year:04d}-{prev_month:02d}"
    next_month_value = f"{next_year:04d}-{next_month:02d}"
    return {
        "kind": "month-grid",
        "period": period,
        "title": first.strftime("%Y-%m"),
        "weekdays": ui_strings.CALENDAR_WEEKDAYS,
        "weeks": weeks,
        "prev_value": prev_month_value,
        "next_value": next_month_value,
        "prev_period_value": _month_grid_period_value(period, prev_month_value),
        "next_period_value": _month_grid_period_value(period, next_month_value),
    }


def _month_picker(year: int, selected_month: int) -> dict[str, object]:
    today = date.today()
    months = []
    for month in range(1, 13):
        months.append(
            {
                "value": f"{year:04d}-{month:02d}",
                "label": date(year, month, 1).strftime("%b").upper(),
                "selected": month == selected_month,
                "today": year == today.year and month == today.month,
                "drill_week_value": visitor_periods.drill_week_value(f"{year:04d}-{month:02d}"),
            }
        )
    rows = [months[index : index + 4] for index in range(0, 12, 4)]
    return {
        "kind": "month-picker",
        "title": str(year),
        "rows": rows,
        "prev_value": str(year - 1),
        "next_value": str(year + 1),
        "prev_period_value": f"{year - 1:04d}-{selected_month:02d}",
        "next_period_value": f"{year + 1:04d}-{selected_month:02d}",
    }


def _year_picker(display_year: int, selected_year: int) -> dict[str, object]:
    current_year = date.today().year
    start_year = display_year - 5
    years = []
    for year in range(start_year, start_year + 12):
        years.append(
            {
                "value": str(year),
                "label": str(year),
                "selected": year == selected_year,
                "today": year == current_year,
                "drill_month_value": visitor_periods.drill_month_value(str(year)),
            }
        )
    rows = [years[index : index + 4] for index in range(0, 12, 4)]
    return {
        "kind": "year-picker",
        "title": str(display_year),
        "rows": rows,
        "prev_value": str(display_year - 12),
        "next_value": str(display_year + 12),
        "prev_period_value": str(display_year - 12),
        "next_period_value": str(display_year + 12),
    }


def _parse_calendar_month(value: str | None, year: int, month: int) -> date:
    try:
        parsed = datetime.strptime(value or f"{year:04d}-{month:02d}", "%Y-%m")
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return date(year, month, 1)


def _parse_calendar_year(value: str | None, fallback: int) -> int:
    try:
        return int(value or str(fallback))
    except ValueError:
        return fallback


def _month_grid_period_value(period: str, month_value: str) -> str:
    if period == "weekly":
        return visitor_periods.drill_week_value(month_value)
    year, month = month_value.split("-", maxsplit=1)
    return f"{year}-{month}-01"
