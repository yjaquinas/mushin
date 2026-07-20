from __future__ import annotations

from datetime import UTC, datetime

from app.models import db
from app.routes.web.common.templates import _format_feed_entry_timestamp
from app.services.search.discovery import (
    FeedCursorError,
    recent_fellow_entries,
    recent_public_entries,
    recent_social_entries,
)


def test_recent_public_entries_returns_individual_visible_entries(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "mushin.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))

    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                visibility TEXT NOT NULL,
                deleted_at TEXT
            );
            CREATE TABLE activity (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT,
                archived_at TEXT,
                secret INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE entry (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                activity_id INTEGER NOT NULL,
                memo TEXT,
                occurred_at TEXT NOT NULL,
                time_known INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                hidden_at TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO user (id, username, visibility, deleted_at) VALUES (?, ?, ?, ?)",
            [
                (1, "public-user", "public", None),
                (2, "private-user", "private", None),
                (3, "deleted-user", "public", "2026-01-01T00:00:00Z"),
            ],
        )
        conn.executemany(
            """INSERT INTO activity (id, owner_id, name, slug, archived_at, secret)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (1, 1, "Running", "running", None, 0),
                (2, 1, "Reading", "reading", None, 0),
                (3, 1, "Secret", "secret", None, 1),
                (4, 1, "Archived", "archived", "2026-01-01T00:00:00Z", 0),
                (5, 2, "Private", "private", None, 0),
                (6, 3, "Deleted", "deleted", None, 0),
            ],
        )
        conn.executemany(
            """INSERT INTO entry
               (id, owner_id, activity_id, memo, occurred_at, created_at, hidden_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, 1, 1, "first run", "2026-01-01", "2026-01-01T00:00:00Z", None),
                (2, 1, 2, "reading", "2026-01-02", "2026-01-02T00:00:00Z", None),
                (3, 1, 1, "second run", "2026-01-03", "2026-01-03T00:00:00Z", None),
                (4, 1, 1, "hidden", "2026-01-04", "2026-01-04T00:00:00Z", "2026-01-04T00:00:00Z"),
                (5, 1, 3, "secret", "2026-01-05", "2026-01-05T00:00:00Z", None),
                (6, 1, 4, "archived", "2026-01-06", "2026-01-06T00:00:00Z", None),
                (7, 2, 5, "private", "2026-01-07", "2026-01-07T00:00:00Z", None),
                (8, 3, 6, "deleted", "2026-01-08", "2026-01-08T00:00:00Z", None),
            ],
        )

    feed = recent_public_entries(limit=2)

    assert [(item["entry_id"], item["name"]) for item in feed] == [
        (3, "Running"),
        (2, "Reading"),
    ]
    assert feed[0]["activity_url"] == "/@public-user/running"


def test_format_feed_entry_timestamp_uses_entry_date_and_optional_time() -> None:
    occurred_at = "2026-07-20T14:05:00+09:00"

    assert _format_feed_entry_timestamp(occurred_at) == "Jul 20 2:05 PM"
    assert _format_feed_entry_timestamp(occurred_at, time_known=False) == "Jul 20"


def test_recent_fellow_entries_returns_only_consented_fellows(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "mushin.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))

    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT NOT NULL, deleted_at TEXT);
            CREATE TABLE activity (
                id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
                slug TEXT, archived_at TEXT, secret INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE entry (
                id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, activity_id INTEGER NOT NULL,
                memo TEXT, occurred_at TEXT NOT NULL, time_known INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, hidden_at TEXT
            );
            CREATE TABLE connection (
                id INTEGER PRIMARY KEY, user_lo INTEGER NOT NULL, user_hi INTEGER NOT NULL,
                status TEXT NOT NULL, sharing_consent_at TEXT
            );
            INSERT INTO user VALUES (1, 'viewer', NULL), (2, 'fellow', NULL),
                (3, 'pending', NULL), (4, 'unconsented', NULL);
            INSERT INTO activity VALUES
                (1, 2, 'Reading', 'reading', NULL, 0),
                (2, 2, 'Secret', 'secret', NULL, 1),
                (3, 3, 'Running', 'running', NULL, 0),
                (4, 4, 'Writing', 'writing', NULL, 0);
            INSERT INTO entry VALUES
                (1, 2, 1, 'visible', '2026-01-01', 1, '2026-01-04T00:00:00Z', NULL),
                (2, 2, 2, 'secret', '2026-01-02', 1, '2026-01-05T00:00:00Z', NULL),
                (3, 3, 3, 'pending', '2026-01-03', 1, '2026-01-06T00:00:00Z', NULL),
                (4, 4, 4, 'unconsented', '2026-01-04', 1, '2026-01-07T00:00:00Z', NULL);
            INSERT INTO connection VALUES
                (1, 1, 2, 'accepted', '2026-01-01T00:00:00Z'),
                (2, 1, 3, 'pending', NULL),
                (3, 1, 4, 'accepted', NULL);
            """
        )

    feed = recent_fellow_entries(1)

    assert [(item["entry_id"], item["username"], item["name"]) for item in feed] == [
        (1, "fellow", "Reading")
    ]


def test_recent_social_entries_excludes_self_limits_window_and_paginates(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "mushin.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(database_path))

    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL, visibility TEXT NOT NULL,
                deleted_at TEXT
            );
            CREATE TABLE activity (
                id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
                slug TEXT, archived_at TEXT, secret INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE entry (
                id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, activity_id INTEGER NOT NULL,
                memo TEXT, occurred_at TEXT NOT NULL, time_known INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, hidden_at TEXT
            );
            INSERT INTO user VALUES (1, 'viewer', 'public', NULL),
                (2, 'other', 'public', NULL);
            INSERT INTO activity VALUES (1, 1, 'Mine', 'mine', NULL, 0),
                (2, 2, 'Reading', 'reading', NULL, 0);
            INSERT INTO entry VALUES
                (1, 1, 1, 'self', '2026-01-31', 1, '2026-01-31T00:00:00+00:00', NULL),
                (2, 2, 2, 'newest', '2026-01-30', 1, '2026-01-30T00:00:00+00:00', NULL),
                (3, 2, 2, 'next', '2026-01-29', 1, '2026-01-29T00:00:00+00:00', NULL),
                (4, 2, 2, 'old', '2025-12-31', 1, '2025-12-31T00:00:00+00:00', NULL);
            """
        )

    now = datetime(2026, 1, 31, tzinfo=UTC)
    first_page = recent_social_entries(1, "public", limit=1, now=now)

    assert [entry["entry_id"] for entry in first_page["entries"]] == [2]
    assert first_page["next_cursor"]

    second_page = recent_social_entries(
        1, "public", limit=1, cursor=first_page["next_cursor"], now=now
    )

    assert [entry["entry_id"] for entry in second_page["entries"]] == [3]
    assert second_page["next_cursor"] is None


def test_recent_social_entries_rejects_malformed_cursor() -> None:
    try:
        recent_social_entries(1, "public", cursor="not a cursor")
    except FeedCursorError:
        pass
    else:
        raise AssertionError("Expected malformed cursor to be rejected")
