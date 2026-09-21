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


def test_month_history_opens_the_page_containing_a_deep_linked_entry(monkeypatch) -> None:
    rows = [
        {"id": entry_id, "occurred_at": f"2026-08-{13 - entry_id:02d}T10:00:00"}
        for entry_id in range(1, 13)
    ]

    def period_entries(*_args, limit=None, offset=None, **_kwargs):
        if limit is None:
            return rows
        return rows[offset : offset + limit]

    monkeypatch.setattr(period.stats, "period_entries", period_entries)
    monkeypatch.setattr(period.entries, "count_entries", lambda *_args, **_kwargs: len(rows))
    monkeypatch.setattr(period, "_build_calendar_context", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(period, "_decorate_comment_counts", lambda *_args: None)

    history = period._build_history_context(
        7,
        3,
        period="month",
        anchor=date(2026, 8, 1),
        tz=ZoneInfo("UTC"),
        expand_comment_entry_id=11,
        page_size=10,
    )

    assert history["page"] == 2
    assert [entry["id"] for group in history["log"] for entry in group["entries"]] == [11, 12]


def test_month_history_filters_before_pagination_and_uses_full_month_for_tags(monkeypatch) -> None:
    rows = [
        {"id": entry_id, "occurred_at": f"2026-08-{13 - entry_id:02d}T10:00:00", "memo": "#run"}
        for entry_id in range(1, 11)
    ] + [
        {"id": 11, "occurred_at": "2026-08-02T10:00:00", "memo": "#read"},
        {"id": 12, "occurred_at": "2026-08-01T10:00:00", "memo": "#read #run"},
    ]

    def period_entries(*_args, limit=None, offset=None, **_kwargs):
        if limit is None:
            return rows
        return rows[offset : offset + limit]

    monkeypatch.setattr(period.stats, "period_entries", period_entries)
    monkeypatch.setattr(period.entries, "count_entries", lambda *_args, **_kwargs: len(rows))
    monkeypatch.setattr(period, "_build_calendar_context", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(period, "_decorate_comment_counts", lambda *_args: None)
    monkeypatch.setattr(history_stats.stats, "_today_local", lambda _tz: date(2026, 8, 12))

    history = period._build_history_context(
        7,
        3,
        period="month",
        anchor=date(2026, 8, 1),
        tz=ZoneInfo("UTC"),
        page=2,
        selected_tags=["read"],
    )

    assert [entry["id"] for group in history["log"] for entry in group["entries"]] == [11, 12]
    assert history["page"] == 1
    assert history["total_pages"] == 1
    assert history_stats._build_history_tags(history, tz=ZoneInfo("UTC"))["tags"] == [
        {"name": "run", "total": 11, "this_period": 11, "last_period": 0, "delta": 11},
        {"name": "read", "total": 2, "this_period": 2, "last_period": 0, "delta": 2},
    ]
