from zoneinfo import ZoneInfo

from app.services import entries


def test_resolve_occurred_at_prefers_submitted_utc_instant() -> None:
    occurred_at, time_known = entries.resolve_occurred_at(
        "2026-07-03",
        "09:30",
        tz=ZoneInfo("Asia/Seoul"),
        occurred_at_utc="2026-07-03T00:30:00.000Z",
    )

    assert occurred_at == "2026-07-03T00:30:00+00:00"
    assert time_known is True


def test_resolve_occurred_at_converts_local_fallback_to_utc() -> None:
    occurred_at, time_known = entries.resolve_occurred_at(
        "2026-07-03",
        "09:30",
        tz=ZoneInfo("Asia/Seoul"),
    )

    assert occurred_at == "2026-07-03T00:30:00+00:00"
    assert time_known is True


def test_resolve_occurred_at_date_only_uses_local_midnight_in_utc() -> None:
    occurred_at, time_known = entries.resolve_occurred_at(
        "2026-07-03",
        "",
        tz=ZoneInfo("Asia/Seoul"),
        occurred_at_utc="2026-07-02T15:00:00.000Z",
    )

    assert occurred_at == "2026-07-02T15:00:00+00:00"
    assert time_known is False
