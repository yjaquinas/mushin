"""Tag and field stats helpers for history/detail views."""

from __future__ import annotations

import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app import ui_strings
from app.services import stats

_TAG_PERIOD_LABELS: dict[str, str] = {
    "week": ui_strings.TAG_FREQUENCY_THIS_WEEK,
    "month": ui_strings.TAG_FREQUENCY_THIS_MONTH,
    "year": ui_strings.TAG_FREQUENCY_THIS_YEAR,
}


def _build_card_top_tags(activity_id: int, owner_id: int, field_defs: list[sqlite3.Row], *, tz: ZoneInfo, top: int = 3) -> dict[str, Any] | None:
    tag_group_fields = [fd for fd in field_defs if fd["kind"] == "tag_group"]
    if not tag_group_fields:
        return None
    fd = min(tag_group_fields, key=lambda f: (f["sort_order"], f["id"]))
    freq = stats.tag_frequency(activity_id, owner_id, fd["id"], tz=tz, period="month", top=top)
    return {"label": fd["label"], "tags": freq["tags"]}


def _build_field_stats_context(activity_id: int, owner_id: int, field_defs: list[sqlite3.Row], *, tz: ZoneInfo, period: str = "month") -> dict[str, Any]:
    tag_groups, scales = [], []
    for fd in field_defs:
        if fd["kind"] == "tag_group":
            tag_groups.append({"label": fd["label"], "tags": stats.tag_frequency(activity_id, owner_id, fd["id"], tz=tz, period=period)["tags"]})
        elif fd["kind"] == "scale":
            scales.append({"label": fd["label"], **stats.scale_distribution(activity_id, owner_id, fd["id"])})
    return {"tag_groups": tag_groups, "scales": scales, "period": period, "period_label": _TAG_PERIOD_LABELS.get(period, ui_strings.TAG_FREQUENCY_THIS_MONTH)}

