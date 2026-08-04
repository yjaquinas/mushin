from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.routes.web.history import period
from app.routes.web.history import stats as history_stats


def test_all_history_uses_full_tag_set_and_paginates_filtered_rows(monkeypatch) -> None:
    rows = [
        {"id": 1, "occurred_at": "2026-08-04T10:00:00", "memo": "#run #outdoors"},
        {"id": 2, "occurred_at": "2026-08-03T10:00:00", "memo": "#read"},
        {"id": 3, "occurred_at": "2026-08-02T10:00:00", "memo": "#run"},
    ]
    monkeypatch.setattr(period.entries, "list_entries", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(period, "_decorate_comment_counts", lambda *_args: None)
    monkeypatch.setattr(history_stats.stats, "_today_local", lambda _tz: date(2026, 8, 4))

    history = period._build_history_context(
        7,
        3,
        period="all",
        anchor=date(2026, 8, 4),
        tz=ZoneInfo("UTC"),
        selected_tags=["run"],
        page=1,
        page_size=1,
    )

    assert history["total_count"] == 2
    assert history["total_pages"] == 2
    assert [entry["id"] for group in history["log"] for entry in group["entries"]] == [1]
    assert history_stats._build_history_tags(history, tz=ZoneInfo("UTC"))["tags"] == [
        {"name": "run", "total": 2, "this_period": 2, "last_period": 0, "delta": 2},
        {"name": "outdoors", "total": 1, "this_period": 1, "last_period": 0, "delta": 1},
        {"name": "read", "total": 1, "this_period": 1, "last_period": 0, "delta": 1},
    ]
