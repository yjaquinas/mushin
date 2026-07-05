"""Visitor analytics read models for the admin dashboard."""

from __future__ import annotations

import sqlite3

from app.services.visitors import periods as visitor_periods, selectors as visitor_selectors

_PAGE_SIZE = 10


def dashboard_context(
    conn: sqlite3.Connection,
    *,
    period: str,
    selected_value: str | None,
    calendar_month: str | None,
    calendar_year: str | None,
    page: int,
) -> dict[str, object]:
    window = visitor_periods.period_window(period, selected_value)
    total_visitors = _visitor_count(conn, window)
    total_pages = max(1, (total_visitors + _PAGE_SIZE - 1) // _PAGE_SIZE)
    current_page = min(page, total_pages)
    return {
        "metrics": {
            "today": _unique_since(conn, "start of day"),
            "week": _unique_since(conn, "-6 days"),
            "month": _unique_since(conn, "-29 days"),
        },
        "selected_period": window.key,
        "selected_value": window.selected_value,
        "selected_page": current_page,
        "period_title": window.title,
        "period_tabs": visitor_periods.period_tabs(window.key),
        "today_value": visitor_periods.today_value(window.key),
        "drill_month_value": visitor_periods.drill_month_value(window.selected_value),
        "drill_week_value": visitor_periods.drill_week_value(window.selected_value)
        if window.key == "monthly"
        else None,
        "selector": visitor_selectors.selector_context(
            window.key,
            window.selected_value,
            calendar_month=calendar_month,
            calendar_year=calendar_year,
        ),
        "countries": _countries_for_window(conn, window),
        "referrers": _referrers_for_window(conn, window),
        "visitors": _recent_visitors(conn, window, current_page),
        "has_previous_page": current_page > 1,
        "has_next_page": current_page < total_pages,
        "total_pages": total_pages,
    }


def _unique_since(conn: sqlite3.Connection, modifier: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT visitor_key)
        FROM visitor_event
        WHERE last_seen_at >= datetime('now', ?)
        """,
        (modifier,),
    ).fetchone()
    return int(row[0] or 0)


def _countries_for_window(
    conn: sqlite3.Connection,
    window: visitor_periods.PeriodWindow,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT COALESCE(country_name, 'Unknown') AS country, COUNT(DISTINCT visitor_key) AS total
        FROM visitor_event
        WHERE last_seen_at >= ? AND last_seen_at < ?
        GROUP BY country
        ORDER BY total DESC, country ASC
        LIMIT 12
        """,
        (window.start_utc, window.end_utc),
    ).fetchall()


def _referrers_for_window(
    conn: sqlite3.Connection,
    window: visitor_periods.PeriodWindow,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT COALESCE(referrer_host, 'Direct / unknown') AS source,
               COUNT(DISTINCT visitor_key) AS total
        FROM visitor_event
        WHERE last_seen_at >= ? AND last_seen_at < ?
        GROUP BY source
        ORDER BY total DESC, source ASC
        LIMIT 12
        """,
        (window.start_utc, window.end_utc),
    ).fetchall()


def _recent_visitors(
    conn: sqlite3.Connection,
    window: visitor_periods.PeriodWindow,
    page: int,
) -> list[sqlite3.Row]:
    page_offset = (page - 1) * _PAGE_SIZE
    return conn.execute(
        """
        SELECT *,
            CASE
                WHEN city IS NOT NULL AND country_name IS NOT NULL THEN city || ', ' || country_name
                WHEN region IS NOT NULL AND country_name IS NOT NULL THEN region || ', ' || country_name
                WHEN country_name IS NOT NULL THEN country_name
                ELSE 'Unknown'
            END AS location_label
        FROM visitor_event
        WHERE last_seen_at >= ? AND last_seen_at < ?
        ORDER BY last_seen_at DESC
        LIMIT ? OFFSET ?
        """,
        (window.start_utc, window.end_utc, _PAGE_SIZE, page_offset),
    ).fetchall()


def _visitor_count(conn: sqlite3.Connection, window: visitor_periods.PeriodWindow) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM visitor_event
        WHERE last_seen_at >= ? AND last_seen_at < ?
        """,
        (window.start_utc, window.end_utc),
    ).fetchone()
    return int(row[0] or 0)
