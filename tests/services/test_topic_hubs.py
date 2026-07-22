from __future__ import annotations

from dataclasses import replace

from app.content.topic_hubs import topic_for_slug
from app.models import db
from app.services.search.topic_hubs import published_topic_paths, topic_page


def _schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, visibility TEXT NOT NULL,
            search_discovery INTEGER NOT NULL, deleted_at TEXT, suspended_at TEXT
        );
        CREATE TABLE activity (
            id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
            slug TEXT, archived_at TEXT, secret INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE entry (
            id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, activity_id INTEGER NOT NULL,
            hidden_at TEXT
        );
        """
    )


def _qualifying_activity(conn, activity_id: int, owner_id: int, name: str, slug: str) -> None:
    conn.execute(
        "INSERT INTO activity VALUES (?, ?, ?, ?, NULL, 0)",
        (activity_id, owner_id, name, slug),
    )
    conn.executemany(
        "INSERT INTO entry VALUES (?, ?, ?, NULL)",
        [(activity_id * 10 + number, owner_id, activity_id) for number in range(1, 4)],
    )


def test_topic_page_requires_approved_opted_in_public_owner_scoped_activities(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "topics.db"))
    topic = topic_for_slug("reading")
    assert topic is not None
    with db.connect() as conn:
        _schema(conn)
        conn.executemany(
            "INSERT INTO user VALUES (?, ?, ?, ?, ?, ?)",
            [(number, f"reader-{number}", "public", 1, None, None) for number in range(1, 6)]
            + [
                (6, "opted-out", "public", 0, None, None),
                (7, "private", "private", 1, None, None),
                (8, "deleted", "public", 1, "2026-01-01", None),
            ],
        )
        for number in range(1, 6):
            _qualifying_activity(conn, number, number, "Reading", f"reading-{number}")
        _qualifying_activity(conn, 6, 6, "Reading", "opted-out")
        _qualifying_activity(conn, 7, 7, "Reading", "private")
        _qualifying_activity(conn, 8, 8, "Reading", "deleted")
        conn.execute("INSERT INTO activity VALUES (9, 1, 'Reading', 'wrong-owner', NULL, 0)")
        conn.executemany(
            "INSERT INTO entry VALUES (?, 2, 9, NULL)", [(91,), (92,), (93,)],
        )

        result = topic_page(conn, topic)

    assert result is not None
    assert [activity["url"] for activity in result["activities"]] == [
        "/@reader-1/reading-1",
        "/@reader-2/reading-2",
        "/@reader-3/reading-3",
        "/@reader-4/reading-4",
        "/@reader-5/reading-5",
    ]
    assert "/@reader-1/wrong-owner" not in [activity["url"] for activity in result["activities"]]


def test_unapproved_or_thin_topic_is_not_published_or_in_sitemap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "thin-topics.db"))
    topic = topic_for_slug("reading")
    assert topic is not None
    with db.connect() as conn:
        _schema(conn)
        conn.executemany(
            "INSERT INTO user VALUES (?, ?, 'public', 1, NULL, NULL)",
            [(number, f"reader-{number}") for number in range(1, 5)],
        )
        for number in range(1, 5):
            _qualifying_activity(conn, number, number, "Reading", f"reading-{number}")

        assert topic_page(conn, topic) is None
        assert topic_page(conn, replace(topic, approved=False)) is None
        assert published_topic_paths(conn) == ()
