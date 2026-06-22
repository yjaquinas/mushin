"""Shared pytest fixtures for Mushin.

See .claude/rules/tests.md for layout and conventions. Integration tests use
httpx.AsyncClient against the FastAPI app directly; never run against the dev DB.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import db
from app.services import categories, entries

_UTC = ZoneInfo("UTC")


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client bound to the FastAPI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Generic test-fixture activity helper
# ---------------------------------------------------------------------------
#
# Replaces the deleted onboarding-template seeding module (the kendo +
# reading starter templates, removed along with the progression feature —
# see meetings/MEETING-2026-06-21-simplify-onboarding). Many tests only ever
# used that module as a fixture convenience to get "an account with at least
# one activity that has entries" so they could test unrelated behavior
# (stats, access control, public profiles, portability, comments). This is a
# fresh, minimal substitute for that — not a restoration of kendo/reading.


def seed_test_activity(
    owner_id: int,
    *,
    name: str = "Test Activity",
    icon: str | None = None,
    entry_count: int = 0,
    extra_field_kinds: tuple[str, ...] = (),
    tz: ZoneInfo = _UTC,
) -> dict[str, Any]:
    """Create one general-log activity for *owner_id* with optional entries.

    Uses :func:`app.services.categories.create_activity`, so the created
    activity carries the current default recipe (``memo`` + ``tag_group``
    field_defs) — the same shape any real user gets when creating a category
    by hand. *entry_count* bare entries (no tags/values) are then logged
    against it via :func:`app.services.entries.create`, in *tz*, so
    count/streak caches are non-zero when *entry_count* > 0.

    *extra_field_kinds* appends additional ``field_def`` rows beyond the
    default memo/tag_group pair (e.g. ``("match_list",)`` for tests exercising
    the competition/match-list sub-form — there's no service-layer helper for
    that, since real category creation never adds one on its own).

    Returns ``{"category_id": int, "activity_id": int, "entry_ids": list[int],
    "field_def_ids": dict[str, int]}`` — ``field_def_ids`` maps each field
    kind present on the activity to its (first) field_def id, covering both
    the default recipe and any *extra_field_kinds*.
    """
    result = categories.create_activity(owner_id, name=name, icon=icon)
    activity_id = result["activity_id"]

    if extra_field_kinds:
        with db.connect() as conn:
            conn.execute("BEGIN")
            next_sort = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM field_def WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()[0]
            for offset, kind in enumerate(extra_field_kinds):
                conn.execute(
                    "INSERT INTO field_def (activity_id, kind, label, sort_order)"
                    " VALUES (?, ?, ?, ?)",
                    (activity_id, kind, kind.replace("_", " ").title(), next_sort + offset),
                )

    entry_ids = [entries.create(owner_id, activity_id, {}, tz=tz)["id"] for _ in range(entry_count)]

    with db.connect() as conn:
        conn.execute("BEGIN")
        field_def_ids = {
            r["kind"]: r["id"]
            for r in conn.execute(
                "SELECT id, kind FROM field_def WHERE activity_id = ? ORDER BY sort_order",
                (activity_id,),
            ).fetchall()
        }

    return {
        "category_id": result["category_id"],
        "activity_id": activity_id,
        "entry_ids": entry_ids,
        "field_def_ids": field_def_ids,
    }


def seed_test_account(
    owner_id: int,
    *,
    activities: tuple[dict[str, Any], ...] = ({"name": "Test Activity", "entry_count": 1},),
    tz: ZoneInfo = _UTC,
) -> list[dict[str, Any]]:
    """Create one or more activities for *owner_id* in a single call.

    *activities* is a tuple of kwargs dicts, each forwarded to
    :func:`seed_test_activity` (``name``, ``icon``, ``entry_count``). Default
    is a single activity with one entry — the common "give this account
    something to test against" case. Returns the list of
    :func:`seed_test_activity` results, in the same order as *activities*.
    """
    return [seed_test_activity(owner_id, tz=tz, **spec) for spec in activities]
