from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.models import db, migrate
from app.models.migrate import run_migrations
from app.services.entries import comments
from app.services.social import notifications


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO user (id, username, password_hash) VALUES (?, ?, 'hash')",
        [(1, "owner"), (2, "original"), (3, "first"), (4, "second"), (5, "other")],
    )
    conn.execute("INSERT INTO activity (id, owner_id, name, slug) VALUES (1, 1, 'Run', 'run')")
    conn.executemany(
        "INSERT INTO entry (id, owner_id, activity_id, occurred_at) VALUES (?, ?, 1, '2026-01-01T00:00:00+00:00')",
        [(1, 1), (2, 5)],
    )


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "comment-replies.db"
    run_migrations(path)
    with db.connect_to(path) as connection:
        _seed(connection)
        yield connection


def test_replies_group_in_order_count_and_deleted_parent_placeholder(conn) -> None:
    parent = comments.create_comment(conn, 1, 2, "Parent")
    first = comments.create_reply(conn, 1, parent["id"], 3, "First")
    second = comments.create_reply(conn, 1, parent["id"], 4, "Second")

    threads = comments.list_comments(conn, 1, viewer_id=1)
    assert [thread["id"] for thread in threads] == [parent["id"]]
    assert [reply["id"] for reply in threads[0]["replies"]] == [first["id"], second["id"]]
    assert comments.counts_for_entries(conn, [1]) == {1: 3}

    comments.soft_delete_comment(conn, parent["id"], 2)
    thread = comments.list_comments(conn, 1, viewer_id=1)[0]
    assert thread["deleted_at"] is not None
    assert [reply["id"] for reply in thread["replies"]] == [first["id"], second["id"]]
    with pytest.raises(comments.CommentNotFoundError):
        comments.create_reply(conn, 1, parent["id"], 3, "No more")


def test_reply_to_a_reply_stays_in_the_original_thread_and_targets_its_author(conn) -> None:
    parent = comments.create_comment(conn, 1, 2, "Parent")
    reply = comments.create_reply(conn, 1, parent["id"], 3, "Reply")
    targeted_reply = comments.create_reply(conn, 1, reply["id"], 4, "Targeted reply")
    rows = comments.list_comments(conn, 1, viewer_id=1)
    assert [item["id"] for item in rows[0]["replies"]] == [reply["id"], targeted_reply["id"]]
    assert targeted_reply["parent_comment_id"] == parent["id"]
    assert targeted_reply["reply_to_comment_id"] == reply["id"]
    assert rows[0]["replies"][1]["reply_to_author_username"] == "first"
    with pytest.raises(comments.CommentNotFoundError):
        comments.create_reply(conn, 2, parent["id"], 4, "Cross entry")


def test_entry_owner_can_hide_a_comment_with_attribution(conn) -> None:
    comment = comments.create_comment(conn, 1, 2, "Keep this private")

    with pytest.raises(comments.CommentPermissionError):
        comments.hide_comment(conn, 1, comment["id"], requester_id=2)

    comments.hide_comment(conn, 1, comment["id"], requester_id=1)

    row = comments.list_comments(conn, 1, viewer_id=3)[0]
    assert row["body"] == "Keep this private"
    assert row["hidden_at"] is not None
    assert row["hidden_by_id"] == 1
    assert row["hidden_by_username"] == "owner"
    with pytest.raises(comments.CommentNotFoundError):
        comments.create_reply(conn, 1, comment["id"], 3, "Reply to hidden")
    with pytest.raises(comments.CommentNotFoundError):
        comments.hide_comment(conn, 1, comment["id"], requester_id=2)

    comments.unhide_comment(conn, 1, comment["id"], requester_id=1)
    restored = comments.list_comments(conn, 1, viewer_id=3)[0]
    assert restored["hidden_at"] is None
    assert restored["hidden_by_id"] is None


def test_reply_notifications_aggregate_and_fan_out(conn) -> None:
    parent = comments.create_comment(conn, 1, 2, "Parent")
    comments.create_reply(conn, 1, parent["id"], 3, "First")
    original = conn.execute(
        "SELECT * FROM notification WHERE user_id = 2 AND type = 'comment_reply'"
    ).fetchone()
    assert original["actor_id"] == 3
    assert original["read_at"] is None
    conn.execute("UPDATE notification SET read_at = '2026-01-02T00:00:00+00:00' WHERE id = ?", (original["id"],))

    comments.create_reply(conn, 1, parent["id"], 4, "Second")
    grouped = conn.execute(
        "SELECT * FROM notification WHERE user_id = 2 AND type = 'comment_reply'"
    ).fetchall()
    assert len(grouped) == 1
    assert grouped[0]["actor_id"] == 4
    assert grouped[0]["read_at"] is None
    participant = conn.execute(
        "SELECT * FROM notification WHERE user_id = 3 AND type = 'comment_reply_participant'"
    ).fetchall()
    assert len(participant) == 1
    assert participant[0]["actor_id"] == 4
    assert conn.execute(
        "SELECT COUNT(*) FROM notification WHERE user_id = 4"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM notification WHERE type = 'comment' AND entry_id = 1"
    ).fetchone()[0] == 1


def test_reply_notification_target_uses_root_comment(conn) -> None:
    parent = comments.create_comment(conn, 1, 2, "Parent")
    comments.create_reply(conn, 1, parent["id"], 3, "Reply")
    row = notifications.list_notifications(conn, 2, username="original")[0]
    assert row["target_url"].endswith(f"?entry_id=1#comment-{parent['id']}")


