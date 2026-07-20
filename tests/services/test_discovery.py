from __future__ import annotations

from app.models import db
from app.routes.web.common.templates import _format_feed_entry_timestamp
from app.services.search.discovery import recent_public_entries


def test_recent_public_entries_returns_individual_visible_entries(
    tmp_path, monkeypatch
) -> None:
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
