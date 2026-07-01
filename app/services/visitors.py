"""Request visitor analytics for the operator dashboard."""

from __future__ import annotations

import hashlib
import ipaddress
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import Request
from user_agents import parse as parse_user_agent

from app.models import db
from app.services import visitor_geo, visitor_store

_BUCKET_HOURS = 2
_SKIPPED_PREFIXES = ("/static/", "/admin")
_SKIPPED_PATHS = {"/health", "/favicon.ico"}


@dataclass(frozen=True)
class VisitorSnapshot:
    visitor_key: str
    bucket_start: str
    ip_address: str
    country_code: str | None
    country_name: str | None
    region: str | None
    city: str | None
    referrer: str | None
    referrer_host: str | None
    landing_path: str
    user_agent: str
    browser: str
    os: str
    device: str
    is_bot: bool


def should_track_path(path: str) -> bool:
    return path not in _SKIPPED_PATHS and not path.startswith(_SKIPPED_PREFIXES)


def record_request(request: Request) -> None:
    if not should_track_path(request.url.path):
        return
    snapshot = snapshot_from_request(request)
    with db.connect() as conn:
        visitor_store.upsert_visit(conn, snapshot)


def snapshot_from_request(request: Request) -> VisitorSnapshot:
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    accept_language = request.headers.get("accept-language", "")
    visitor_key = _visitor_key(ip_address, user_agent, accept_language)
    ua = parse_user_agent(user_agent)
    location = visitor_geo.lookup_location(ip_address)
    referrer = request.headers.get("referer")
    return VisitorSnapshot(
        visitor_key=visitor_key,
        bucket_start=_bucket_start(datetime.now(UTC)),
        ip_address=ip_address,
        country_code=location["country_code"],
        country_name=location["country_name"],
        region=location["region"],
        city=location["city"],
        referrer=referrer,
        referrer_host=_host_from_url(referrer),
        landing_path=request.url.path,
        user_agent=user_agent,
        browser=ua.browser.family,
        os=ua.os.family,
        device=_device_label(ua),
        is_bot=ua.is_bot,
    )


def _client_ip(request: Request) -> str:
    candidates = [
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        request.client.host if request.client else None,
    ]
    public_ip: str | None = None
    fallback_ip: str | None = None
    for value in candidates:
        for ip_address in _ip_candidates(value):
            if fallback_ip is None:
                fallback_ip = ip_address
            if _is_public_ip(ip_address):
                public_ip = ip_address
                break
        if public_ip is not None:
            break
    return public_ip or fallback_ip or ""


def _ip_candidates(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _is_public_ip(value: str) -> bool:
    try:
        ip_address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip_address.is_global


def _visitor_key(ip_address: str, user_agent: str, accept_language: str) -> str:
    salt = os.getenv("VISITOR_ANALYTICS_SALT") or os.getenv("SESSION_SECRET", "")
    raw = "\n".join((salt, ip_address, user_agent, accept_language))
    return hashlib.sha256(raw.encode()).hexdigest()


def _bucket_start(now: datetime) -> str:
    start_hour = now.hour - (now.hour % _BUCKET_HOURS)
    bucket = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    return bucket.strftime("%Y-%m-%d %H:%M:%S")


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    host = urlparse(value).netloc.lower()
    return host.removeprefix("www.") or None


def _device_label(ua: object) -> str:
    if ua.is_mobile:
        return "Mobile"
    if ua.is_tablet:
        return "Tablet"
    if ua.is_pc:
        return "Desktop"
    if ua.is_bot:
        return "Bot"
    return "Other"
