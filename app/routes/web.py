"""Web (HTMX) routes for Mushin.

Thin handlers only — business logic lives in app/services/. Full pages render on
initial navigation; fragments swap on interaction (detect via the HX-Request
header). See .claude/rules/web-templates.md for conventions.

Session resolution
-------------------
This router resolves the current user the same way ``app/auth/routes.py``
does (via the signed ``mushin_session`` cookie + ``app.auth.users``), but never
*creates* anything on a bare GET — guest creation stays an explicit
``POST /auth/guest`` the entry screen calls on the user's first tap, per the
bot-guard rule.

Read helpers
------------
``app/services/`` doesn't yet expose a "list my categories/sub-tallies/fields"
view (that's outside this task's owned files), so the small read-only queries
needed to assemble the home screen and the quick-add recipe live here as
private helpers, built on the owner-scoped ``app.services._db`` accessors —
the same pattern ``app/services/stats.py`` uses for field lookups. They contain
no business rules (no counting/streak math — that's ``app/services/stats.py``).
"""

from __future__ import annotations

import calendar as cal
import json
import os
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Cookie, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import ui_strings
from app.auth import sessions, users
from app.models import db
from app.services import (
    _db,
    categories,
    comments,
    competition,
    connections,
    entries,
    profiles,
    search,
    stats,
)
from app.services.entries import EntryNotFoundError, SubTallyNotFoundError

# Cookie holding the user's explicit theme choice: "light" | "dark" | "system".
# Missing/invalid values are treated as "system" (no data-theme attribute, so
# the prefers-color-scheme media query in input.css applies).
THEME_COOKIE = "mushin_theme"
THEME_VALUES = ("light", "dark", "system")
THEME_CYCLE = {"light": "dark", "dark": "system", "system": "light"}

_TAG_PERIOD_LABELS: dict[str, str] = {
    "week": ui_strings.TAG_FREQUENCY_THIS_WEEK,
    "month": ui_strings.TAG_FREQUENCY_THIS_MONTH,
    "year": ui_strings.TAG_FREQUENCY_THIS_YEAR,
}


def _theme_from_cookie(value: str | None) -> str:
    """Normalize the ``mushin_theme`` cookie to a known value, defaulting to "system"."""
    if value in THEME_VALUES:
        return value
    return "system"


def _theme_context(request: Request) -> dict[str, Any]:
    """Context processor: exposes ``theme`` to every template render."""
    return {"theme": _theme_from_cookie(request.cookies.get(THEME_COOKIE))}


def _home_url_for(user: dict[str, Any] | None) -> str:
    """Where "go to my home/profile" should point for *user* (or an anonymous visitor)."""
    if user is None:
        return "/"
    username = user.get("username")
    if username:
        return profiles.canonical_profile_url(username)
    return "/home"


def _home_url_context(request: Request) -> dict[str, Any]:
    """Context processor: exposes ``home_url`` to every template render."""
    session = request.cookies.get(sessions.COOKIE_NAME)
    user = _current_user(session)
    return {"home_url": _home_url_for(user)}


router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates", context_processors=[_theme_context, _home_url_context]
)
# Centralized copy is exposed to every template as `strings` — templates
# never hardcode user-facing text (see .claude/skills/copy-patterns).
templates.env.globals["strings"] = ui_strings


def _format_entry_time(occurred_at: str) -> str:
    """Format the time portion of an ISO8601 ``occurred_at`` string as 12h AM/PM.

    Input: ``"2026-06-16T14:30:00"`` → output: ``"2:30 PM"``.
    Falls back to an empty string on any parse error.
    """
    try:
        dt = datetime.fromisoformat(occurred_at)
        hour = dt.hour
        minute = dt.minute
        period = "AM" if hour < 12 else "PM"
        hour12 = hour % 12 or 12
        return f"{hour12}:{minute:02d} {period}"
    except (ValueError, AttributeError):
        return ""


templates.env.filters["format_entry_time"] = _format_entry_time


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _current_user(session: str | None) -> dict[str, Any] | None:
    """Resolve the session cookie to a user row, or ``None`` if logged out.

    Never mints a guest — that only happens via the explicit
    ``POST /auth/guest`` the entry screen's "그냥 시작하기" button calls.
    """
    uid = sessions.read_uid(session)
    if uid is None:
        return None
    return users.get_user(uid)


# ---------------------------------------------------------------------------
# Read-only view assembly (no business rules — see module docstring)
# ---------------------------------------------------------------------------


def _list_sub_tallies(conn: sqlite3.Connection, owner_id: int) -> list[sqlite3.Row]:
    """Active activities for *owner_id*, joined with their category, ordered
    by category sort_order then activity sort_order."""
    return conn.execute(
        """SELECT st.id, st.name, st.slug, st.count_mode, st.cached_count, st.cached_streak,
                  st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
             FROM activity st
             JOIN category c ON c.id = st.category_id
            WHERE st.owner_id = ?
              AND st.archived_at IS NULL
              AND c.archived_at IS NULL
            ORDER BY c.sort_order, st.sort_order""",
        (owner_id,),
    ).fetchall()


def _field_defs_for_activity(conn: sqlite3.Connection, activity_id: int) -> list[sqlite3.Row]:
    """Recipe fields for an activity, in the stored field-priority order."""
    return conn.execute(
        "SELECT id, kind, label, sort_order FROM field_def"
        " WHERE activity_id = ? ORDER BY sort_order",
        (activity_id,),
    ).fetchall()


_EMPTY_MATCH_ROW: dict[str, str] = {"opponent": "", "score": "", "result": ""}


def _build_card_context(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_row: sqlite3.Row,
    *,
    tz: ZoneInfo,
    selected_tags: set[int] | None = None,
    linked: bool = False,
) -> dict[str, Any]:
    """Assemble the per-card render context: hero, progress, advance line.

    Field-priority order (shared domain rule): hero stat -> progress
    affordance -> advance line. The hero is always the running count — Mushin
    tracks activity and frequency, not tiers or levels.
    """
    activity_id = activity_row["id"]

    progress: dict[str, Any] | None = None
    advance_line: str | None = None
    hero_label = activity_row["cached_count"] or 0

    counts = stats.counts_for_sub_tallies([activity_id], owner_id, tz=tz).get(activity_id, {})
    streak = activity_row["cached_streak"] or 0

    field_defs = _field_defs_for_activity(conn, activity_id)
    fields = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {
            "id": fd["id"],
            "kind": fd["kind"],
            "label": fd["label"],
        }
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = ""
        fields.append(field_ctx)

    slug = activity_row["slug"] if "slug" in activity_row.keys() else None

    return {
        "id": activity_id,
        "slug": slug,
        "category_name": activity_row["category_name"],
        "icon": activity_row["icon"] or categories.DEFAULT_ICON,
        "name": activity_row["name"],
        "show_breadcrumb": activity_row["category_name"] != activity_row["name"],
        # Always "running" — there is no leveling ladder left. Kept as a
        # context key (rather than removed) because some templates still
        # branch on this string; do not drop the key until they're updated.
        "count_mode": "running",
        "hero_label": hero_label,
        "progress": progress,
        "advance_line": advance_line,
        "lifetime": counts.get("lifetime", activity_row["cached_count"] or 0),
        "streak": streak,
        "fields": fields,
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
        "linked": linked,
    }


# ---------------------------------------------------------------------------
# Stats: calendar, heatmap, streak, distributions (detail screen only)
# ---------------------------------------------------------------------------


# Heatmap bucket thresholds: a day's entry count maps to .heat-cell--0..4.
# 0 -> bucket 0 (empty); 1 -> bucket 1; 2 -> bucket 2; 3-4 -> bucket 3; 5+ -> bucket 4.
_HEATMAP_BUCKET_EDGES = (0, 1, 2, 4)


