from datetime import date
from zoneinfo import ZoneInfo

from app.routes.web._history_stats import _aggregate_memo_hashtags, _build_history_tags


def test_aggregate_memo_hashtags_counts_distinct_tags_per_entry() -> None:
    rows = [
        {"memo": "Run #easy #easy #outside", "occurred_at": "2026-07-02T00:00:00+00:00"},
        {"memo": "Lift #easy", "occurred_at": "2026-06-15T00:00:00+00:00"},
        {"memo": "Walk #outside", "occurred_at": "2026-05-20T00:00:00+00:00"},
        {"memo": "No tags here", "occurred_at": "2026-07-01T00:00:00+00:00"},
    ]

    result = _aggregate_memo_hashtags(
        rows,
        tz=ZoneInfo("UTC"),
        today=date(2026, 7, 3),
    )

    assert result == {
        "period": "month",
        "tags": [
            {
                "name": "easy",
                "total": 2,
                "this_period": 1,
                "last_period": 1,
                "delta": 0,
            },
            {
                "name": "outside",
                "total": 2,
                "this_period": 1,
                "last_period": 0,
                "delta": 1,
            },
        ],
    }


def test_aggregate_memo_hashtags_returns_none_when_absent() -> None:
    result = _aggregate_memo_hashtags(
        [{"memo": "plain memo", "occurred_at": "2026-07-02T00:00:00+00:00"}],
        tz=ZoneInfo("UTC"),
        today=date(2026, 7, 3),
    )

    assert result is None


def test_build_history_tags_uses_only_currently_visible_history_rows() -> None:
    history = {
        "selected_day": None,
        "log": [
            {
                "day": "2026-07-02",
                "entries": [
                    {"memo": "Run #easy", "occurred_at": "2026-07-02T00:00:00+00:00"},
                    {"memo": "Walk #outside", "occurred_at": "2026-07-02T01:00:00+00:00"},
                ],
            }
        ],
        "day_entries": [
            {"memo": "Ignored #other", "occurred_at": "2026-07-02T02:00:00+00:00"},
        ],
    }

    result = _build_history_tags(history, tz=ZoneInfo("UTC"))

    assert [tag["name"] for tag in result["tags"]] == ["easy", "outside"]
