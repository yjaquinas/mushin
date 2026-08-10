from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from fastapi import Request

from app.routes.public.activity import handlers
from app.routes.web.history import calendar


def _request(entry_id: str | None = None) -> Request:
    query_string = f"entry_id={entry_id}".encode() if entry_id else b""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/@owner/activity",
            "query_string": query_string,
            "headers": [(b"host", b"mushin.test")],
            "server": ("mushin.test", 443),
        }
    )


def test_comment_deep_link_returns_the_scoped_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = {"id": 37, "owner_id": 2, "activity_id": 4, "occurred_at": "2026-05-03T08:00:00+09:00"}
    monkeypatch.setattr(calendar.entries, "get", lambda *_args: entry)

    assert calendar._resolve_comment_deep_link("37", activity_id=4, owner_id=2) == entry
    assert calendar._resolve_comment_deep_link("37", activity_id=5, owner_id=2) is None


def test_deep_link_history_uses_the_target_entry_month(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handlers,
        "_resolve_comment_deep_link",
        lambda *_args, **_kwargs: {"id": 37, "occurred_at": "2026-05-03T08:00:00+09:00"},
    )

    entry_id, anchor = handlers._comment_deep_link_state(
        _request("37"),
        activity_id=4,
        owner_id=2,
        tz=ZoneInfo("Asia/Seoul"),
        today=date(2026, 8, 9),
    )

    assert entry_id == 37
    assert anchor == date(2026, 5, 3)


def test_missing_deep_link_keeps_the_current_month() -> None:
    entry_id, anchor = handlers._comment_deep_link_state(
        _request(),
        activity_id=4,
        owner_id=2,
        tz=ZoneInfo("Asia/Seoul"),
        today=date(2026, 8, 9),
    )

    assert entry_id is None
    assert anchor == date(2026, 8, 9)
