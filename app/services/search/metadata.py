"""Truthful metadata for canonical, search-eligible public pages.

The route decides whether a response is eligible for indexing.  This module
only turns data already visible on that response into bounded metadata and
JSON-LD; it is deliberately not a second visibility authority.
"""

from __future__ import annotations

from typing import Any

from app import ui_strings

DESCRIPTION_LIMIT = 160


def _bounded(text: str, *, limit: int = DESCRIPTION_LIMIT) -> str:
    """Normalize whitespace and cap a metadata description at a useful size."""
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _date_part(value: str | None) -> str | None:
    return value[:10] if value else None


def _row_value(row: Any, key: str) -> Any:
    """Read a DB row defensively so optional aggregate results stay optional."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _activity_dates(conn: Any, *, owner_id: int, activity_id: int) -> dict[str, str | None]:
    """Return public entry dates, always scoped to the record owner."""
    row = conn.execute(
        """SELECT MIN(occurred_at) AS first_entry_at,
                  MAX(occurred_at) AS last_entry_at,
                  MAX(COALESCE(updated_at, created_at)) AS modified_at
             FROM entry
            WHERE owner_id = ? AND activity_id = ? AND hidden_at IS NULL""",
        (owner_id, activity_id),
    ).fetchone()
    if row is None:
        return {"first": None, "last": None, "modified": None}
    return {
        "first": _date_part(_row_value(row, "first_entry_at")),
        "last": _date_part(_row_value(row, "last_entry_at")),
        "modified": _row_value(row, "modified_at"),
    }


def profile_metadata(
    conn: Any,
    *,
    canonical_url: str,
    username: str,
    profile_user: dict[str, Any],
    cards: list[dict[str, Any]],
    fellow_count: int | None,
    bio: str,
) -> dict[str, Any]:
    """Build metadata for an already-eligible public profile."""
    public_activity_count = len(cards)
    description = _bounded(
        bio or ui_strings.META_DESCRIPTION_PROFILE_PUBLIC.format(
            username=username, activity_count=public_activity_count
        )
    )
    created_at = profile_user.get("created_at")
    latest = conn.execute(
        """SELECT MAX(COALESCE(e.updated_at, e.created_at)) AS modified_at
             FROM entry AS e
             JOIN activity AS a ON a.id = e.activity_id AND a.owner_id = e.owner_id
            WHERE e.owner_id = ? AND e.hidden_at IS NULL
              AND a.archived_at IS NULL AND a.secret = 0""",
        (profile_user["id"],),
    ).fetchone()
    modified_at = _row_value(latest, "modified_at") or created_at

    person: dict[str, Any] = {
        "@type": "Person",
        "name": username,
        "alternateName": username,
        "url": canonical_url,
    }
    if bio:
        person["description"] = bio
    properties = [{"@type": "PropertyValue", "name": ui_strings.SCHEMA_PUBLIC_ACTIVITIES, "value": public_activity_count}]
    if fellow_count is not None:
        properties.append({"@type": "PropertyValue", "name": ui_strings.SCHEMA_FELLOWS, "value": fellow_count})
    person["additionalProperty"] = properties

    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "ProfilePage",
        "@id": canonical_url,
        "url": canonical_url,
        "mainEntity": person,
    }
    if created_at:
        schema["dateCreated"] = created_at
    if modified_at:
        schema["dateModified"] = modified_at
    return {
        "meta_description": description,
        "og_title": ui_strings.META_TITLE_PROFILE_PUBLIC.format(username=username),
        "og_description": description,
        "og_type": "profile",
        "twitter_card_type": "summary_large_image",
        "structured_data": schema,
        "visible_summary": ui_strings.PUBLIC_PROFILE_SUMMARY.format(
            username=username, activity_count=public_activity_count
        ),
    }


def activity_metadata(
    conn: Any,
    *,
    canonical_url: str,
    username: str,
    owner_id: int,
    activity_id: int,
    card: dict[str, Any],
) -> dict[str, Any]:
    """Build metadata for an already-eligible public activity record."""
    dates = _activity_dates(conn, owner_id=owner_id, activity_id=activity_id)
    title = str(card.get("name") or "")
    total = int(card.get("counts", {}).get("lifetime", 0))
    streak = int(card.get("streaks", {}).get("current", card.get("streak", 0)) or 0)
    description = ui_strings.META_DESCRIPTION_ACTIVITY_PUBLIC.format(
        activity=title, username=username, total=total
    )
    if streak:
        description = f"{description} {ui_strings.META_DESCRIPTION_ACTIVITY_STREAK.format(streak=streak)}"
    if dates["first"] and dates["last"]:
        description = f"{description} {ui_strings.META_DESCRIPTION_DATE_RANGE.format(start=dates['first'], end=dates['last'])}"
    description = _bounded(description)

    collection: dict[str, Any] = {
        "@type": "Collection",
        "name": title,
        "url": canonical_url,
        "creator": {"@type": "Person", "name": username, "alternateName": username},
        "additionalProperty": [
            {"@type": "PropertyValue", "name": ui_strings.SCHEMA_CURRENT_TOTAL, "value": total}
        ],
    }
    if streak:
        collection["additionalProperty"].append(
            {"@type": "PropertyValue", "name": ui_strings.SCHEMA_CURRENT_STREAK, "value": streak}
        )
    if dates["first"] and dates["last"]:
        collection["temporalCoverage"] = f"{dates['first']}/{dates['last']}"

    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": canonical_url,
        "url": canonical_url,
        "name": title,
        "mainEntity": collection,
    }
    if dates["modified"]:
        schema["dateModified"] = dates["modified"]

    summary = ui_strings.PUBLIC_ACTIVITY_SUMMARY.format(
        username=username, activity=title, total=total
    )
    if streak:
        summary = f"{summary} {ui_strings.PUBLIC_ACTIVITY_SUMMARY_STREAK.format(streak=streak)}"
    if dates["first"] and dates["last"]:
        summary = f"{summary} {ui_strings.PUBLIC_ACTIVITY_SUMMARY_RANGE.format(start=dates['first'], end=dates['last'])}"
    return {
        "meta_description": description,
        "og_title": ui_strings.META_TITLE_ACTIVITY_PUBLIC.format(activity=title, username=username),
        "og_description": description,
        "og_type": "website",
        "twitter_card_type": "summary_large_image",
        "structured_data": schema,
        "visible_summary": summary,
    }