def _heat_bucket(count: int) -> int:
    """Map a day's entry count to a 0..4 heat-cell intensity bucket."""
    if count <= 0:
        return 0
    for bucket, edge in enumerate(_HEATMAP_BUCKET_EDGES[1:], start=1):
        if count <= edge:
            return bucket
    return 4


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last day of *year*-*month*."""
    first = date(year, month, 1)
    last_day = cal.monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _build_calendar_context(
    activity_id: int,
    owner_id: int,
    *,
    year: int,
    month: int,
    tz: ZoneInfo,
    selected: date | None = None,
) -> dict[str, Any]:
    """Month-grid context: weeks of ``.cal-day`` cells, marked + today flags.

    Weeks are Monday-first (matching ``stats._week_start``), padded with
    ``None`` cells for days outside *year*-*month* so the grid stays a regular
    table. Marked days are derived from the activity's entry days for that
    month (one query via ``entries.list_for_activity`` would over-fetch, so we
    use ``stats.heatmap`` only when the month is within the trailing 365 days;
    otherwise we read entries directly).

    *selected*, when given, flags the matching cell's ``selected`` key so the
    template can render ``.cal-day--selected`` on it. Defaults to ``None``
    (no cell selected) for callers that don't track a tapped day.
    """
    first, last = _month_bounds(year, month)
    today = datetime.now(UTC).date()
    # Reuse stats._entry_days via the public heatmap when possible would be
    # awkward for arbitrary months, so read entry days directly (owner-scoped).
    rows = entries.list_for_activity(owner_id, activity_id)
    marked_days: set[date] = set()
    for e in rows:
        d = entries._local_day(e["occurred_at"], tz)
        if first <= d <= last:
            marked_days.add(d)

    weeks: list[list[dict[str, Any] | None]] = []
    week: list[dict[str, Any] | None] = []
    # Monday-first padding before the first day of the month.
    for _ in range(first.weekday()):
        week.append(None)
    cursor = first
    while cursor <= last:
        week.append(
            {
                "date": cursor.isoformat(),
                "day": cursor.day,
                "marked": cursor in marked_days,
                "today": cursor == today,
                "selected": cursor == selected,
            }
        )
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor = cursor + timedelta(days=1)
    if week:
        while len(week) < 7:
            week.append(None)
        weeks.append(week)

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    return {
        "year": year,
        "month": month,
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "weekdays": ui_strings.CALENDAR_WEEKDAYS,
    }


def _entries_on_day(
    activity_id: int, owner_id: int, day: date, *, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """All of an activity's entries (hydrated) whose local day in *tz* is *day*."""
    rows = entries.list_for_activity(owner_id, activity_id)
    return [e for e in rows if entries._local_day(e["occurred_at"], tz) == day]


def _resolve_comment_deep_link(
    raw_c: str | None, *, activity_id: int, owner_id: int, tz: ZoneInfo
) -> tuple[int, date] | None:
    """Resolve a ``?c={entry_id}`` query param to ``(entry_id, local_day)``.

    Used by a notification click-through to land the viewer on the right
    calendar day with that entry's comment thread pre-expanded. Returns
    ``None`` — silently, no error — when *raw_c* is missing, non-numeric, or
    resolves to an entry that doesn't exist or belongs to a different
    activity/owner; the caller falls back to no day selected and no expand,
    matching the old flat-list ``?c=`` behavior this replaces.
    """
    if raw_c is None:
        return None
    try:
        entry_id = int(raw_c)
    except ValueError:
        return None
    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return None
    if entry["activity_id"] != activity_id:
        return None
    return entry_id, entries._local_day(entry["occurred_at"], tz)


def _decorate_comment_counts(
    log: list[dict[str, Any]], day_entries: list[dict[str, Any]] | None
) -> None:
    """Mutate ``log``'s and ``day_entries``' entry dicts in place, adding ``comment_count``.

    Opens its own connection — this module's other history helpers (e.g.
    ``entries.list_for_activity``, ``stats.period_entries``) already each open
    their own short-lived connection rather than share one with the caller, and
    no caller of ``_build_history_context`` holds a connection open across the
    call (both ``activity_detail`` callers explicitly close their connection
    first) — so opening one more short transaction here matches the existing
    pattern instead of threading a connection through every helper.
    """
    all_entries: list[dict[str, Any]] = [e for group in log for e in group["entries"]]
    if day_entries is not None:
        all_entries.extend(day_entries)
    if not all_entries:
        return
    entry_ids = [e["id"] for e in all_entries]
    with db.connect() as conn:
        conn.execute("BEGIN")
        counts = comments.counts_for_entries(conn, entry_ids)
    for e in all_entries:
        e["comment_count"] = counts.get(e["id"], 0)


def _build_history_context(
    activity_id: int,
    owner_id: int,
    *,
    period: str,
    anchor: date,
    tz: ZoneInfo,
    selected: date | None = None,
    is_owner: bool = False,
    can_comment: bool = False,
    username: str | None = None,
    slug: str | None = None,
    expand_comment_entry_id: int | None = None,
    login_redirect_url: str | None = None,
) -> dict[str, Any]:
    """History view context for *period* (``week``/``month``/``year``/``all``) at *anchor*.

    ``visual`` is shaped per period: a calendar grid (month), a single week of
    day-cells (week), or a bucketed heatmap series (year). For ``all``, there is
    no visual and no prev/next navigation — only the full day-grouped log.
    ``log`` groups the period's entries by local day (in *tz*), newest day first,
    for the chronological log.

    *selected*, when given (``week`` or ``month`` period — ``year``'s heatmap
    cells deliberately have no day-select), flags the matching cell/day and
    populates ``selected_day``/``day_entries`` with that day's detail.

    Every entry dict in ``log`` and ``day_entries`` carries a ``comment_count``
    key (via ``comments.counts_for_entries``), so a template can render the
    comment affordance without a separate per-entry lookup.

    *is_owner*, *can_comment*, *username*, *slug* are passed straight through
    into the returned context unchanged — this function does no capability
    checking of its own (that's the caller's job, via
    ``app/services/profiles.py``). *username*/*slug* are ``None`` when the
    activity has no public URL (e.g. a guest-owned account); pass ``None``
    faithfully rather than substituting a fallback — templates are responsible
    for suppressing comment affordances when either is ``None``.

    *expand_comment_entry_id*, when given, is a ``?c={entry_id}`` deep-link
    target (see ``_resolve_comment_deep_link``) — the caller is responsible
    for validating it belongs to this activity/owner and for setting
    *selected* to the day that contains it. Passed straight through into the
    returned context; ``components/day_entries.html.jinja2`` auto-expands the
    matching entry's comment slot on render when it equals an entry's id.

    *login_redirect_url*, when given, is an already-validated (via
    ``profiles.safe_next_path``) ``/login?next=...`` URL for an anonymous
    viewer who can read this activity but can't comment (``can_comment`` is
    ``False`` precisely because there's no session — see
    ``profiles.can_comment_on_entry``). Passed straight through; the caller
    is responsible for only ever constructing it on the already-capability-
    cleared read-only path, never for a blocked/limited viewer (who never
    reaches this function at all).
    """
    if period == "all":
        all_rows = entries.list_for_activity(owner_id, activity_id)
        by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for row in all_rows:
            by_day[entries._local_day(row["occurred_at"], tz)].append(row)
        log = [
            {"day": day.isoformat(), "entries": day_entries}
            for day, day_entries in sorted(by_day.items(), reverse=True)
        ]
        _decorate_comment_counts(log, None)
        return {
            "period": "all",
            "anchor": anchor.isoformat(),
            "label": None,
            "visual": None,
            "log": log,
            "prev_anchor": None,
            "next_anchor": None,
            "start": None,
            "end": None,
            "selected_day": None,
            "day_entries": None,
            "is_owner": is_owner,
            "can_comment": can_comment,
            "username": username,
            "slug": slug,
            "expand_comment_entry_id": expand_comment_entry_id,
            "login_redirect_url": login_redirect_url,
        }

    start = stats._shift_period(anchor, period, 0)
    end = stats._shift_period(anchor, period, 1) - timedelta(days=1)
    today = datetime.now(UTC).date()

    if period == "month":
        visual: dict[str, Any] = _build_calendar_context(
            activity_id,
            owner_id,
            year=start.year,
            month=start.month,
            tz=tz,
            selected=selected,
        )
        label = f"{start.year}.{start.month:02d}"
    elif period == "week":
        series = stats.heatmap_range(activity_id, owner_id, start, end, tz=tz)
        marked_days = {date.fromisoformat(d["date"]) for d in series if d["count"] > 0}
        days_cells = []
        cursor = start
        while cursor <= end:
            days_cells.append(
                {
                    "date": cursor.isoformat(),
                    "day": cursor.day,
                    "marked": cursor in marked_days,
                    "today": cursor == today,
                    "selected": cursor == selected,
                }
            )
            cursor += timedelta(days=1)
        visual = {"days": days_cells}
        label = f"{start.isoformat()} – {end.isoformat()}"
    elif period == "year":
        series = stats.heatmap_range(activity_id, owner_id, start, end, tz=tz)
        cells = [{"date": d["date"], "bucket": _heat_bucket(d["count"])} for d in series]
        visual = {"cells": cells}
        label = f"{start.year}"
    else:
        raise ValueError(f"unknown period {period!r}; expected week/month/year/all")

    period_rows = stats.period_entries(activity_id, owner_id, start, end, tz=tz)
    by_day = defaultdict(list)
    for row in period_rows:
        by_day[entries._local_day(row["occurred_at"], tz)].append(row)

    log = [
        {"day": day.isoformat(), "entries": day_entries}
        for day, day_entries in sorted(by_day.items(), reverse=True)
    ]

    prev_anchor = stats._shift_period(anchor, period, -1).isoformat()
    next_anchor = stats._shift_period(anchor, period, 1).isoformat()

    selected_day = selected.isoformat() if selected is not None else None
    day_entries = (
        _entries_on_day(activity_id, owner_id, selected, tz=tz) if selected is not None else None
    )

    _decorate_comment_counts(log, day_entries)

    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "label": label,
        "visual": visual,
        "log": log,
        "prev_anchor": prev_anchor,
        "next_anchor": next_anchor,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "selected_day": selected_day,
        "day_entries": day_entries,
        "is_owner": is_owner,
        "can_comment": can_comment,
        "username": username,
        "slug": slug,
        "expand_comment_entry_id": expand_comment_entry_id,
        "login_redirect_url": login_redirect_url,
    }


