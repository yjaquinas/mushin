"""Dynamic XML sitemap response for canonical, search-eligible pages."""

from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import Request
from fastapi.responses import Response

from app.models import db
from app.services.search.indexing import sitemap_records
from app.services.search.topic_hubs import published_topic_paths

_STABLE_PATHS = (
    "/",
    "/privacy",
    "/terms",
    "/licenses",
    "/guides",
    "/guides/what-is-a-practice-log",
    "/guides/simple-habit-tracker-for-showing-up",
    "/guides/track-a-habit-without-a-chore",
    "/guides/keep-a-training-log",
    "/guides/progress-journal-for-steady-study",
    "/guides/progress-journal-versus-habit-tracker",
    "/guides/streaks-help-and-do-not",
    "/guides/start-tracking-one-activity",
)


def sitemap_response(request: Request) -> Response:
    """Build the first bounded sitemap page from canonical eligible URLs.

    ``sitemap_records`` is intentionally page-sized, so introducing a sitemap
    index later only needs cursor/page routes around this serializer.
    """
    base = str(request.base_url).rstrip("/")
    with db.connect() as conn:
        conn.execute("BEGIN")
        records = sitemap_records(conn)
        topic_paths = published_topic_paths(conn)

    urls = [{"path": path, "lastmod": None} for path in _STABLE_PATHS]
    urls.extend({"path": path, "lastmod": None} for path in topic_paths)
    urls.extend(records)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for record in urls:
        loc = escape(f"{base}{record['path']}")
        lastmod = f"<lastmod>{escape(record['lastmod'])}</lastmod>" if record["lastmod"] else ""
        lines.append(f"  <url><loc>{loc}</loc>{lastmod}</url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines) + "\n", media_type="application/xml")