def test_comment_notification_targets_the_new_comment(conn) -> None:
    comment = comments.create_comment(conn, 1, 2, "Comment")
    row = notifications.list_notifications(conn, 1, username="owner")[0]
    assert row["target_url"].endswith(f"?entry_id=1#comment-{comment['id']}")


def test_comment_notification_previews_are_compact_and_persisted(conn) -> None:
    body = "one two three four five six seven eight nine ten eleven twelve thirteen"
    comment = comments.create_comment(conn, 1, 2, body)

    stored = conn.execute(
        "SELECT comment_preview FROM notification WHERE comment_id = ?", (comment["id"],)
    ).fetchone()
    assert stored["comment_preview"] == "one two three four five six seven eight nine ten eleven twelve…"
    row = notifications.list_notifications(conn, 1, username="owner")[0]
    assert row["comment_preview"] == stored["comment_preview"]

    comments.soft_delete_comment(conn, comment["id"], 2)
    row = notifications.list_notifications(conn, 1, username="owner")[0]
    assert row["comment_preview"] == stored["comment_preview"]


def test_reply_notification_preview_tracks_the_latest_reply(conn) -> None:
    parent = comments.create_comment(conn, 1, 2, "Parent")
    comments.create_reply(conn, 1, parent["id"], 3, "First reply")
    comments.create_reply(conn, 1, parent["id"], 4, "Second reply")

    root_author = notifications.list_notifications(conn, 2, username="original")[0]
    participant = notifications.list_notifications(conn, 3, username="first")[0]
    assert root_author["comment_preview"] == "Second reply"
    assert root_author["target_url"].endswith(f"#comment-{parent['id']}")
    assert participant["comment_preview"] == "Second reply"


def test_comment_preview_normalizes_whitespace_and_adds_ellipsis_only_when_needed() -> None:
    assert notifications.comment_preview(" one\n two\tthree ") == "one two three"
    assert notifications.comment_preview(" ".join(str(n) for n in range(12))) == " ".join(
        str(n) for n in range(12)
    )
    assert notifications.comment_preview(" ".join(str(n) for n in range(13))) == " ".join(
        str(n) for n in range(12)
    ) + "…"


def test_migration_preserves_legacy_notifications_and_enforces_grouped_root_alert(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "legacy.db"
    legacy_migrations = tmp_path / "migrations"
    legacy_migrations.mkdir()
    for migration_file in migrate.MIGRATIONS_DIR.glob("00*.sql"):
        if migration_file.name not in {
            "0029_comment_replies.sql",
            "0030_comment_reply_targets.sql",
            "0031_backfill_comment_notification_targets.sql",
            "0032_notification_comment_previews.sql",
        }:
            shutil.copy(migration_file, legacy_migrations / migration_file.name)

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", legacy_migrations)
    run_migrations(database_path)
    with db.connect_to(database_path) as connection:
        _seed(connection)
        connection.execute(
            "INSERT INTO comment (id, entry_id, author_id, body, created_at)"
            " VALUES (10, 1, 2, 'Legacy comment', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO notification (id, user_id, type, actor_id, entry_id, created_at)"
            " VALUES (99, 1, 'comment', 2, 1, '2026-01-01T00:00:00+00:00')"
        )

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", Path(__file__).parents[2] / "app/models/migrations")
    assert run_migrations(database_path) == [
        "0029_comment_replies.sql",
        "0030_comment_reply_targets.sql",
        "0031_backfill_comment_notification_targets.sql",
        "0032_notification_comment_previews.sql",
    ]
    with db.connect_to(database_path) as connection:
        preserved = connection.execute("SELECT * FROM notification WHERE id = 99").fetchone()
        assert preserved["type"] == "comment"
        assert preserved["comment_id"] == 10
        assert preserved["comment_preview"] == "Legacy comment"
        connection.execute(
            "INSERT INTO comment (id, entry_id, author_id, body, created_at)"
            " VALUES (11, 1, 2, 'Parent', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO notification (user_id, type, actor_id, entry_id, comment_id, created_at)"
            " VALUES (2, 'comment_reply', 3, 1, 11, '2026-01-01T00:00:00+00:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO notification (user_id, type, actor_id, entry_id, comment_id, created_at)"
                " VALUES (2, 'comment_reply', 4, 1, 11, '2026-01-02T00:00:00+00:00')"
            )


def test_preview_migration_backfills_historical_reply_text(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "reply-preview.db"
    legacy_migrations = tmp_path / "migrations"
    legacy_migrations.mkdir()
    for migration_file in migrate.MIGRATIONS_DIR.glob("00*.sql"):
        if migration_file.name != "0032_notification_comment_previews.sql":
            shutil.copy(migration_file, legacy_migrations / migration_file.name)

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", legacy_migrations)
    run_migrations(database_path)
    with db.connect_to(database_path) as connection:
        _seed(connection)
        connection.execute(
            "INSERT INTO comment (id, entry_id, author_id, body, created_at)"
            " VALUES (10, 1, 2, 'Root text', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO comment (id, entry_id, parent_comment_id, reply_to_comment_id, author_id, body, created_at)"
            " VALUES (11, 1, 10, 10, 3, 'Historical reply text', '2026-01-02T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO notification (user_id, type, actor_id, entry_id, comment_id, created_at)"
            " VALUES (2, 'comment_reply', 3, 1, 10, '2026-01-02T00:00:00+00:00')"
        )

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", Path(__file__).parents[2] / "app/models/migrations")
    assert run_migrations(database_path) == ["0032_notification_comment_previews.sql"]
    with db.connect_to(database_path) as connection:
        notification = connection.execute(
            "SELECT comment_preview FROM notification WHERE type = 'comment_reply'"
        ).fetchone()
        assert notification["comment_preview"] == "Historical reply text"