def _build_field_stats_context(
    activity_id: int,
    owner_id: int,
    field_defs: list[sqlite3.Row],
    *,
    tz: ZoneInfo,
    period: str = "month",
) -> dict[str, Any]:
    """Tag-frequency and scale-distribution sections for the fields that exist."""
    tag_groups = []
    scales = []
    for fd in field_defs:
        if fd["kind"] == "tag_group":
            freq = stats.tag_frequency(activity_id, owner_id, fd["id"], tz=tz, period=period)
            tag_groups.append({"label": fd["label"], "tags": freq["tags"]})
        elif fd["kind"] == "scale":
            dist = stats.scale_distribution(activity_id, owner_id, fd["id"])
            scales.append({"label": fd["label"], **dist})
    return {
        "tag_groups": tag_groups,
        "scales": scales,
        "period": period,
        "period_label": _TAG_PERIOD_LABELS.get(period, ui_strings.TAG_FREQUENCY_THIS_MONTH),
    }


# ---------------------------------------------------------------------------
# Entry screen + home
# ---------------------------------------------------------------------------


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    """The privacy policy page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/privacy.html.jinja2",
        context={},
    )


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """First-run entry screen, or the character-sheet home for a known session."""
    user = _current_user(session)
    if user is None:
        demo_username = os.getenv("DEMO_PROFILE_USERNAME", "")
        return templates.TemplateResponse(
            request=request,
            name="web/entry.html.jinja2",
            context={"active": "login", "demo_username": demo_username, "next": None},
        )
    return await _render_home(request, user)


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login(
    request: Request,
    next: str | None = None,  # noqa: A002 - query-param name is part of the public URL contract
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Dedicated login entry point that preserves a post-login redirect target.

    ``?next=`` is the page the visitor was trying to act on (e.g. an
    anonymous comment attempt on a public activity) — validated via
    ``profiles.safe_next_path`` so an attacker-supplied value can never become
    an open redirect; an unsafe or missing value silently falls back to no
    redirect target rather than erroring. A caller already logged in is sent
    straight to the (validated) target, or their home/profile if there is
    none — there's nothing to log into here.
    """
    safe_next = profiles.safe_next_path(next)
    user = _current_user(session)
    if user is not None:
        return RedirectResponse(url=safe_next or _home_url_for(user), status_code=303)

    demo_username = os.getenv("DEMO_PROFILE_USERNAME", "")
    return templates.TemplateResponse(
        request=request,
        name="web/entry.html.jinja2",
        context={"active": "login", "demo_username": demo_username, "next": safe_next},
    )


@router.get("/auth/login-form", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    """The Log in tab's fragment — swapped into ``#auth-form`` by the entry-screen toggle.

    Renders standalone (re-asserts the toggle with "Log in" selected) so a
    direct fragment load isn't visually orphaned.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/auth_login_form.html.jinja2",
        context={"active": "login"},
    )


@router.get("/auth/create-form", response_class=HTMLResponse)
async def create_form(request: Request) -> HTMLResponse:
    """The Create account tab's fragment — swapped into ``#auth-form`` by the entry-screen toggle.

    Renders standalone (re-asserts the toggle with "Create account" selected)
    so a direct fragment load isn't visually orphaned.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/auth_create_form.html.jinja2",
        context={"active": "create"},
    )


