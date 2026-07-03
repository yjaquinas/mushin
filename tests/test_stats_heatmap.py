from datetime import date

from app.services import stats


def test_heatmap_quarter_labels_are_once_per_calendar_quarter() -> None:
    heatmap = stats._build_heatmap_weeks(date(2026, 1, 1), date(2026, 12, 31), {})

    labels = [
        (index, week["quarter_month"])
        for index, week in enumerate(heatmap)
        if week["quarter_month"]
    ]

    assert labels == [(0, 1), (12, 4), (25, 7), (39, 10)]
    assert len(heatmap) == 53
