"""History-log and field-stats context-assembly helpers for the ``web`` surface.

Split out from ``_contexts.py`` (route-structure rule, option 2 applied to a
non-route companion module) — these helpers are exclusively the detail
screen's stats/log assembly, a cohesive sub-concern of the broader
context-assembly module. The calendar-grid + comment-deep-link helpers
``_build_history_context`` itself depends on live in the sibling
``_calendar_context.py``, split out for the same reason.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app import ui_strings
from app.models import db
from app.routes.web._calendar_context import (
    _build_calendar_context,
    _entries_on_day,
    _heat_bucket,
)
from app.services import comments, entries, stats

_TAG_PERIOD_LABELS: dict[str, str] = {
    "week": ui_strings.TAG_FREQUENCY_THIS_WEEK,
    "month": ui_strings.TAG_FREQUENCY_THIS_MONTH,
    "year": ui_strings.TAG_FREQUENCY_THIS_YEAR,
}


def _decorate_comment_counts(
    log: list[dict[str, Any]], day_entries: list[dict[str, Any]] | None
) -> None:
    """Mutate ``log``'s and ``day_entries``' entry dicts in place, adding ``comment_count``.

    Opens its own connection — this module's other history helpers (e.g.
    ``entries.list_for_activity``, ``stats.period_entries``) already each open
    their own short-lived connection rather than share one with the caller, and
    no caller of ``_build_history_context`` holds a connection open across the
    call (both ``activity_detail`` callers explicitly close their connection
    first) — so opening one more short transaction here matches the existing
    pattern instead of threading a connection through every helper.
    """
    all_entries: list[dict[str, Any]] = [e for group in log for e in group["entries"]]
    if day_entries is not None:
        all_entries.extend(day_entries)
    if not all_entries:
        return
    entry_ids = [e["id"] for e in all_entries]
    with db.connect() as conn:
        conn.execute("BEGIN")
        counts = comments.counts_for_entries(conn, entry_ids)
    for e in all_entries:
        e["comment_count"] = counts.get(e["id"], 0)


def _build_history_context(
    activity_id: int,
    owner_id: int,
    *,
    period: str,
    anchor: date,
    tz: ZoneInfo,
    selected: date | None = None,
    is_owner: bool = False,
    can_comment: bool = False,
    username: str | None = None,
    slug: str | None = None,
    expand_comment_entry_id: int | None = None,
    login_redirect_url: str | None = None,
) -> dict[str, Any]:
    """History view context for *period* (``week``/``month``/``year``/``all``) at *anchor*.

    ``visual`` is shaped per period: a calendar grid (month), a single week of
    day-cells (week), or a bucketed heatmap series (year). For ``all``, there is
    no visual and no prev/next navigation — only the full day-grouped log.
    ``log`` groups the period's entries by local day (in *tz*), newest day first,
    for the chronological log.

    *selected*, when given (``week`` or ``month`` period — ``year``'s heatmap
    cells deliberately have no day-select), flags the matching cell/day and
    populates ``selected_day``/``day_entries`` with that day's detail.

    Every entry dict in ``log`` and ``day_entries`` carries a ``comment_count``
    key (via ``comments.counts_for_entries``), so a template can render the
    comment affordance without a separate per-entry lookup.

    *is_owner*, *can_comment*, *username*, *slug* are passed straight through
    into the returned context unchanged — this function does no capability
    checking of its own (that's the caller's job, via
    ``app/services/profiles.py``). *username*/*slug* are ``None`` when the
    activity has no public URL (e.g. a guest-owned account); pass ``None``
    faithfully rather than substituting a fallback — templates are responsible
    for suppressing comment affordances when either is ``None``.

    *expand_comment_entry_id*, when given, is a ``?c={entry_id}`` deep-link
    target (see ``_resolve_comment_deep_link``) — the caller is responsible
    for validating it belongs to this activity/owner and for setting
    *selected* to the day that contains it. Passed straight through into the
    returned context; ``components/day_entries.html.jinja2`` auto-expands the
    matching entry's comment slot on render when it equals an entry's id.

    *login_redirect_url*, when given, is an already-validated (via
    ``profiles.safe_next_path``) ``/login?next=...`` URL for an anonymous
    viewer who can read this activity but can't comment (``can_comment`` is
    ``False`` precisely because there's no session — see
    ``profiles.can_comment_on_entry``). Passed straight through; the caller
    is responsible for only ever constructing it on the already-capability-
    cleared read-only path, never for a blocked/limited viewer (who never
    reaches this function at all).
    """
    if period == "all":
        all_rows = entries.list_for_activity(owner_id, activity_id)
        by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for row in all_rows:
            by_day[entries._local_day(row["occurred_at"], tz)].append(row)
        log = [
            {"day": day.isoformat(), "entries": day_entries}
            for day, day_entries in sorted(by_day.items(), reverse=True)
        ]
        _decorate_comment_counts(log, None)
        return {
            "period": "all",
            "anchor": anchor.isoformat(),
            "label": None,
            "visual": None,
            "log": log,
            "prev_anchor": None,
            "next_anchor": None,
            "start": None,
            "end": None,
            "selected_day": None,
            "day_entries": None,
            "is_owner": is_owner,
            "can_comment": can_comment,
            "username": username,
            "slug": slug,
            "expand_comment_entry_id": expand_comment_entry_id,
            "login_redirect_url": login_redirect_url,
        }

    start = stats._shift_period(anchor, period, 0)
    end = stats._shift_period(anchor, period, 1) - timedelta(days=1)
    today = datetime.now(UTC).date()

    if period == "month":
        visual: dict[str, Any] = _build_calendar_context(
            activity_id,
            owner_id,
            year=start.year,
            month=start.month,
            tz=tz,
            selected=selected,
        )
        label = f"{start.year}.{start.month:02d}"
    elif period == "week":
        series = stats.heatmap_range(activity_id, owner_id, start, end, tz=tz)
        marked_days = {date.fromisoformat(d["date"]) for d in series if d["count"] > 0}
        days_cells = []
        cursor = start
        while cursor <= end:
            days_cells.append(
                {
                    "date": cursor.isoformat(),
                    "day": cursor.day,
                    "marked": cursor in marked_days,
                    "today": cursor == today,
                    "selected": cursor == selected,
                }
            )
            cursor += timedelta(days=1)
        visual = {"days": days_cells}
        label = f"{start.isoformat()} – {end.isoformat()}"
    elif period == "year":
        series = stats.heatmap_range(activity_id, owner_id, start, end, tz=tz)
        year_rows = 14
        cells = []
        prev_month: int | None = None
        for d in series:
            day = date.fromisoformat(d["date"])
            is_first_of_month = day.month != prev_month
            prev_month = day.month
            cells.append(
                {
                    "date": d["date"],
                    "bucket": _heat_bucket(d["count"]),
                    "month": day.month,
                    "is_first_of_month": is_first_of_month,
                }
            )
        # One entry per grid column (cells pack column-major, `year_rows`
        # per column — see grid-rows-14 in history.html.jinja2), so the
        # label strip above the grid can align 1:1 by column index rather
        # than by day. A column is a "month start" if any of its cells is
        # the first day of its month; only sparse (quarterly) months get
        # text, but every month-start column gets a boundary flag so the
        # template can draw a divider even where there's no label.
        month_columns = []
        for col_start in range(0, len(cells), year_rows):
            col_cells = cells[col_start : col_start + year_rows]
            month_start_cell = next((c for c in col_cells if c["is_first_of_month"]), None)
            is_month_start_column = month_start_cell is not None
            month_columns.append(
                {
                    "is_month_start": is_month_start_column,
                    "month": month_start_cell["month"] if month_start_cell else None,
                }
            )
            # The divider border reads as a full-column rule, not a tick
            # mark mid-column, so every cell in a month-start column gets
            # the boundary flag — not just the single day that's the 1st
            # (which can land anywhere within its 14-day column).
            for c in col_cells:
                c["is_month_start_column"] = is_month_start_column
        visual = {"cells": cells, "month_columns": month_columns, "year_rows": year_rows}
        label = f"{start.year}"
    else:
        raise ValueError(f"unknown period {period!r}; expected week/month/year/all")

    period_rows = stats.period_entries(activity_id, owner_id, start, end, tz=tz)
    by_day = defaultdict(list)
    for row in period_rows:
        by_day[entries._local_day(row["occurred_at"], tz)].append(row)

    log = [
        {"day": day.isoformat(), "entries": day_entries}
        for day, day_entries in sorted(by_day.items(), reverse=True)
    ]

    prev_anchor = stats._shift_period(anchor, period, -1).isoformat()
    next_anchor = stats._shift_period(anchor, period, 1).isoformat()

    selected_day = selected.isoformat() if selected is not None else None
    day_entries = (
        _entries_on_day(activity_id, owner_id, selected, tz=tz) if selected is not None else None
    )

    _decorate_comment_counts(log, day_entries)

    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "label": label,
        "visual": visual,
        "log": log,
        "prev_anchor": prev_anchor,
        "next_anchor": next_anchor,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "selected_day": selected_day,
        "day_entries": day_entries,
        "is_owner": is_owner,
        "can_comment": can_comment,
        "username": username,
        "slug": slug,
        "expand_comment_entry_id": expand_comment_entry_id,
        "login_redirect_url": login_redirect_url,
    }


def _build_field_stats_context(
    activity_id: int,
    owner_id: int,
    field_defs: list[sqlite3.Row],
    *,
    tz: ZoneInfo,
    period: str = "month",
) -> dict[str, Any]:
    """Tag-frequency and scale-distribution sections for the fields that exist."""
    tag_groups = []
    scales = []
    for fd in field_defs:
        if fd["kind"] == "tag_group":
            freq = stats.tag_frequency(activity_id, owner_id, fd["id"], tz=tz, period=period)
            tag_groups.append({"label": fd["label"], "tags": freq["tags"]})
        elif fd["kind"] == "scale":
            dist = stats.scale_distribution(activity_id, owner_id, fd["id"])
            scales.append({"label": fd["label"], **dist})
    return {
        "tag_groups": tag_groups,
        "scales": scales,
        "period": period,
        "period_label": _TAG_PERIOD_LABELS.get(period, ui_strings.TAG_FREQUENCY_THIS_MONTH),
    }
