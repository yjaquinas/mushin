"""Tag and field stats helpers for history/detail views."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from app import ui_strings
from app.services import entries, stats


def _build_card_top_tags(
    activity_id: int,
    owner_id: int,
    field_defs: list[sqlite3.Row],
    *,
    tz: ZoneInfo,
    top: int | None = None,
) -> dict[str, Any] | None:
    """Build hashtag stats from entry memos for an activity detail view."""
    rows = entries.list_entries(owner_id, activity_id, tz=tz)
    return _aggregate_memo_hashtags(rows, tz=tz, top=top)


def _aggregate_memo_hashtags(
    rows: list[dict[str, Any]], *, tz: ZoneInfo, top: int | None = None, today: date | None = None
) -> dict[str, Any] | None:
    """Aggregate ``#tag`` usage from entry memos.

    Counts each distinct hashtag at most once per entry, so repeated mentions of
    the same tag inside one memo do not inflate totals.
    """
    if today is None:
        today = stats._today_local(tz)
    this_start, last_start, this_end = stats._period_bounds(today, "month")

    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"name": "", "total": 0, "this_period": 0, "last_period": 0}
    )
    for row in rows:
        memo = str(row.get("memo") or "")
        tags = set(entries.parse_hashtags(memo))
        if not tags:
            continue
        local_day = entries._local_day(row["occurred_at"], tz)
        for tag in tags:
            item = agg[tag]
            item["name"] = tag
            item["total"] += 1
            if this_start <= local_day < this_end:
                item["this_period"] += 1
            elif last_start <= local_day < this_start:
                item["last_period"] += 1

    if not agg:
        return None

    tags = sorted(agg.values(), key=lambda item: (-item["total"], item["name"]))
    for item in tags:
        item["delta"] = item["this_period"] - item["last_period"]
    if top is not None:
        tags = tags[:top]
    return {"period": "month", "tags": tags}


def _build_history_tags(history: dict[str, Any], *, tz: ZoneInfo) -> dict[str, Any] | None:
    """Aggregate hashtags for the entries currently shown by a history view."""
    if history.get("selected_day") is not None:
        rows = history.get("day_entries") or []
    else:
        rows = [entry for group in history.get("log", []) for entry in group.get("entries", [])]
    return _aggregate_memo_hashtags(rows, tz=tz)


def _build_field_stats_context(activity_id: int, owner_id: int, field_defs: list[sqlite3.Row], *, tz: ZoneInfo, period: str = "month") -> dict[str, Any]:
    """No-op: field system removed."""
    return {"tag_groups": [], "scales": [], "period": period, "period_label": ui_strings.TAG_FREQUENCY_THIS_MONTH}
