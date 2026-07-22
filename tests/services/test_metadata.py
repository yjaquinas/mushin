from __future__ import annotations

import json
import re
from dataclasses import dataclass

from fastapi import Request

from app.routes.web.common.templates import templates
from app.services.search import metadata


@dataclass
class _Result:
    row: dict[str, str | None]

    def fetchone(self) -> dict[str, str | None]:
        return self.row


class _Connection:
    def __init__(self, *rows: dict[str, str | None]) -> None:
        self.rows = iter(rows)

    def execute(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result(next(self.rows))


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


def _json_ld(body: str) -> dict[str, object]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', body)
    assert match is not None
    return json.loads(match.group(1))


def test_eligible_profile_metadata_is_specific_escaped_and_valid_json_ld() -> None:
    url = "https://mushin.aqnas.xyz/@sam"
    data = metadata.profile_metadata(
        _Connection({"modified_at": "2026-07-20T12:00:00Z"}),
        canonical_url=url,
        username="sam",
        profile_user={"id": 1, "created_at": "2025-01-02T00:00:00Z"},
        cards=[{"name": "Reading"}],
        fellow_count=2,
        bio='Reads <books> & writes "notes".',
    )

    body = templates.get_template("web/base.html.jinja2").render(
        request=_request("/@sam"), meta_robots="index, follow", title=data["og_title"], **data
    )
    schema = _json_ld(body)

    assert 'content="Reads &lt;books&gt; &amp; writes &#34;notes&#34;.' in body
    assert "<title>sam · Mushin</title>" in body
    assert '<meta name="robots" content="index, follow">' in body
    assert '<meta property="og:title" content="sam · Mushin">' in body
    assert '<meta property="og:url" content="https://mushin.aqnas.xyz/@sam">' in body
    assert '<link rel="canonical" href="https://mushin.aqnas.xyz/@sam">' in body
    assert '<meta name="twitter:card" content="summary_large_image">' in body
    assert schema["@type"] == "ProfilePage"
    assert schema["dateCreated"] == "2025-01-02T00:00:00Z"
    assert schema["dateModified"] == "2026-07-20T12:00:00Z"
    assert schema["mainEntity"]["alternateName"] == "sam"  # type: ignore[index]


def test_eligible_activity_metadata_is_truthful_and_noindex_page_emits_no_json_ld() -> None:
    url = "https://mushin.aqnas.xyz/@sam/reading"
    data = metadata.activity_metadata(
        _Connection(
            {
                "first_entry_at": "2026-01-01T08:00:00Z",
                "last_entry_at": "2026-07-20T08:00:00Z",
                "modified_at": "2026-07-20T09:00:00Z",
            }
        ),
        canonical_url=url,
        username="sam",
        owner_id=1,
        activity_id=3,
        card={"name": 'Reading <"classics">', "counts": {"lifetime": 12}, "streaks": {"current": 4}},
    )
    body = templates.get_template("web/base.html.jinja2").render(
        request=_request("/@sam/reading"), meta_robots="index, follow", title=data["og_title"], **data
    )
    schema = _json_ld(body)
    noindex_body = templates.get_template("web/base.html.jinja2").render(
        request=_request("/@sam/reading"), meta_robots="noindex, nofollow"
    )

    assert 'Reading &lt;&#34;classics&#34;&gt;' in body
    assert '<meta name="robots" content="index, follow">' in body
    assert '<meta property="og:title" content="Reading &lt;&#34;classics&#34;&gt; · sam · Mushin">' in body
    assert '<meta property="og:type" content="website">' in body
    assert "Recorded from 2026-01-01 to 2026-07-20." in body
    assert schema["@type"] == "CollectionPage"
    assert schema["mainEntity"]["@type"] == "Collection"  # type: ignore[index]
    assert schema["mainEntity"]["temporalCoverage"] == "2026-01-01/2026-07-20"  # type: ignore[index]
    assert "application/ld+json" not in noindex_body
