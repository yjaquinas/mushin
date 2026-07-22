from __future__ import annotations

import json
import re
from xml.etree import ElementTree

import pytest
from fastapi import Request

from app.content.guides import GUIDES
from app.routes.web.guides import routes as guide_routes
from app.routes.web.home._sitemap import sitemap_response


def _request(path: str, query_string: bytes = b"") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query_string,
            "headers": [(b"host", b"mushin.aqnas.xyz")],
            "server": ("mushin.aqnas.xyz", 443),
        }
    )


def _json_ld(body: str) -> dict[str, object]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', body)
    assert match is not None
    return json.loads(match.group(1))


async def test_guide_index_is_public_and_links_every_guide() -> None:
    response = await guide_routes.guide_index(_request("/guides"))
    body = response.body.decode()

    assert response.status_code == 200
    assert '<h1 class="text-hero-numeral' in body
    assert '<link rel="canonical" href="https://mushin.aqnas.xyz/guides">' in body
    assert 'class="bottom-nav"' not in body
    assert "data-guide-back" in body
    for guide in GUIDES:
        assert guide.title in body
        assert f'href="/guides/{guide.slug}"' in body


async def test_guide_detail_has_truthful_article_metadata_and_server_rendered_content() -> None:
    guide = GUIDES[0]
    response = await guide_routes.guide_detail(
        _request(f"/guides/{guide.slug}", b"ref=home"), guide.slug
    )
    body = response.body.decode()
    schema = _json_ld(body)

    assert response.status_code == 200
    assert f"<title>{guide.title} · Mushin</title>" in body
    assert f'<meta name="description" content="{guide.description}">' in body
    assert f'<link rel="canonical" href="https://mushin.aqnas.xyz/guides/{guide.slug}">' in body
    assert '<meta property="og:type" content="article">' in body
    assert 'class="bottom-nav"' not in body
    assert "data-guide-back" in body
    assert re.search(rf"<h1[^>]*>{re.escape(guide.title)}</h1>", body)
    assert guide.workflow in body
    assert guide.limitation in body
    assert schema["@type"] == "Article"
    assert schema["author"] == {"@type": "Organization", "name": "Mushin editorial team"}
    assert schema["datePublished"] == guide.published_on


async def test_unknown_guide_returns_a_non_indexable_not_found_page() -> None:
    response = await guide_routes.guide_detail(_request("/guides/nope"), "nope")

    assert response.status_code == 404
    assert b'content="noindex, nofollow"' in response.body


async def test_signed_in_guide_reader_gets_the_shared_bottom_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(guide_routes, "_current_user", lambda _session: {"id": 1})

    response = await guide_routes.guide_index(_request("/guides"), "signed-in-session")

    assert 'class="bottom-nav"' in response.body.decode()


def test_sitemap_includes_the_stable_guide_urls() -> None:
    response = sitemap_response(_request("/sitemap.xml"))
    root = ElementTree.fromstring(response.body)
    locs = [
        item.text
        for item in root.findall(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]

    assert "https://mushin.aqnas.xyz/guides" in locs
    assert len([loc for loc in locs if loc and "/guides/" in loc]) == len(GUIDES)
