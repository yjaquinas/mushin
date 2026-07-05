"""Visitor analytics persistence."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.visitors.visitors import VisitorSnapshot


def upsert_visit(conn: sqlite3.Connection, visit: VisitorSnapshot) -> None:
    existing = conn.execute(
        """
        SELECT id
        FROM visitor_event
        WHERE visitor_key = ?
          AND last_seen_at >= datetime('now', '-2 hours')
        ORDER BY last_seen_at DESC
        LIMIT 1
        """,
        (visit.visitor_key,),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE visitor_event
            SET last_seen_at = CURRENT_TIMESTAMP,
                seen_count = seen_count + 1
            WHERE id = ?
            """,
            (existing["id"],),
        )
        return
    conn.execute(
        """
        INSERT INTO visitor_event (
            visitor_key, bucket_start, ip_address, country_code, country_name,
            region, city, referrer, referrer_host, landing_path, user_agent,
            browser, os, device, is_bot
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            visit.visitor_key,
            visit.bucket_start,
            visit.ip_address,
            visit.country_code,
            visit.country_name,
            visit.region,
            visit.city,
            visit.referrer,
            visit.referrer_host,
            visit.landing_path,
            visit.user_agent,
            visit.browser,
            visit.os,
            visit.device,
            int(visit.is_bot),
        ),
    )
