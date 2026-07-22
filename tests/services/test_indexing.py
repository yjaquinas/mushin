from __future__ import annotations

from xml.etree import ElementTree

from app.models import db
from app.models.migrate import run_migrations
from app.routes.web.home import routes as home_routes
from app.services.search.indexing import (
    is_indexable_activity,
    is_indexable_profile,
    sitemap_records,
)


def _schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, visibility TEXT NOT NULL,
            search_discovery INTEGER NOT NULL DEFAULT 0, search_discovery_updated_at TEXT,
            created_at TEXT NOT NULL, deleted_at TEXT, suspended_at TEXT
        );
        CREATE TABLE activity (
            id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name TEXT NOT NULL, slug TEXT,
            archived_at TEXT, secret INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE entry (
            id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, activity_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT, hidden_at TEXT
        );
        """
    )


def _seed(conn) -> None:
    conn.executemany(
        "INSERT INTO user VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                1,
                "eligible",
                "public",
                1,
                "2026-02-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                None,
                None,
            ),
            (2, "private", "private", 1, None, "2026-01-01T00:00:00Z", None, None),
            (3, "opted-out", "public", 0, None, "2026-01-01T00:00:00Z", None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO activity VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "Running", "running", None, 0, "2026-01-01T00:00:00Z"),
            (2, 1, "Secret", "secret", None, 1, "2026-01-01T00:00:00Z"),
            (3, 1, " ", "empty", None, 0, "2026-01-01T00:00:00Z"),
            (4, 1, "Two", "two", None, 0, "2026-01-01T00:00:00Z"),
            (5, 2, "Private", "private", None, 0, "2026-01-01T00:00:00Z"),
            (6, 3, "Opted out", "opted-out", None, 0, "2026-01-01T00:00:00Z"),
        ],
    )
    entry_id = 1
    for activity_id in (1, 2, 3, 5, 6):
        for _ in range(3):
            conn.execute(
                "INSERT INTO entry VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    1 if activity_id < 5 else (2 if activity_id == 5 else 3),
                    activity_id,
                    "2026-03-01T00:00:00Z",
                    "2026-03-02T00:00:00Z",
                    None,
                ),
            )
            entry_id += 1
    for _ in range(2):
        conn.execute(
            "INSERT INTO entry VALUES (?, 1, 4, ?, ?, ?)",
            (entry_id, "2026-03-01T00:00:00Z", None, None),
        )
        entry_id += 1


def test_eligibility_requires_public_opt_in_qualifying_activity(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "indexing.db"))
    with db.connect() as conn:
        _schema(conn)
        _seed(conn)
        eligible = {"id": 1, "visibility": "public", "search_discovery": True}
        assert is_indexable_profile(conn, eligible)
        assert is_indexable_activity(conn, owner_id=1, activity_id=1, profile_user=eligible)
        assert not is_indexable_activity(conn, owner_id=1, activity_id=2, profile_user=eligible)
        assert not is_indexable_activity(conn, owner_id=1, activity_id=3, profile_user=eligible)
        assert not is_indexable_activity(conn, owner_id=1, activity_id=4, profile_user=eligible)
        assert not is_indexable_profile(
            conn, {"id": 2, "visibility": "private", "search_discovery": True}
        )
        assert not is_indexable_profile(
            conn, {"id": 3, "visibility": "public", "search_discovery": False}
        )


def test_sitemap_includes_only_eligible_canonical_records_and_valid_xml(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "sitemap.db"))
    with db.connect() as conn:
        _schema(conn)
        _seed(conn)
        records = sitemap_records(conn)
    assert records == [
        {"path": "/@eligible", "lastmod": "2026-03-02T00:00:00Z"},
        {"path": "/@eligible/running", "lastmod": "2026-03-02T00:00:00Z"},
    ]

    from fastapi import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/sitemap.xml",
            "headers": [(b"host", b"mushin.aqnas.xyz")],
            "server": ("mushin.aqnas.xyz", 443),
        }
    )
    response = awaitable_result(home_routes.sitemap_xml(request))
    assert response.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(response.body)
    locs = [
        item.text
        for item in root.findall(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]
    assert "https://mushin.aqnas.xyz/@eligible" in locs
    assert "https://mushin.aqnas.xyz/@eligible/running" in locs
    assert all(
        "private" not in loc and "secret" not in loc and "empty" not in loc and "two" not in loc
        for loc in locs
    )


def awaitable_result(coro):
    import asyncio

    return asyncio.run(coro)


def test_search_discovery_defaults_to_opted_in_and_enables_existing_users(tmp_path) -> None:
    database_path = tmp_path / "migrations.db"
    run_migrations(database_path)
    with db.connect_to(database_path) as conn:
        conn.execute("INSERT INTO user (username, password_hash) VALUES ('new-user', 'hash')")
        row = conn.execute(
            "SELECT search_discovery FROM user WHERE username = 'new-user'"
        ).fetchone()
        assert row[0] == 1
        conn.execute("UPDATE user SET search_discovery = 0")
        conn.execute("DELETE FROM _migrations WHERE filename = '0028_enable_search_discovery.sql'")

    run_migrations(database_path)
    with db.connect_to(database_path) as conn:
        row = conn.execute(
            "SELECT search_discovery FROM user WHERE username = 'new-user'"
        ).fetchone()
    assert row[0] == 1
