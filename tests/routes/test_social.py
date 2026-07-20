from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import Request

from app.routes.web.social import routes


class _SecretActivityConnection:
    def execute(self, _query: str, _params: tuple[int, ...] = ()) -> _SecretActivityConnection:
        return self

    def fetchone(self) -> dict[str, int]:
        return {"secret": 0}


@contextmanager
def _connection():
    yield _SecretActivityConnection()


def _request(query_string: bytes = b"") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/social/@aqnas/reading",
            "raw_path": b"/social/@aqnas/reading",
            "query_string": query_string,
            "headers": [],
            "server": ("testserver", 80),
        }
    )


@pytest.mark.parametrize(
    ("query_string", "location"),
    [
        (b"entry_id=29", "/@aqnas/reading?entry_id=29"),
        (b"", "/@aqnas/reading"),
    ],
)
async def test_owner_social_activity_redirect_preserves_query_string(
    monkeypatch: pytest.MonkeyPatch, query_string: bytes, location: str
) -> None:
    monkeypatch.setattr(routes.sessions, "read_uid", lambda _session: 1)
    monkeypatch.setattr(routes.db, "connect", _connection)
    monkeypatch.setattr(routes.profiles, "get_public_user", lambda *_args: {"id": 1})
    monkeypatch.setattr(routes.profiles, "resolve_activity_slug", lambda *_args: 7)
    monkeypatch.setattr(routes.profiles, "viewer_capability", lambda *_args, **_kwargs: "owner")

    response = await routes.social_activity(_request(query_string), "aqnas", "reading")

    assert response.status_code == 303
    assert response.headers["location"] == location
