"""History period rendering helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.routes.web._calendar_context import _build_calendar_context, _entries_on_day
from app.services import comments, entries, stats


def _build_history_context(activity_id: int, owner_id: int, *, period: str, anchor: date, tz: ZoneInfo, selected: date | None = None, is_owner: bool = False, can_comment: bool = False, username: str | None = None, slug: str | None = None, expand_comment_entry_id: int | None = None, login_redirect_url: str | None = None) -> dict[str, Any]:
    if period == "all":
        log = _group_log(entries.list_for_activity(owner_id, activity_id), tz)
        _decorate_comment_counts(log, None)
        return {"period": "all", "anchor": anchor.isoformat(), "today_anchor": datetime.now(UTC).date().isoformat(), "label": None, "visual": None, "log": log, "prev_anchor": None, "next_anchor": None, "start": None, "end": None, "selected_day": None, "day_entries": None, "is_owner": is_owner, "can_comment": can_comment, "username": username, "slug": slug, "expand_comment_entry_id": expand_comment_entry_id, "login_redirect_url": login_redirect_url}
    start = stats._shift_period(anchor, period, 0)
    end = stats._shift_period(anchor, period, 1) - timedelta(days=1)
    today = datetime.now(UTC).date()
    visual, label = _period_visual(period, activity_id, owner_id, start, end, tz, selected, today)
    log = _group_log(stats.period_entries(activity_id, owner_id, start, end, tz=tz), tz)
    day_entries = _entries_on_day(activity_id, owner_id, selected, tz=tz) if selected is not None else None
    _decorate_comment_counts(log, day_entries)
    return {"period": period, "anchor": anchor.isoformat(), "today_anchor": today.isoformat(), "label": label, "visual": visual, "log": log, "prev_anchor": stats._shift_period(anchor, period, -1).isoformat(), "next_anchor": stats._shift_period(anchor, period, 1).isoformat(), "start": start.isoformat(), "end": end.isoformat(), "selected_day": selected.isoformat() if selected is not None else None, "day_entries": day_entries, "is_owner": is_owner, "can_comment": can_comment, "username": username, "slug": slug, "expand_comment_entry_id": expand_comment_entry_id, "login_redirect_url": login_redirect_url}


def _group_log(rows: list[dict[str, Any]], tz: ZoneInfo) -> list[dict[str, Any]]:
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[entries._local_day(row["occurred_at"], tz)].append(row)
    return [{"day": day.isoformat(), "entries": day_entries} for day, day_entries in sorted(by_day.items(), reverse=True)]


def _period_visual(period: str, activity_id: int, owner_id: int, start: date, end: date, tz: ZoneInfo, selected: date | None, today: date) -> tuple[dict[str, Any], str]:
    if period == "month":
        return _build_calendar_context(activity_id, owner_id, year=start.year, month=start.month, tz=tz, selected=selected), f"{start.year}.{start.month:02d}"
    if period == "week":
        marked_days = {date.fromisoformat(d["date"]) for d in stats.heatmap_range(activity_id, owner_id, start, end, tz=tz) if d["count"] > 0}
        days, cursor = [], start
        while cursor <= end:
            days.append({"date": cursor.isoformat(), "day": cursor.day, "marked": cursor in marked_days, "today": cursor == today, "selected": cursor == selected})
            cursor += timedelta(days=1)
        return {"days": days}, f"{start.isoformat()} – {end.isoformat()}"
    raise ValueError(f"unknown period {period!r}; expected week/month/all")


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

