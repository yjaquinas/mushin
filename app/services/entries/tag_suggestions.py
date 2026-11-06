"""Owner-scoped suggestions from saved entry notes."""
import sqlite3
from app.services.entries.entries import parse_hashtags


def activity_tags(conn: sqlite3.Connection, owner_id: int, activity_id: int) -> list[str]:
    totals = {}
    for row in conn.execute(
        "SELECT memo, occurred_at FROM entry WHERE owner_id = ? AND activity_id = ?",
        (owner_id, activity_id),
    ):
        for name in set(parse_hashtags(row["memo"] or "")):
            count, latest = totals.get(name, (0, ""))
            totals[name] = (count + 1, max(latest, str(row["occurred_at"])))
    names = sorted(totals)
    names.sort(key=lambda name: totals[name][1], reverse=True)
    names.sort(key=lambda name: totals[name][0], reverse=True)
    return names
