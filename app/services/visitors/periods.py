"""Period selection helpers for visitor analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class PeriodWindow:
    key: str
    title: str
    selected_value: str
    start_utc: str
    end_utc: str


def period_window(period: str, selected_value: str | None) -> PeriodWindow:
    today = datetime.now().astimezone().date()
    if period == "weekly":
        start = _parse_week(selected_value, today)
        end = start + timedelta(days=7)
        title = f"{start.strftime('%Y-%m-%d')} to {(end - timedelta(days=1)).strftime('%Y-%m-%d')}"
        return _window("weekly", title, start.isoformat(), start, end)
    if period == "monthly":
        start = _parse_month(selected_value, today)
        end = date(start.year + (start.month // 12), (start.month % 12) + 1, 1)
        return _window("monthly", start.strftime("%Y-%m"), start.strftime("%Y-%m"), start, end)
    if period == "yearly":
        year = _parse_year(selected_value, today.year)
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        return _window("yearly", str(year), str(year), start, end)
    target = _parse_day(selected_value, today)
    return _window(
        "daily", target.strftime("%Y-%m-%d"), target.isoformat(), target, target + timedelta(days=1)
    )


def period_tabs(selected_period: str) -> list[dict[str, str | bool]]:
    return [
        {"key": "daily", "selected": selected_period == "daily"},
        {"key": "weekly", "selected": selected_period == "weekly"},
        {"key": "monthly", "selected": selected_period == "monthly"},
        {"key": "yearly", "selected": selected_period == "yearly"},
    ]


def today_value(period: str) -> str:
    today = datetime.now().astimezone().date()
    if period == "weekly":
        return (today - timedelta(days=today.weekday())).isoformat()
    if period == "monthly":
        return today.strftime("%Y-%m")
    if period == "yearly":
        return str(today.year)
    return today.isoformat()


def drill_month_value(year_value: str) -> str:
    today = datetime.now().astimezone().date()
    year = _parse_year(year_value, today.year)
    month = today.month if year == today.year else 1
    return f"{year:04d}-{month:02d}"


def drill_week_value(month_value: str) -> str:
    today = datetime.now().astimezone().date()
    month_start = _parse_month(month_value, today)
    if month_start.year == today.year and month_start.month == today.month:
        target = today
    else:
        target = month_start
    return (target - timedelta(days=target.weekday())).isoformat()


def _window(
    key: str, title: str, selected_value: str, start_local: date, end_local: date
) -> PeriodWindow:
    start = _to_utc_string(datetime.combine(start_local, time.min).astimezone())
    end = _to_utc_string(datetime.combine(end_local, time.min).astimezone())
    return PeriodWindow(key, title, selected_value, start, end)


def _to_utc_string(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _parse_day(value: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat(value or fallback.isoformat())
    except ValueError:
        return fallback


def _parse_week(value: str | None, fallback: date) -> date:
    base = _parse_day(value, fallback)
    return base - timedelta(days=base.weekday())


def _parse_month(value: str | None, fallback: date) -> date:
    try:
        parsed = datetime.strptime(value or fallback.strftime("%Y-%m"), "%Y-%m")
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return date(fallback.year, fallback.month, 1)


def _parse_year(value: str | None, fallback: int) -> int:
    try:
        return int(value or str(fallback))
    except ValueError:
        return fallback
