from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request

from app.models import db
from app.models.migrate import run_migrations
from app.routes.public.comments import handlers, reply_handlers
from app.services.entries import comments


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/@owner/run",
            "raw_path": b"/@owner/run",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "server": ("testserver", 443),
        }
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "comment-ui.db"
    run_migrations(path)
    with db.connect_to(path) as conn:
        conn.executemany(
            "INSERT INTO user (id, username, password_hash) VALUES (?, ?, 'hash')",
            [(1, "owner"), (2, "original"), (3, "viewer"), (4, "second")],
        )
        conn.execute("INSERT INTO activity (id, owner_id, name, slug) VALUES (1, 1, 'Run', 'run')")
        conn.execute(
            "INSERT INTO entry (id, owner_id, activity_id, occurred_at)"
            " VALUES (1, 1, 1, '2026-01-01T00:00:00+00:00')"
        )
    return path


async def test_reply_form_route_renders_for_top_level_comments_and_replies(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))
    monkeypatch.setattr(reply_handlers.sessions, "read_uid", lambda _session: 3)
    with db.connect_to(database_path) as conn:
        parent = comments.create_comment(conn, 1, 2, "Original")
        reply = comments.create_reply(conn, 1, parent["id"], 3, "Already replied")

    response = await reply_handlers.get_entry_comment_reply_form_body(
        _request(), "owner", "run", 1, parent["id"], False, None
    )
    body = response.body.decode()
    assert response.status_code == 200
    assert "Replying to @original" in body
    assert f"comments/{parent['id']}/replies" in body
    assert "data-comment-form" in body
    assert "comment_timezone" not in body

    nested_response = await reply_handlers.get_entry_comment_reply_form_body(
        _request(), "owner", "run", 1, reply["id"], False, None
    )
    assert nested_response.status_code == 200
    assert "Replying to @viewer" in nested_response.body.decode()


async def test_thread_groups_replies_and_shows_reply_controls_at_one_level(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))
    with db.connect_to(database_path) as conn:
        parent = comments.create_comment(conn, 1, 2, "Original")
        first = comments.create_reply(conn, 1, parent["id"], 3, "First reply")
        second = comments.create_reply(conn, 1, first["id"], 4, "Second reply")
        response = handlers._render_comment_thread(
            _request(),
            conn,
            username="owner",
            slug="run",
            owner_id=1,
            activity_id=1,
            entry_id=1,
            current_uid=3,
            user={"id": 1, "visibility": "public"},
        )
        body = response.body.decode()
        assert body.index("First reply") < body.index("Second reply")
        assert body.count('>Reply</span>') == 3
        assert f'id="comment-{first["id"]}"' in body
        assert f'id="comment-{second["id"]}"' in body
        assert "@original" in body
        assert "@viewer" in body
        assert '<span class="font-medium text-text-secondary">@viewer</span>' in body
        assert '<a href="/@viewer" class="font-medium text-accent-text' not in body
        assert '<a href="/@original"' in body

        comments.soft_delete_comment(conn, parent["id"], 2)
        deleted_response = handlers._render_comment_thread(
            _request(),
            conn,
            username="owner",
            slug="run",
            owner_id=1,
            activity_id=1,
            entry_id=1,
            current_uid=3,
            user={"id": 1, "visibility": "public"},
        )

    deleted_body = deleted_response.body.decode()
    assert "Comment deleted" in deleted_body
    assert '>Reply</span>' not in deleted_body


async def test_reply_submission_returns_refreshed_thread_fragment(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))
    monkeypatch.setattr(reply_handlers.sessions, "read_uid", lambda _session: 3)
    with db.connect_to(database_path) as conn:
        parent = comments.create_comment(conn, 1, 2, "Original")

    response = await reply_handlers.post_entry_comment_reply_body(
        _request(), "owner", "run", 1, parent["id"], "A new reply", "UTC", None
    )
    body = response.body.decode()
    assert response.status_code == 200
    assert 'id="comment-thread-1"' in body
    assert "A new reply" in body


async def test_entry_owner_hides_a_comment_and_the_thread_shows_attribution(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))
    monkeypatch.setattr(handlers.sessions, "read_uid", lambda _session: 1)
    with db.connect_to(database_path) as conn:
        comment = comments.create_comment(conn, 1, 2, "Hide this")
        before = handlers._render_comment_thread(
            _request(),
            conn,
            username="owner",
            slug="run",
            owner_id=1,
            activity_id=1,
            entry_id=1,
            current_uid=1,
            user={"id": 1, "visibility": "public"},
        ).body.decode()
        assert f'comments/{comment["id"]}/visibility' in before

    response = await handlers.hide_entry_comment_body(
        _request(), "owner", "run", 1, comment["id"], None
    )
    body = response.body.decode()

    assert response.status_code == 200
    assert "Hidden by owner" in body
    assert "Hide this" not in body
    assert f'comments/{comment["id"]}/visibility' in body
    assert ">Unhide</button>" in body

    restored_response = await handlers.unhide_entry_comment_body(
        _request(), "owner", "run", 1, comment["id"], None
    )
    restored_body = restored_response.body.decode()
    assert restored_response.status_code == 200
    assert "Hide this" in restored_body
    assert f'comments/{comment["id"]}/visibility' in restored_body
    assert ">Hide</button>" in restored_body
