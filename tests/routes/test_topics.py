from __future__ import annotations

import json
import re

from fastapi import Request

from app.models import db
from app.routes.web.home._sitemap import sitemap_response
from app.routes.web.topics import routes as topic_routes


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http", "method": "GET", "scheme": "https", "path": path,
            "raw_path": path.encode(), "query_string": b"ref=ignored",
            "headers": [(b"host", b"mushin.aqnas.xyz")], "server": ("mushin.aqnas.xyz", 443),
        }
    )


def _seed(conn, *, activity_count: int = 5) -> None:
    conn.executescript(
        """
        CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT NOT NULL, visibility TEXT NOT NULL,
            search_discovery INTEGER NOT NULL, search_discovery_updated_at TEXT, created_at TEXT NOT NULL,
            deleted_at TEXT, suspended_at TEXT);
        CREATE TABLE activity (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
            slug TEXT, archived_at TEXT, secret INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE entry (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, activity_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT, hidden_at TEXT);
        """
    )
    for number in range(1, activity_count + 1):
        username = "reader-&lt;safe&gt;" if number == 1 else f"reader-{number}"
        conn.execute(
            "INSERT INTO user VALUES (?, ?, 'public', 1, NULL, '2026-01-01', NULL, NULL)",
            (number, username),
        )
        conn.execute(
            "INSERT INTO activity VALUES (?, ?, 'Reading', ?, NULL, 0, '2026-01-01')",
            (number, number, f"reading-{number}"),
        )
        conn.executemany(
            "INSERT INTO entry VALUES (?, ?, ?, '2026-01-01', NULL, NULL)",
            [(number * 10 + index, number, number) for index in range(1, 4)],
        )


async def test_published_topic_has_canonical_metadata_safe_content_and_sitemap_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "topic-route.db"))
    with db.connect() as conn:
        _seed(conn)

    response = await topic_routes.topic_detail(_request("/topics/reading"), "reading")
    body = response.body.decode()
    schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', body).group(1))

    assert response.status_code == 200
    assert '<link rel="canonical" href="https://mushin.aqnas.xyz/topics/reading">' in body
    assert '<meta name="description" content="Explore public reading records' in body
    assert "reader-&amp;lt;safe&amp;gt;" in body
    assert "reader-&lt;safe&gt;" not in body
    assert schema["@type"] == "ItemList"
    assert len(schema["itemListElement"]) == 5
    assert all("/reading-" in item["url"] for item in schema["itemListElement"])
    sitemap = sitemap_response(_request("/sitemap.xml")).body.decode()
    assert "https://mushin.aqnas.xyz/topics/reading" in sitemap


async def test_empty_or_unknown_topic_returns_noindex_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "empty-topic-route.db"))
    with db.connect() as conn:
        _seed(conn)
        conn.execute("DELETE FROM entry WHERE activity_id = 5")

    empty = await topic_routes.topic_detail(_request("/topics/reading"), "reading")
    unknown = await topic_routes.topic_detail(_request("/topics/nope"), "nope")

    assert empty.status_code == unknown.status_code == 404
    assert b'content="noindex, nofollow"' in empty.body


async def test_topic_page_uses_a_crawlable_path_for_pagination(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "topic-page.db"))
    with db.connect() as conn:
        _seed(conn, activity_count=13)

    response = await topic_routes.topic_detail(_request("/topics/reading/page/2"), "reading", 2)
    body = response.body.decode()

    assert response.status_code == 200
    assert '<link rel="canonical" href="https://mushin.aqnas.xyz/topics/reading/page/2">' in body
    assert 'href="/topics/reading"' in body