@router.get("/home", response_class=HTMLResponse)
async def home(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """The character-sheet home. Redirects to the entry screen with no session.

    Renders in place for everyone (guest or real user) once past the
    one-time visibility-consent gate for non-guest accounts.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    gate = consent_gate_redirect(user)
    if gate is not None:
        return gate
    return await _render_home(request, user)


def consent_gate_redirect(user: dict[str, Any]) -> RedirectResponse | None:
    """One-time consent gating for a logged-in owner, or ``None`` to proceed.

    Two ordered, fail-once gates for non-guest accounts (guests have no public
    profile and are never gated):

    1. **First-run visibility consent** — ``consent_seen_at IS NULL`` → send to
       ``/welcome-sharing``. This takes precedence so a brand-new account picks
       a visibility under the current three-tier copy.
    2. **Private redefinition re-consent** — a pre-existing private account
       (``visibility='private' AND private_redefinition_seen_at IS NULL``) →
       send to ``/visibility-update`` once.

    New users never hit gate 2: ``users.set_visibility_consent`` (the
    welcome-sharing / account-settings write path) stamps
    ``private_redefinition_seen_at`` at the same moment it stamps
    ``consent_seen_at``, so by the time they clear gate 1 the redefinition flag
    is already set. Gate 2 therefore fires only for accounts that chose
    ``private`` under the old "nothing shown" copy. Shared verbatim by the owner
    branch of ``GET /@{username}`` in ``app/routes/public.py``.
    """
    if user["auth_provider"] == "guest":
        return None
    if user["consent_seen_at"] is None:
        return RedirectResponse(url="/welcome-sharing", status_code=303)
    if user["visibility"] == "private" and user["private_redefinition_seen_at"] is None:
        return RedirectResponse(url="/visibility-update", status_code=303)
    return None


def _build_fellows_context(
    profile_user_id: int,
    *,
    viewer_id: int | None,
    is_owner: bool,
) -> dict[str, Any]:
    """Assemble the ``fellows_section`` context for *profile_user_id*'s page.

    Names-vs-count rule: the fellow list's ``@username`` rows are shown only
    to the profile owner and to a viewer who is themselves a mutual fellow of
    that profile — every other viewer (stranger, logged-out, pending) gets
    only the ``fellow_count`` number, never the clickable names (so a private
    fellow can't be outed by association). The owner additionally gets the
    requests cluster (incoming/outgoing pending) and a content-free pending
    count badge.
    """
    fellows = connections.list_fellows(profile_user_id)
    is_mutual_fellow = (
        not is_owner
        and viewer_id is not None
        and connections.relationship_state(viewer_id, profile_user_id) == "fellow"
    )
    show_names = is_owner or is_mutual_fellow

    context: dict[str, Any] = {
        "fellow_count": len(fellows),
        "fellows": fellows if show_names else [],
        "show_fellow_names": show_names,
        "is_owner": is_owner,
        "profile_user_id": profile_user_id,
    }

    if is_owner:
        context["incoming_requests"] = connections.list_incoming_pending(profile_user_id)
        context["outgoing_requests"] = connections.list_outgoing_pending(profile_user_id)
        context["pending_count"] = connections.pending_count(profile_user_id)
    else:
        context["incoming_requests"] = []
        context["outgoing_requests"] = []
        context["pending_count"] = 0

    return context


def _build_home_context(conn: sqlite3.Connection, owner_id: int, tz: ZoneInfo) -> dict[str, Any]:
    """Assemble the owner-dashboard context: cards (linked) + example categories.

    Shared by ``_render_home`` (``GET /home``) and the unified profile route
    (``GET /@{username}`` in ``app/routes/public.py``) so the owner-rendering
    logic lives in exactly one place. Takes an already-open connection per
    ``app/models/db.py`` convention (one connection per request).

    Also reads the unseen-comment count (``comments.unseen_comment_count``,
    derived live against the ``comments_seen_at`` watermark — no stored
    notification entity) for the home badge. Home **never writes**
    ``comments_seen_at`` — the badge only clears once the owner actually
    visits ``GET /comments`` (the dedicated notification-history page), which
    is the sole place that watermark advances. Stamping it on every home load
    made the badge show a count once and vanish before the owner could act on
    it; see ``comments`` route for the fix.
    """
    sub_tallies = _list_sub_tallies(conn, owner_id)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=True) for row in sub_tallies]
    fellows_context = _build_fellows_context(owner_id, viewer_id=owner_id, is_owner=True)

    unseen_comments = comments.unseen_comment_count(conn, owner_id)

    return {
        "cards": cards,
        "examples": categories.EXAMPLE_CATEGORIES,
        "fellows": fellows_context,
        "unseen_comments": unseen_comments,
    }


async def _render_home(request: Request, user: dict[str, Any]) -> HTMLResponse:
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        context = _build_home_context(conn, owner_id, tz)

    return templates.TemplateResponse(
        request=request,
        name="web/home.html.jinja2",
        context=context,
    )


# ---------------------------------------------------------------------------
# Comment notification history
# ---------------------------------------------------------------------------


@router.get("/comments", response_class=HTMLResponse)
async def comments_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
    before_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    """The dedicated comment-notification history — the only place the
    ``comments_seen_at`` watermark advances.

    Order matters and is the entire point of this route: read the
    pre-visit watermark, use it to compute each row's ``is_new``, render,
    THEN advance the watermark. Stamping first (as the old ``home`` handler
    did) would make every row compute as already-seen on its own render.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    gate = consent_gate_redirect(user)
    if gate is not None:
        return gate

    owner_id = int(user["id"])
    with db.connect() as conn:
        conn.execute("BEGIN")
        watermark_row = conn.execute(
            "SELECT comments_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()
        watermark = watermark_row["comments_seen_at"] if watermark_row else None

        rows = comments.list_comments_for_owner(
            conn, owner_id, before_id=before_id, watermark=watermark
        )

        conn.execute(
            "UPDATE user SET comments_seen_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), owner_id),
        )

    has_more = len(rows) == 50
    next_before_id = rows[-1]["comment_id"] if has_more and rows else None

    return templates.TemplateResponse(
        request=request,
        name="web/comments.html.jinja2",
        context={
            "comments": rows,
            "username": user["username"],
            "has_more": has_more,
            "next_before_id": next_before_id,
        },
    )


# ---------------------------------------------------------------------------
# Visibility consent (one-time, before first /home use)
# ---------------------------------------------------------------------------


@router.get("/welcome-sharing", response_class=HTMLResponse)
async def welcome_sharing(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """The one-time visibility-consent screen.

    Shown once to every non-guest account before they can use ``/home``: it
    explains the new ``visibility`` setting plainly and lets them choose
    ``public`` or ``private`` (private pre-selected). Once chosen, the gate in
    ``home()`` never sends them here again. Guests have no public profile and
    are bounced straight to ``/home``.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if user["auth_provider"] == "guest" or user["consent_seen_at"] is not None:
        return RedirectResponse(url=_home_url_for(user), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="web/welcome_sharing.html.jinja2",
        context={},
    )


@router.post("/welcome-sharing", response_model=None)
async def submit_welcome_sharing(
    visibility: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Persist the user's one-time visibility choice, then go to ``/home``.

    Validates *visibility* is ``'public'`` or ``'private'`` (400 otherwise),
    writes ``user.visibility`` + ``user.consent_seen_at`` for the session user,
    and redirects to ``/home`` (which now passes the consent gate).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    return RedirectResponse(url=_home_url_for(user), status_code=303)


# ---------------------------------------------------------------------------
# Private redefinition (one-time re-consent interstitial)
# ---------------------------------------------------------------------------


@router.get("/visibility-update", response_class=HTMLResponse, response_model=None)
async def visibility_update(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """The one-time "what Private means has changed" interstitial.

    Shown once to a pre-existing private account whose meaning of ``private``
    changed under them. Self-guards the same way ``welcome_sharing`` does: a
    guest, a still-unconsented account (gate 1 owns them), a public account, or
    an account that has already acknowledged the change is bounced straight
    home — so a direct visit can't show the screen out of turn.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if (
        user["auth_provider"] == "guest"
        or user["consent_seen_at"] is None
        or user["visibility"] != "private"
        or user["private_redefinition_seen_at"] is not None
    ):
        return RedirectResponse(url=_home_url_for(user), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="web/visibility_update.html.jinja2",
        context={},
    )


@router.post("/visibility-update", response_model=None)
async def submit_visibility_update(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Acknowledge the private-redefinition interstitial, then go to ``/home``.

    Stamps ``private_redefinition_seen_at`` for the session user via
    ``users.mark_redefinition_seen`` so the re-consent gate never fires again,
    then redirects to the owner's home/profile URL. No body to validate — this
    is a single affirmative acknowledgement, not a re-choice.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    users.mark_redefinition_seen(int(user["id"]))
    return RedirectResponse(url=_home_url_for(user), status_code=303)


# ---------------------------------------------------------------------------
# Account settings (/account) — visibility toggle
# ---------------------------------------------------------------------------


@router.get("/account", response_class=HTMLResponse, response_model=None)
async def account_settings(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Account settings page.

    Shows the visibility toggle and the ``/@{username}`` share-link line for
    non-guest accounts; guests (no ``username``, no public profile) see neither
    — the section is suppressed entirely in the template.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    is_guest = user["auth_provider"] == "guest"
    return templates.TemplateResponse(
        request=request,
        name="web/account.html.jinja2",
        context={
            "is_guest": is_guest,
            "username": user["username"],
            "visibility": user["visibility"],
        },
    )


@router.post("/account/visibility", response_model=None)
async def update_visibility(
    visibility: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account's ``visibility`` from the settings page.

    Validates *visibility* against ``users.VALID_VISIBILITIES`` (400 otherwise),
    persists via ``users.set_visibility_consent`` (re-stamping ``consent_seen_at``
    is idempotent — the user already passed the one-time screen), and redirects
    back to ``/account``. Guests have no public profile and cannot toggle.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    return RedirectResponse(url="/account", status_code=303)


# ---------------------------------------------------------------------------
# Create activity
# ---------------------------------------------------------------------------


@router.get("/activities/new", response_class=HTMLResponse)
async def new_activity(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Manual create-activity form: name only, rendered as an inline sheet.

    Both home-page entry points ("+ Add activity" and "start from scratch")
    open this same HTMX sheet fragment — there is no standalone full-page
    create-activity route.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="components/category_sheet.html.jinja2",
        context={},
    )


@router.post("/activities", response_class=HTMLResponse)
async def create_activity(
    request: Request,
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create a general-log activity (manual form or one-tap example adopt).

    Returns the new ``activity_card`` fragment for an HTMX swap into
    ``#cards``, or a 303 to ``/home`` for the no-JS path.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    name = name.strip()
    if not name:
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request=request,
                name="components/category_form.html.jinja2",
                context={
                    "hx_post": "/activities",
                    "hx_target": "#cards",
                    "hx_swap": "beforeend",
                    "name_error": ui_strings.ACTIVITY_FORM_NAME_REQUIRED,
                },
                status_code=400,
            )

        return RedirectResponse(url="/home", status_code=303)

    tz = users.get_user_timezone(owner_id)
    result = categories.create_activity(owner_id, name=name)

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (result["activity_id"], owner_id),
        ).fetchone()
        card = _build_card_context(conn, owner_id, sub_row, tz=tz, linked=True)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="components/activity_card.html.jinja2",
            context={"card": card},
        )

    return RedirectResponse(url=_home_url_for(user), status_code=303)


# ---------------------------------------------------------------------------
# Activity detail
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}", response_class=HTMLResponse, response_model=None)
async def activity_detail(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Activity detail screen: card + (for tournament activities) competition stats.

    Active activities with a slug redirect 301 to ``/@{username}/{slug}``
    (the canonical public/private unified URL).  Archived activities, or those
    somehow without a slug, render the dashboard in place — this preserves access
    to archived activities that are no longer addressable via the public route.

    Competition stats only render for activities whose recipe includes a
    ``match_list`` field (e.g. 검도 / 시합).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        if row is None:
            return HTMLResponse(status_code=404)

        # Redirect active, slugged activities to the canonical URL —
        # only when the owner has a username (guests have username=None and
        # have no public profile URL to redirect to).
        username = user.get("username")
        if username is not None and row["slug"] is not None and row["archived_at"] is None:
            return RedirectResponse(
                url=profiles.canonical_activity_url(username, row["slug"]), status_code=301
            )

        sub_row = conn.execute(
            """SELECT st.id, st.name, st.slug, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
        has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
        card = _build_card_context(conn, owner_id, sub_row, tz=tz)

    context: dict[str, Any] = {"card": card}

    if has_match_list:
        context["record"] = competition.record(owner_id, activity_id)
        context["timeline"] = competition.results_timeline(owner_id, activity_id)
        context["head_to_head"] = competition.head_to_head(owner_id, activity_id)
    else:
        context["record"] = None
        context["timeline"] = []
        context["head_to_head"] = []

    today = datetime.now(UTC).date()

    # `?c={entry_id}` (a notification click-through) pre-selects that entry's
    # calendar day and pre-expands its comment thread. Silently ignored — no
    # error, no 500 — when missing/non-numeric/unknown/cross-activity.
    deep_link = _resolve_comment_deep_link(
        request.query_params.get("c"), activity_id=activity_id, owner_id=owner_id, tz=tz
    )
    expand_comment_entry_id, selected_day = deep_link if deep_link is not None else (None, None)

    context["activity_id"] = activity_id
    context["counts"] = stats.counts(activity_id, owner_id, tz=tz)
    context["streaks"] = stats.streaks(activity_id, owner_id, tz=tz)
    context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=selected_day or today,
        tz=tz,
        selected=selected_day,
        is_owner=True,
        can_comment=True,
        username=username,
        slug=sub_row["slug"],
        expand_comment_entry_id=expand_comment_entry_id,
    )
    context["field_stats"] = _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz)
    context["public_notice"] = None
    context["preview_visitor_url"] = None
    context["is_owner"] = True

    return templates.TemplateResponse(
        request=request,
        name="web/activity_detail.html.jinja2",
        context=context,
    )


# ---------------------------------------------------------------------------
# Inline rename (activity heading)
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/rename-form", response_class=HTMLResponse)
async def rename_form(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline rename form fragment for *activity_id*.

    Detected as an HTMX fragment — the caller swaps ``#rename-heading``
    with the returned form via ``hx-swap="outerHTML"``.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
    if row is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/rename_form.html.jinja2",
        context={"activity_id": activity_id, "current_name": row["name"]},
    )


@router.get("/activities/{activity_id}/rename-form-cancel", response_class=HTMLResponse)
async def rename_form_cancel(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the plain heading fragment (cancel path).

    Swaps ``#rename-heading`` back to the read-only heading without a page reload.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
    if row is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/rename_heading.html.jinja2",
        context={"activity_id": activity_id, "current_name": row["name"]},
    )


@router.post("/activities/{activity_id}/rename", response_class=HTMLResponse, response_model=None)
async def rename_activity(
    request: Request,
    activity_id: int,
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Rename *activity_id* and redirect to the new canonical URL.

    On success: 200 with ``HX-Redirect`` to ``/@{username}/{new_slug}``.
    On ``SubTallyNotFoundError``: 404.
    On ``ValueError`` (empty / too-long name): return the rename form fragment
    with an inline error message (no 400 full-page, preserves the HTMX context).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    try:
        with db.connect() as conn:
            conn.execute("BEGIN")
            new_slug = categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name=name
            )
    except SubTallyNotFoundError:
        return HTMLResponse(status_code=404)
    except ValueError as exc:
        # Return the inline form with a validation error — never a bare 400.
        return templates.TemplateResponse(
            request=request,
            name="components/rename_form.html.jinja2",
            context={
                "activity_id": activity_id,
                "current_name": name,
                "error": str(exc),
            },
            status_code=422,
        )

    username = user.get("username")
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(username, new_slug)
    return response


# ---------------------------------------------------------------------------
# Category delete (two-step confirm from rename form)
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/delete-confirm", response_class=HTMLResponse)
async def category_delete_confirm(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline delete-confirm fragment for the category that owns *activity_id*.

    Ownership check: the sub-tally must exist and belong to the session user — 404 otherwise.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, name FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
    if row is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/category_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "activity_name": row["name"]},
    )


@router.post("/activities/{activity_id}/delete", response_class=HTMLResponse)
async def delete_category(
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete the category (and all sub-tallies/entries) that owns *activity_id*.

    On success (or if already gone): ``HX-Redirect`` to the owner's home/profile
    URL with status 200. Non-owner or unknown sub-tally: 404.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT category_id FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
        if row is None:
            return HTMLResponse(status_code=404)
        categories.delete_category(conn, owner_id=owner_id, category_id=row["category_id"])

    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = _home_url_for(user)
    return response


@router.get("/activities/{activity_id}/history", response_class=HTMLResponse)
async def activity_history(
    request: Request,
    activity_id: int,
    period: str,
    anchor: str | None = None,
    day: str | None = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the history fragment (visual + log) for *period* at *anchor*.

    *day*, when given, selects a calendar cell (month period) and includes
    that day's entries in the returned fragment.

    Shared by the owner dashboard AND every interactive control inside the
    same ``components/history.html.jinja2`` partial rendered read-only on
    ``/@{username}/{slug}`` (period tabs, prev/next nav, day-select taps, the
    "Calendar" back-control) — so the viewer here is not assumed to be the
    activity's owner. The activity's real owner is resolved from
    ``activity_id`` alone, then ``profiles.viewer_capability`` /
    ``can_view_activity_detail`` (the same fail-closed authority
    ``app/routes/public.py`` uses for the initial page load) decides whether
    *this* viewer — owner, fellow, public visitor, or anonymous — may see it
    at all. A denied viewer (blocked, or limited-without-detail-access) gets
    404, matching the no-existence-oracle behavior the rest of the read-only
    surface uses; this never reveals whether the activity exists to someone
    who isn't allowed to know.

    Owner behavior is unchanged byte-for-byte: ``is_owner=True``,
    ``can_comment=True``, username/slug from the owner's own row. A non-owner
    viewer gets ``is_owner=False`` and ``can_comment`` from
    ``can_comment_on_entry`` (always ``False`` for an anonymous viewer, since
    that helper requires a session) — and, per the context-shape safety rule,
    no write-action context key is ever constructed for a non-owner response.
    """
    current_uid = sessions.read_uid(session)

    if period not in ("week", "month", "year", "all"):
        return HTMLResponse(status_code=400)

    if anchor is None:
        anchor_date = datetime.now(UTC).date()
    else:
        try:
            anchor_date = date.fromisoformat(anchor)
        except ValueError:
            return HTMLResponse(status_code=400)

    if day is None:
        selected_date = None
    else:
        try:
            selected_date = date.fromisoformat(day)
        except ValueError:
            return HTMLResponse(status_code=400)

    with db.connect() as conn:
        conn.execute("BEGIN")
        owner_row = conn.execute(
            """SELECT u.id, u.username, u.visibility, u.auth_provider, u.consent_seen_at,
                      st.slug AS activity_slug
                 FROM activity st
                 JOIN user u ON u.id = st.owner_id
                WHERE st.id = ?""",
            (activity_id,),
        ).fetchone()
        if owner_row is None:
            return HTMLResponse(status_code=404)

        profile_user = {
            "id": owner_row["id"],
            "username": owner_row["username"],
            "visibility": owner_row["visibility"],
            "auth_provider": owner_row["auth_provider"],
            "consent_seen_at": owner_row["consent_seen_at"],
        }
        owner_id = int(profile_user["id"])

        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )
        is_owner = cap == "owner"

        if not is_owner and not profiles.can_view_activity_detail(
            conn, current_user_id=current_uid, profile_user=profile_user
        ):
            # "blocked" or "limited" (non-connected visitor on a non-public
            # account) — fail closed, no existence oracle.
            return HTMLResponse(status_code=404)

        can_comment = (
            True
            if is_owner
            else profiles.can_comment_on_entry(
                conn,
                current_user_id=current_uid,
                profile_user=profile_user,
                activity_id=activity_id,
            )
        )

    tz = users.get_user_timezone(owner_id)
    username = profile_user["username"]
    slug = owner_row["activity_slug"]

    # Anonymous (no session) real visitor on an already-cleared-readable
    # activity (blocked/limited 404s above before this point) — same
    # "log in to comment" prompt the initial page load gets
    # (`public.py::_render_readonly_activity_detail`), threaded through this
    # interactive fragment route too, since a visitor can reach a fresh
    # period/day swap without ever re-loading the full page. `next` points at
    # the canonical activity page (not this fragment URL, which isn't a
    # navigable page on its own), built from `username`/`slug` rather than
    # `request.url.path` — both are already-trusted server-derived strings, so
    # `safe_next_path` here is defense in depth, not the primary guarantee.
    login_redirect_url = None
    if not is_owner and current_uid is None and username is not None and slug is not None:
        target = profiles.safe_next_path(profiles.canonical_activity_url(username, slug))
        login_redirect_url = f"/login?next={quote(target or '', safe='')}"

    history_ctx = _build_history_context(
        activity_id,
        owner_id,
        period=period,
        anchor=anchor_date,
        tz=tz,
        selected=selected_date,
        is_owner=is_owner,
        can_comment=can_comment,
        username=username,
        slug=slug,
        login_redirect_url=login_redirect_url,
    )
    response = templates.TemplateResponse(
        request=request,
        name="components/history.html.jinja2",
        context={
            "activity_id": activity_id,
            "history": history_ctx,
            "is_owner": is_owner,
            "can_comment": can_comment,
            "username": username,
            "slug": slug,
            "login_redirect_url": login_redirect_url,
        },
    )
    if period != "all":
        response.headers["HX-Trigger"] = json.dumps({"history-period-changed": {"period": period}})
    return response


@router.get("/activities/{activity_id}/stats-summary", response_class=HTMLResponse)
async def stats_summary_fragment(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Stats summary fragment for HTMX refresh after a log."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/stats_summary.html.jinja2",
        context={
            "activity_id": activity_id,
            "counts": stats.counts(activity_id, owner_id, tz=tz),
            "streaks": stats.streaks(activity_id, owner_id, tz=tz),
            "is_owner": True,
        },
    )


@router.get("/activities/{activity_id}/field-stats", response_class=HTMLResponse)
async def field_stats_fragment(
    request: Request,
    activity_id: int,
    period: str = "month",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Tag-frequency + scale-distribution fragment for HTMX refresh after a log or period change."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    if period not in ("week", "month", "year"):
        period = "month"
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
    return templates.TemplateResponse(
        request=request,
        name="components/field_stats.html.jinja2",
        context={
            "activity_id": activity_id,
            "field_stats": _build_field_stats_context(
                activity_id, owner_id, field_defs, tz=tz, period=period
            ),
            "is_owner": True,
        },
    )


# ---------------------------------------------------------------------------
# Entry edit-in-place
# ---------------------------------------------------------------------------


def _build_edit_fields_context(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_id: int,
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the fields context for the entry edit form.

    Mirrors _build_card_context's field assembly, but pre-fills values and
    tag selections from the existing entry instead of leaving them blank.
    """
    field_defs = _field_defs_for_activity(conn, activity_id)

    # Index entry values by field_def_id for quick lookup.
    entry_values: dict[int, dict[str, Any]] = {}
    for ev in entry.get("values") or []:
        entry_values[ev["field_def_id"]] = ev

    fields: list[dict[str, Any]] = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {
            "id": fd["id"],
            "kind": fd["kind"],
            "label": fd["label"],
        }
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = entry.get("memo") or ""
        elif fd["kind"] in ("count", "scale"):
            ev = entry_values.get(fd["id"])
            if ev is not None and ev.get("num_value") is not None:
                field_ctx["prefilled_value"] = ev["num_value"]
            else:
                field_ctx["prefilled_value"] = ""
        # memo: rendered directly from entry.memo in the template.
        # match_list / level / result: not editable in v1 of the edit form.
        fields.append(field_ctx)

    return fields


def _render_entry_row(
    request: Any,
    activity_id: int,
    owner_id: int,
    entry: dict[str, Any],
) -> HTMLResponse:
    """Return the read-only entry row fragment after a successful edit or cancel.

    is_owner/can_comment are always True here (only the owner ever reaches
    the edit/cancel-edit routes — same reasoning as activity_detail's
    owner-only branch). username/slug are looked up the same way
    activity_detail does, via the session user's username and
    profiles.get_activity_for_owner's slug, so the comment toggle keeps its
    `/@{username}/{slug}/...` URL after the swap. entry["comment_count"] is
    decorated via comments.counts_for_entries — the same helper
    _decorate_comment_counts uses for the full history context — rather
    than a fresh query, so the toggle's live count matches what the rest of
    the calendar/log shows.
    """
    user = users.get_user(owner_id)
    username = user.get("username") if user is not None else None

    with db.connect() as conn:
        conn.execute("BEGIN")
        activity_row = profiles.get_activity_for_owner(
            conn, activity_id=activity_id, owner_id=owner_id
        )
        slug = activity_row["slug"] if activity_row is not None else None
        counts = comments.counts_for_entries(conn, [entry["id"]])

    entry = dict(entry)
    entry["comment_count"] = counts.get(entry["id"], 0)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_row.html.jinja2",
        context={
            "activity_id": activity_id,
            "entry": entry,
            "username": username,
            "slug": slug,
        },
    )


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/edit",
    response_class=HTMLResponse,
)
async def get_entry_edit_form(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the edit form fragment for *entry_id* under *activity_id*.

    Ownership checks (in order):
    1. Session required — 401 if not authenticated.
    2. Entry must exist for this owner — 404 via EntryNotFoundError.
    3. Entry must belong to the requested activity_id — 404 on mismatch.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fields = _build_edit_fields_context(conn, owner_id, activity_id, entry)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_edit_form.html.jinja2",
        context={"activity_id": activity_id, "entry": entry, "fields": fields},
    )


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/cancel-edit",
    response_class=HTMLResponse,
)
async def cancel_entry_edit(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the read-only entry row fragment (cancel path).

    Same ownership checks as the edit GET.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return _render_entry_row(request, activity_id, owner_id, entry)


@router.post(
    "/activities/{activity_id}/entries/{entry_id}",
    response_class=HTMLResponse,
)
async def update_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Update *entry_id* and return the refreshed read-only row fragment.

    Parses occurred_at (date-only), memo, tag selections, and scalar values
    from the form. ``time_known`` handling: if a ``time`` field is present and
    non-empty, combine date+time (time_known=1); if the time field is empty or
    absent, use midnight (time_known=0 — Task 6 adds the time UI, so for now
    the field is never submitted and we default to midnight).

    Ownership checks are the same as the GET.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    try:
        existing = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if existing["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    form = await request.form()

    # --- occurred_at + time_known -------------------------------------------
    occurred_at, time_known = _resolve_occurred_at(
        str(form.get("date") or "").strip(),
        str(form.get("time") or "").strip(),
        tz=tz,
    )

    # --- field values -------------------------------------------------------
    with db.connect() as conn:
        conn.execute("BEGIN")
        field_defs = _field_defs_for_activity(conn, activity_id)

    values: dict[int, Any] = {}

    for fd in field_defs:
        fid = fd["id"]
        kind = fd["kind"]
        if kind in ("count", "scale"):
            raw_val = str(form.get(f"value_{fid}") or "").strip()
            if raw_val:
                values[fid] = raw_val

    memo: str | None = None  # resolved below from combined notes field

    all_tag_ids: list[int] = []
    hashtag_fids = [fd["id"] for fd in field_defs if fd["kind"] == "tag_group"]
    if hashtag_fids:
        with db.connect() as conn:
            conn.execute("BEGIN")
            for fid in hashtag_fids:
                raw = str(form.get(f"hashtags_{fid}", "")).strip()
                if raw:
                    memo = raw  # combined text field → memo
                names = entries.parse_hashtags(raw)
                if names:
                    ids = entries.find_or_create_tags(
                        conn, owner_id=owner_id, field_def_id=fid, names=names
                    )
                    all_tag_ids.extend(ids)
    else:
        raw_memo = str(form.get("memo") or "").strip()
        memo = raw_memo or None

    updated = entries.update(
        owner_id,
        entry_id,
        memo=memo,
        occurred_at=occurred_at,
        time_known=time_known,
        values=values if values else None,
        tags=all_tag_ids,
        tz=tz,
    )

    return _render_entry_row(request, activity_id, owner_id, updated)


# ---------------------------------------------------------------------------
# Entry delete
# ---------------------------------------------------------------------------


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/delete-confirm",
    response_class=HTMLResponse,
)
async def get_entry_delete_confirm(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline delete-confirm fragment for *entry_id* under *activity_id*.

    Ownership checks (in order):
    1. Session required — 401 if not authenticated.
    2. Entry must exist for this owner — 404 via EntryNotFoundError.
    3. Entry must belong to the requested activity_id — 404 on mismatch.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "entry": entry},
    )


@router.post(
    "/activities/{activity_id}/entries/{entry_id}/delete",
    response_class=HTMLResponse,
)
async def delete_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete *entry_id* and return an empty 200 so HTMX removes the row from the DOM.

    Ownership checks are the same as the delete-confirm GET.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    entries.delete(owner_id, entry_id, tz=tz)
    return HTMLResponse(content="", status_code=200)


# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/log", response_class=HTMLResponse)
async def log_sheet(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the quick-add sheet fragment for a sub-tally."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
        if row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
        fields = []
        for fd in field_defs:
            field_ctx: dict[str, Any] = {"id": fd["id"], "kind": fd["kind"], "label": fd["label"]}
            if fd["kind"] == "tag_group":
                field_ctx["hashtag_text"] = ""
            elif fd["kind"] == "match_list":
                # Quick-add starts with one empty bout row; addable via the
                # /match-rows/{field_id}/add fragment.
                field_ctx["rows"] = [dict(_EMPTY_MATCH_ROW)]
            fields.append(field_ctx)

    context = {
        "activity_id": activity_id,
        "name": row["name"],
        "fields": fields,
        "today": datetime.now(tz).strftime("%Y-%m-%d"),
    }
    return templates.TemplateResponse(
        request=request,
        name="components/log_sheet.html.jinja2",
        context=context,
    )


def _require_match_list_field(
    conn: sqlite3.Connection, activity_id: int, field_def_id: int
) -> sqlite3.Row | None:
    """The ``match_list`` field_def for *field_def_id* under *activity_id*, or None."""
    return conn.execute(
        "SELECT id, label FROM field_def WHERE id = ? AND activity_id = ? AND kind = 'match_list'",
        (field_def_id, activity_id),
    ).fetchone()


@router.post("/activities/{activity_id}/match-rows/{field_def_id}/add", response_class=HTMLResponse)
async def add_match_row(
    request: Request,
    activity_id: int,
    field_def_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Append an empty bout row to the match-list sub-form, preserving existing rows."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, activity_id, field_def_id)
        if fd is None:
            return HTMLResponse(status_code=404)

    form = await request.form()
    rows = _parse_match_rows(form, field_def_id)
    rows.append(dict(_EMPTY_MATCH_ROW))

    return templates.TemplateResponse(
        request=request,
        name="components/match_rows.html.jinja2",
        context={
            "activity_id": activity_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )


@router.post(
    "/activities/{activity_id}/match-rows/{field_def_id}/remove/{row_index}",
    response_class=HTMLResponse,
)
async def remove_match_row(
    request: Request,
    activity_id: int,
    field_def_id: int,
    row_index: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Remove bout row *row_index* from the match-list sub-form.

    Always leaves at least one (possibly empty) row so the sub-form never
    disappears entirely.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, activity_id, field_def_id)
        if fd is None:
            return HTMLResponse(status_code=404)

    form = await request.form()
    rows = _parse_match_rows(form, field_def_id)
    if 0 <= row_index < len(rows):
        del rows[row_index]
    if not rows:
        rows.append(dict(_EMPTY_MATCH_ROW))

    return templates.TemplateResponse(
        request=request,
        name="components/match_rows.html.jinja2",
        context={
            "activity_id": activity_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )


@router.post("/activities/{activity_id}/log", response_class=HTMLResponse)
async def create_log(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create an entry and return the updated activity-card fragment.

    Tag selections, scale/count values and memo are read from the submitted
    form. ``occurred_at`` is editable-defaulting (backfillable). The just-used
    tag selections are echoed back into the swapped card so they "survive" the
    swap, per the component-patterns skill.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    form = await request.form()

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)

    payload, selected_tags = _payload_from_form(form, field_defs)

    # Resolve #hashtag text inputs to tag IDs
    all_tag_ids: list[int] = []
    hashtag_fids = [fd["id"] for fd in field_defs if fd["kind"] == "tag_group"]
    if hashtag_fids:
        with db.connect() as conn:
            conn.execute("BEGIN")
            for fid in hashtag_fids:
                raw = str(form.get(f"hashtags_{fid}", "")).strip()
                if raw:
                    payload["memo"] = raw  # combined text → also the memo
                names = entries.parse_hashtags(raw)
                if names:
                    ids = entries.find_or_create_tags(
                        conn, owner_id=owner_id, field_def_id=fid, names=names
                    )
                    all_tag_ids.extend(ids)
    payload["tags"] = all_tag_ids

    occurred_at, time_known = _resolve_occurred_at(
        str(form.get("date") or "").strip(),
        str(form.get("time") or "").strip(),
        tz=tz,
    )

    created = entries.create(
        owner_id, activity_id, payload, occurred_at=occurred_at, tz=tz, time_known=time_known
    )

    # Persist any match-list bouts submitted alongside the entry.
    has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
    for fd in field_defs:
        if fd["kind"] != "match_list":
            continue
        rows = _matches_payload_from_rows(_parse_match_rows(form, fd["id"]))
        if rows:
            competition.add_matches(owner_id, created["id"], rows)

    with db.connect() as conn:
        conn.execute("BEGIN")
        # Re-fetch for fresh cached_count/streak after entries.create's cache refresh.
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        card = _build_card_context(conn, owner_id, sub_row, tz=tz, selected_tags=selected_tags)

    card["bumped"] = True

    html = templates.get_template("components/activity_card.html.jinja2").render(
        {
            "card": card,
        }
    )

    # A match-list log doesn't just update the hero card -- the Record
    # section (W/L/D, timeline, head-to-head) on the same detail page is
    # otherwise stale until a full reload. Append it as an out-of-band swap
    # alongside the hero-card fragment this response already targets.
    if has_match_list:
        record_html = templates.get_template("components/competition_stats.html.jinja2").render(
            {
                "record": competition.record(owner_id, activity_id),
                "timeline": competition.results_timeline(owner_id, activity_id),
                "head_to_head": competition.head_to_head(owner_id, activity_id),
                "oob": True,
            }
        )
        html += record_html

    response = HTMLResponse(content=html)
    response.headers["HX-Trigger"] = "log-saved"
    return response


def _resolve_occurred_at(
    raw_date: str | None,
    raw_time: str | None = None,
    *,
    tz: ZoneInfo,
) -> tuple[str | None, int]:
    """Turn the log sheet's date + optional time fields into (occurred_at, time_known).

    *raw_date* is the ``type="date"`` value (``YYYY-MM-DD``) in the owner's
    local timezone; *raw_time* is the optional ``type="time"`` value (``HH:MM``).

    When *raw_time* is provided and non-empty:
    - Returns an explicit ``YYYY-MM-DDTHH:MM:00`` timestamp with ``time_known=1``.

    When *raw_time* is absent or empty:
    - If *raw_date* is empty or today's date (in *tz*): returns ``(None, 1)``
      so ``entries.create`` defaults to "now" (time still known).
    - If *raw_date* is a past date (backfill, no time supplied): returns
      ``YYYY-MM-DDT00:00:00`` sentinel with ``time_known=0``.
    """
    raw_time = (raw_time or "").strip()
    if not raw_date:
        raw_date = datetime.now(tz).strftime("%Y-%m-%d")
    if "T" in raw_date:
        # Defensive: a full timestamp slipped through (e.g. an old client).
        return raw_date, 1
    if raw_time:
        return f"{raw_date}T{raw_time}:00", 1
    # No time given: always date-only, time_known=0.
    return f"{raw_date}T00:00:00", 0


def _parse_match_rows(form: Any, field_def_id: int) -> list[dict[str, str]]:
    """Read submitted match-list rows for *field_def_id* from form data.

    Rows are indexed 0..n contiguously as ``match_opponent_{field_id}_{i}`` /
    ``match_score_{field_id}_{i}`` / ``match_result_{field_id}_{i}``; reading
    stops at the first missing index.
    """
    rows: list[dict[str, str]] = []
    i = 0
    while True:
        opponent_key = f"match_opponent_{field_def_id}_{i}"
        if opponent_key not in form:
            break
        rows.append(
            {
                "opponent": str(form.get(opponent_key) or ""),
                "score": str(form.get(f"match_score_{field_def_id}_{i}") or ""),
                "result": str(form.get(f"match_result_{field_def_id}_{i}") or ""),
            }
        )
        i += 1
    return rows


def _matches_payload_from_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Filter parsed match rows down to ones ready for ``competition.add_matches``.

    A row is persisted only when it has both an opponent and a result —
    incomplete trailing rows (e.g. an empty row left over from the sub-form)
    are silently dropped rather than raising ``MatchPayloadError``.
    """
    payload: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        opponent = row["opponent"].strip()
        result = row["result"].strip()
        if not opponent or result not in {"win", "loss", "draw"}:
            continue
        payload.append(
            {
                "opponent": opponent,
                "score": row["score"].strip(),
                "result": result,
                "sort_order": index,
            }
        )
    return payload


def _payload_from_form(form: Any, field_defs: list[sqlite3.Row]) -> tuple[dict[str, Any], set[int]]:
    """Build an ``entries.create`` payload from submitted form fields.

    Returns ``(payload, selected_tag_ids)`` — the selected tags are returned
    separately so the swapped card can echo the just-used selection.
    """
    values: dict[str, Any] = {}
    selected_tags: set[int] = set()
    memo: str | None = None

    for fd in field_defs:
        fid = fd["id"]
        kind = fd["kind"]
        if kind in {"count", "scale"}:
            raw_val = form.get(f"value_{fid}")
            if raw_val not in (None, ""):
                values[fid] = raw_val
        elif kind == "memo":
            raw_memo = form.get(f"value_{fid}")
            if raw_memo:
                memo = str(raw_memo)
        # 'level' / 'result' / 'match_list' fields are not part of quick-add v1.

    payload: dict[str, Any] = {"tags": sorted(selected_tags), "values": values}
    if memo is not None:
        payload["memo"] = memo
    return payload, selected_tags


# ---------------------------------------------------------------------------
# Search (people + public tags)
# ---------------------------------------------------------------------------
#
# Session-authenticated. The page route always renders the full page (with
# an initial empty/prompt results region); the results route is HTMX-only,
# debounced by the search box itself (see web/search.html.jinja2), and
# always returns the components/search_results.html.jinja2 fragment — a
# blank query renders a calm prompt, never an error.


@router.get("/search", response_class=HTMLResponse, response_model=None)
async def search_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Render the search page — a search box plus an initially-empty results region."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="web/search.html.jinja2",
        context={"query": "", "people": [], "tags": []},
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the grouped People/Tags results fragment for the search box.

    A blank *q* renders the calm prompt state (handled inside the template)
    rather than running either query.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    query = q.strip()
    people = search.search_people(owner_id, query, limit=20) if query else []
    tags = search.search_tags_public(owner_id, query, limit=20) if query else []

    return templates.TemplateResponse(
        request=request,
        name="components/search_results.html.jinja2",
        context={"query": query, "people": people, "tags": tags},
    )


# ---------------------------------------------------------------------------
# Fellows / connections (social graph)
# ---------------------------------------------------------------------------
#
# All action routes here are session-authenticated and operate on the
# session user as one side of the pair; the other side is resolved from the
# ``{username}`` path segment via ``users.find_by_username`` — never a raw id
# from the client. Every route returns an HTMX fragment (never a full
# reload) and catches the ``connections`` service exceptions into a calm
# inline message (never a bare 500). Two actions — sending a request and
# accepting one — each require a GET-then-POST consent step (the
# ``SHARING_CONSENT_*`` consequence screen) before the mutation fires;
# decline/cancel/unblock are direct, while disconnect/block sit behind a
# two-step inline confirm mirroring ``category_delete_confirm``.


def _connect_error_message(exc: connections.ConnectionError) -> str:
    """Map a connections-service exception to a calm, centralized inline message."""
    if isinstance(exc, connections.AlreadyExistsError):
        return ui_strings.CONNECT_ERROR_ALREADY_EXISTS
    if isinstance(exc, connections.BlockedError):
        return ui_strings.CONNECT_ERROR_BLOCKED
    if isinstance(exc, connections.RateLimitedError):
        return ui_strings.CONNECT_ERROR_RATE_LIMITED
    if isinstance(exc, connections.NotFoundError):
        return ui_strings.CONNECT_ERROR_NOT_FOUND
    return ui_strings.CONNECT_ERROR_GENERIC


def _render_fellows_section(
    request: Request,
    profile_user_id: int,
    *,
    viewer_id: int,
    is_owner: bool,
    error: str | None = None,
) -> HTMLResponse:
    """Re-render the ``fellows_section`` fragment for *profile_user_id*'s page.

    The common "mutate then refresh the fragment" return shape for every
    fellows/requests action below — keeps the fellow list, requests cluster,
    and pending badge all in sync after any action without a full reload.
    """
    fellows_context = _build_fellows_context(
        profile_user_id, viewer_id=viewer_id, is_owner=is_owner
    )
    return templates.TemplateResponse(
        request=request,
        name="components/fellows_section.html.jinja2",
        context={"fellows": fellows_context, "error": error},
    )


def _relationship_dom_id(username: str, *, from_search: bool) -> str:
    """The id a relationship-affordance fragment should render with.

    Search results render one ``relationship_affordance`` per row on the same
    page, so each row needs a unique id (HTMX's id-selector swap is a global
    ``document.querySelector`` — a shared id would always re-target the
    first row). Single-instance contexts (profile pages) keep the original
    plain id unchanged.
    """
    if from_search:
        return f"relationship-affordance-{username}"
    return "relationship-affordance"


def _render_relationship_affordance(
    request: Request,
    profile_username: str,
    profile_user_id: int,
    viewer_id: int,
    *,
    error: str | None = None,
    from_search: bool = False,
) -> HTMLResponse:
    """Re-render the relationship-state affordance fragment for a non-owner viewer."""
    state = connections.relationship_state(viewer_id, profile_user_id)
    dom_id = _relationship_dom_id(profile_username, from_search=from_search)
    return templates.TemplateResponse(
        request=request,
        name="components/relationship_affordance.html.jinja2",
        context={
            "username": profile_username,
            "state": state,
            "error": error,
            "dom_id": dom_id,
            "pending_incoming_target_id": dom_id,
            "from_search": from_search,
        },
    )


def _resolve_other_user(username: str) -> dict[str, Any] | None:
    """Resolve a path ``{username}`` segment to a non-guest user row, or ``None``."""
    other = users.find_by_username(username)
    if other is None or other.get("auth_provider") == "guest":
        return None
    return other


# --- Send request (Connect) — consent-gated -------------------------------


@router.get("/fellows/{username}/connect-confirm", response_class=HTMLResponse)
async def connect_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the sharing-consent confirm step before sending a request."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    from_search = source == "search"
    suffix = "?source=search" if from_search else ""
    return templates.TemplateResponse(
        request=request,
        name="components/sharing_consent_confirm.html.jinja2",
        context={
            "username": username,
            "action": "connect",
            "confirm_url": f"/fellows/{username}/connect{suffix}",
            "cancel_url": f"/fellows/{username}/connect-cancel{suffix}",
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "body": ui_strings.SHARING_CONSENT_BODY_SEND,
            "confirm_label": ui_strings.SHARING_CONSENT_CONFIRM,
        },
    )


@router.get("/fellows/{username}/connect-cancel", response_class=HTMLResponse)
async def connect_cancel(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the connect consent step back to the plain affordance."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    return _render_relationship_affordance(
        request, username, int(other["id"]), int(user["id"]), from_search=source == "search"
    )


@router.post("/fellows/{username}/connect", response_class=HTMLResponse)
async def send_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: send a connection request to *username*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    other_id = int(other["id"])
    viewer_id = int(user["id"])

    error: str | None = None
    try:
        connections.send_request(viewer_id, other_id)
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    return _render_relationship_affordance(
        request, username, other_id, viewer_id, error=error, from_search=source == "search"
    )


# --- Accept / decline / cancel (incoming + outgoing requests) -------------


@router.get("/fellows/requests/{username}/accept-confirm", response_class=HTMLResponse)
async def accept_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the sharing-consent confirm step before accepting *username*'s request."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    from_search = source == "search"
    if from_search:
        # No page-singleton #fellows-section on the search page — swap this
        # row's own relationship-affordance instead (see
        # _relationship_dom_id / accept_connect_request below).
        confirm_url = f"/fellows/requests/{username}/accept?source=search"
        cancel_url = f"/fellows/{username}/connect-cancel?source=search"
    else:
        confirm_url = f"/fellows/requests/{username}/accept"
        cancel_url = "/fellows/requests-cancel"

    action = "accept" if not from_search else "connect"
    if action == "accept":
        body = ui_strings.SHARING_CONSENT_BODY_ACCEPT
        confirm_label = ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT
    else:
        body = ui_strings.SHARING_CONSENT_BODY_SEND
        confirm_label = ui_strings.SHARING_CONSENT_CONFIRM

    return templates.TemplateResponse(
        request=request,
        name="components/sharing_consent_confirm.html.jinja2",
        context={
            "username": username,
            "action": action,
            "confirm_url": confirm_url,
            "cancel_url": cancel_url,
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "body": body,
            "confirm_label": confirm_label,
        },
    )


@router.get("/fellows/requests-cancel", response_class=HTMLResponse)
async def requests_cancel(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the accept consent step back to the requests cluster."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)


@router.post("/fellows/requests/{username}/accept", response_class=HTMLResponse)
async def accept_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: accept *username*'s pending incoming request.

    From search (``?source=search``) there's no page-level fellows section to
    refresh, so the response is this one row's relationship-affordance
    fragment (now "fellow") instead of the owner's whole fellows section.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    error: str | None = None
    try:
        connections.accept(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    if source == "search":
        return _render_relationship_affordance(
            request, username, int(other["id"]), owner_id, error=error, from_search=True
        )

    return _render_fellows_section(
        request, owner_id, viewer_id=owner_id, is_owner=True, error=error
    )


@router.post("/fellows/requests/{username}/decline", response_class=HTMLResponse)
async def decline_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Decline *username*'s pending incoming request — direct, no confirm step.

    From search (``?source=search``), returns this row's relationship-
    affordance fragment (now "none") instead of the owner's fellows section.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    error: str | None = None
    try:
        connections.decline(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    if source == "search":
        return _render_relationship_affordance(
            request, username, int(other["id"]), owner_id, error=error, from_search=True
        )

    return _render_fellows_section(
        request, owner_id, viewer_id=owner_id, is_owner=True, error=error
    )


@router.post("/fellows/requests/{username}/cancel", response_class=HTMLResponse)
async def cancel_connect_request(
    request: Request,
    username: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Withdraw one's own pending outgoing request to *username* — direct."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    connections.cancel(owner_id, int(other["id"]))

    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)


# --- Disconnect (remove a fellow) — two-step inline confirm ---------------


@router.get("/fellows/{username}/remove-confirm", response_class=HTMLResponse)
async def remove_fellow_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline "remove this fellow" confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/connect_remove_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=source == "search"),
        },
    )


@router.post("/fellows/{username}/remove", response_class=HTMLResponse)
async def remove_fellow(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: remove the fellow connection with *username*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    connections.disconnect(viewer_id, int(other["id"]))

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, from_search=source == "search"
    )


# --- Block / unblock --------------------------------------------------------


@router.get("/fellows/{username}/block-confirm", response_class=HTMLResponse)
async def block_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline "block this account" confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/connect_block_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=source == "search"),
        },
    )


@router.get("/fellows/{username}/block-cancel", response_class=HTMLResponse)
async def block_cancel(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the block confirm step back to the plain affordance."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    return _render_relationship_affordance(
        request, username, int(other["id"]), int(user["id"]), from_search=source == "search"
    )


@router.post("/fellows/{username}/block", response_class=HTMLResponse)
async def block_user(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: block *username*. Tears down any connection both ways."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    error: str | None = None
    try:
        connections.block(viewer_id, int(other["id"]))
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, error=error, from_search=source == "search"
    )


@router.post("/fellows/{username}/unblock", response_class=HTMLResponse)
async def unblock_user(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Lift a block on *username* — direct, no confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    connections.unblock(viewer_id, int(other["id"]))

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, from_search=source == "search"
    )


# ---------------------------------------------------------------------------
# Theme toggle
# ---------------------------------------------------------------------------


@router.post("/preferences/theme", response_class=HTMLResponse)
async def toggle_theme(request: Request) -> HTMLResponse:
    """Cycle the theme (light -> dark -> system -> light) and return the toggle fragment.

    No auth required — works for guests and signed-in users alike. The
    ``mushin_theme`` cookie is not ``HttpOnly`` so it stays readable if a
    future client-side enhancement needs it, but is otherwise set the same
    way as the app's other preference cookies.
    """
    current = _theme_from_cookie(request.cookies.get(THEME_COOKIE))
    next_theme = THEME_CYCLE[current]

    # Render directly rather than via templates.TemplateResponse: the
    # _theme_context context processor would overwrite "theme" with the
    # (stale) request-cookie value before the new cookie is set on the
    # response.
    fragment = templates.get_template("components/theme_toggle.html.jinja2").render(
        request=request, theme=next_theme
    )
    response = HTMLResponse(content=fragment)
    response.set_cookie(
        key=THEME_COOKIE,
        value=next_theme,
        max_age=60 * 60 * 24 * 365,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response
