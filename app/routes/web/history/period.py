"""History period rendering helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.routes.web.history.calendar import _build_calendar_context
from app.services.entries import comments, entries, stats


def _build_history_context(activity_id: int, owner_id: int, *, period: str, anchor: date, tz: ZoneInfo, is_owner: bool = False, can_comment: bool = False, username: str | None = None, slug: str | None = None, expand_comment_entry_id: int | None = None, login_redirect_url: str | None = None, tag: str | None = None, selected_day: date | None = None, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    _PAGE_SIZE = page_size
    today = datetime.now(UTC).date()
    day_entries: list[dict[str, Any]] = []

    if period == "all":
        total_count = entries.count_entries(owner_id, activity_id)
        rows = entries.list_entries(owner_id, activity_id, tz=tz, limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE)
        selected_day = None
    elif selected_day is not None:
        start = stats._shift_period(anchor, period, 0)
        end = stats._shift_period(anchor, period, 1) - timedelta(days=1)
        day_entries = entries.list_entries_by_day(owner_id, activity_id, selected_day, tz=tz)
        total_count = len(day_entries)
        rows = []
        visual, label = _period_visual(period, activity_id, owner_id, start, end, tz, selected_day, today)
    else:
        start = stats._shift_period(anchor, period, 0)
        end = stats._shift_period(anchor, period, 1) - timedelta(days=1)
        total_count = entries.count_entries(owner_id, activity_id, start=start, end=end)
        rows = stats.period_entries(activity_id, owner_id, start, end, tz=tz, limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE)
        visual, label = _period_visual(period, activity_id, owner_id, start, end, tz, None, today)

    total_pages = max(1, (total_count + _PAGE_SIZE - 1) // _PAGE_SIZE)
    log = _group_log(rows, tz)
    _decorate_comment_counts(log, day_entries)

    base = {
        "period": period,
        "anchor": anchor.isoformat(),
        "today_anchor": today.isoformat(),
        "log": log,
        "is_owner": is_owner,
        "can_comment": can_comment,
        "username": username,
        "slug": slug,
        "expand_comment_entry_id": expand_comment_entry_id if period != "all" else None,
        "login_redirect_url": login_redirect_url,
        "selected_day": selected_day.isoformat() if selected_day is not None else None,
        "selected_day_label": selected_day.strftime("%a, %b %-d, %Y") if selected_day is not None else None,
        "day_entries": day_entries,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "page_range": _page_range(page, total_pages),
    }

    if period == "all":
        base.update({"label": None, "visual": None, "prev_anchor": None, "next_anchor": None, "start": None, "end": None})
    else:
        base.update({"label": label, "visual": visual, "prev_anchor": stats._shift_period(anchor, period, -1).isoformat(), "next_anchor": stats._shift_period(anchor, period, 1).isoformat(), "start": start.isoformat(), "end": end.isoformat()})
    return base


def _group_log(rows: list[dict[str, Any]], tz: ZoneInfo) -> list[dict[str, Any]]:
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[entries._local_day(row["occurred_at"], tz)].append(row)
    return [{"day": day.isoformat(), "entries": day_entries} for day, day_entries in sorted(by_day.items(), reverse=True)]


def _period_visual(period: str, activity_id: int, owner_id: int, start: date, end: date, tz: ZoneInfo, selected: date | None, today: date) -> tuple[dict[str, Any], str]:
    if period == "month":
        return _build_calendar_context(activity_id, owner_id, year=start.year, month=start.month, tz=tz, selected=selected), f"{start.year}-{start.month:02d}"
    raise ValueError(f"unknown period {period!r}; expected month/all")


def _decorate_comment_counts(log: list[dict[str, Any]], day_entries: list[dict[str, Any]] | None) -> None:
    all_entries = [e for group in log for e in group["entries"]]
    if day_entries is not None:
        all_entries.extend(day_entries)
    if not all_entries:
        return
    with db.connect() as conn:
        conn.execute("BEGIN")
        counts = comments.counts_for_entries(conn, [e["id"] for e in all_entries])
    for e in all_entries:
        e["comment_count"] = counts.get(e["id"], 0)


def _page_range(current: int, total: int, window: int = 5) -> list[int | None]:
    """Return page numbers for pagination, with ``None`` for ellipsis gaps."""
    if total <= window:
        return list(range(1, total + 1))
    half = window // 2
    start = max(1, current - half)
    end = min(total, start + window - 1)
    start = max(1, end - window + 1)
    pages: list[int | None] = []
    if start > 1:
        pages.append(1)
        if start > 2:
            pages.append(None)
    for p in range(start, end + 1):
        pages.append(p)
    if end < total:
        if end < total - 1:
            pages.append(None)
        pages.append(total)
    return pages
