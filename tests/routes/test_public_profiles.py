from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import Request
from fastapi.responses import HTMLResponse

from app.routes.public.activity import routes as activity_routes
from app.routes.public.profile import routes as profile_routes
from app.routes.web.home import routes as home_routes


class _Connection:
    def execute(self, _query: str, _params: tuple[object, ...] = ()) -> _Connection:
        return self

    def fetchone(self) -> dict[str, int]:
        return {"secret": 0}


@contextmanager
def _connection():
    yield _Connection()


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"host", b"mushin.aqnas.xyz")],
            "server": ("mushin.aqnas.xyz", 443),
        }
    )


def _profile_context(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "username": "public-user",
        "view_mode": "public",
        "cards": [],
        "fellows": {"is_owner": False, "pending_count": 0, "fellow_count": 0, "fellows": []},
        "state": "none",
        "viewer_logged_in": False,
        "bio": "",
    }


async def test_public_profile_is_crawlable_at_its_canonical_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profile_routes.sessions, "read_uid", lambda _session: None)
    monkeypatch.setattr(profile_routes.db, "connect", _connection)
    monkeypatch.setattr(
        profile_routes.profiles,
        "get_public_user",
        lambda *_args: {"id": 1, "visibility": "public", "bio": ""},
    )
    monkeypatch.setattr(profile_routes.profiles, "viewer_capability", lambda *_args, **_kwargs: "public")
    monkeypatch.setattr(profile_routes.users, "get_user_timezone", lambda _owner_id: None)
    monkeypatch.setattr(profile_routes, "read_only_profile_context", _profile_context)

    response = await profile_routes.profile(_request("/@public-user"), "public-user")

    assert response.status_code == 200
    body = response.body.decode()
    assert '<link rel="canonical" href="https://mushin.aqnas.xyz/@public-user">' in body
    assert '<meta name="robots" content="index, follow">' in body


async def test_private_activity_redirects_to_the_canonical_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_routes.sessions, "read_uid", lambda _session: None)
    monkeypatch.setattr(activity_routes.db, "connect", _connection)
    monkeypatch.setattr(
        activity_routes.profiles,
        "get_public_user",
        lambda *_args: {"id": 1, "visibility": "private"},
    )
    monkeypatch.setattr(activity_routes.profiles, "resolve_activity_slug", lambda *_args: 7)
    monkeypatch.setattr(activity_routes.profiles, "viewer_capability", lambda *_args, **_kwargs: "limited")
    monkeypatch.setattr(activity_routes.profiles, "can_view_activity_detail", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(activity_routes.users, "get_user_timezone", lambda _owner_id: None)

    response = await activity_routes.public_activity(_request("/@private-user/reading"), "private-user", "reading")

    assert response.status_code == 303
    assert response.headers["location"] == "/@private-user"


async def test_private_profile_is_not_indexable_and_does_not_link_to_activity_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profile_routes.sessions, "read_uid", lambda _session: None)
    monkeypatch.setattr(profile_routes.db, "connect", _connection)
    monkeypatch.setattr(
        profile_routes.profiles,
        "get_public_user",
        lambda *_args: {"id": 1, "visibility": "private", "bio": ""},
    )
    monkeypatch.setattr(profile_routes.profiles, "viewer_capability", lambda *_args, **_kwargs: "limited")
    monkeypatch.setattr(profile_routes.users, "get_user_timezone", lambda _owner_id: None)
    monkeypatch.setattr(
        profile_routes,
        "read_only_profile_context",
        lambda *_args, **_kwargs: {
            **_profile_context(),
            "username": "private-user",
            "view_mode": "limited",
            "cards": [
                {
                    "name": "Reading",
                    "slug": "reading",
                    "linked": False,
                    "counts": {"lifetime": 8},
                }
            ],
        },
    )

    response = await profile_routes.profile(_request("/@private-user"), "private-user")

    body = response.body.decode()
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in body
    assert "Reading" in body
    assert "/@private-user/reading" not in body


async def test_public_activity_uses_a_self_referential_canonical_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_routes.sessions, "read_uid", lambda _session: None)
    monkeypatch.setattr(activity_routes.db, "connect", _connection)
    monkeypatch.setattr(
        activity_routes.profiles,
        "get_public_user",
        lambda *_args: {"id": 1, "visibility": "public"},
    )
    monkeypatch.setattr(activity_routes.profiles, "resolve_activity_slug", lambda *_args: 7)
    monkeypatch.setattr(activity_routes.profiles, "viewer_capability", lambda *_args, **_kwargs: "public")
    monkeypatch.setattr(activity_routes.profiles, "can_view_activity_detail", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(activity_routes.users, "get_user_timezone", lambda _owner_id: None)

    def render_public_activity(request: Request, *_args: object, **_kwargs: object) -> HTMLResponse:
        return HTMLResponse(
            f'<link rel="canonical" href="{request.url}"><meta name="robots" content="index, follow">'
        )

    monkeypatch.setattr(activity_routes, "_render_readonly_activity_detail", render_public_activity)

    response = await activity_routes.public_activity(_request("/@public-user/reading"), "public-user", "reading")

    assert response.status_code == 200
    assert 'href="https://mushin.aqnas.xyz/@public-user/reading"' in response.body.decode()


async def test_robots_txt_uses_the_production_sitemap() -> None:
    response = await home_routes.robots_txt()

    assert response.body.decode().splitlines()[-1] == "Sitemap: https://mushin.aqnas.xyz/sitemap.xml"
