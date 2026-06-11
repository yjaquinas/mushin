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
no business rules (no counting/streak/progression math — that's
``app/services/stats.py`` and ``app/services/progression.py``).
"""

from __future__ import annotations

import calendar as cal
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import ui_strings
from app.auth import sessions, users
from app.models import db
from app.services import _db, competition, entries, progression, stats
from app.services.entries import _kst_day

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")
# Centralized Korean copy is exposed to every template as `strings` — templates
# never hardcode user-facing text (see .claude/skills/copy-patterns).
templates.env.globals["strings"] = ui_strings

# Cookie that remembers the highest progression-level id for which the guest
# upgrade nudge has been dismissed ("나중에" — respected until the *next*
# milestone, never shown again for the same level-up).
NUDGE_COOKIE = "mushin_nudge_dismissed_level"


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
    """Active sub-tallies for *owner_id*, joined with their category, ordered
    by category sort_order then sub-tally sort_order."""
    return conn.execute(
        """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                  st.last_entry_at, st.category_id, c.name AS category_name
             FROM sub_tally st
             JOIN category c ON c.id = st.category_id
            WHERE st.owner_id = ?
              AND st.archived_at IS NULL
              AND c.archived_at IS NULL
            ORDER BY c.sort_order, st.sort_order""",
        (owner_id,),
    ).fetchall()


def _field_defs_for_sub_tally(conn: sqlite3.Connection, sub_tally_id: int) -> list[sqlite3.Row]:
    """Recipe fields for a sub-tally, in the stored field-priority order."""
    return conn.execute(
        "SELECT id, kind, label, sort_order FROM field_def"
        " WHERE sub_tally_id = ? ORDER BY sort_order",
        (sub_tally_id,),
    ).fetchall()


def _tags_for_field(
    conn: sqlite3.Connection, owner_id: int, field_def_id: int
) -> list[sqlite3.Row]:
    """Active tags for a tag_group field, owner-scoped."""
    return _db.fetch_all(
        conn,
        "tag",
        owner_id,
        where="field_def_id = ? AND archived_at IS NULL",
        params=(field_def_id,),
        order_by="sort_order, id",
    )


_EMPTY_MATCH_ROW: dict[str, str] = {"opponent": "", "score": "", "result": ""}


def _build_card_context(
    conn: sqlite3.Connection,
    owner_id: int,
    sub_tally_row: sqlite3.Row,
    *,
    selected_tags: set[int] | None = None,
) -> dict[str, Any]:
    """Assemble the per-card render context: hero, progress, advance line.

    Field-priority order (shared domain rule, see progression.hero_field):
    hero stat -> progress affordance -> advance line. This function does not
    invent the hierarchy — it just shapes ``hero_field`` / ``progression.status``
    output for the template.
    """
    sub_tally_id = sub_tally_row["id"]
    hero = progression.hero_field(sub_tally_id, owner_id)

    progress: dict[str, Any] | None = None
    advance_line: str | None = None

    if hero.get("count_mode") == "progression":
        st = progression.status(sub_tally_id, owner_id)
        track = st["tracks"][0] if st["tracks"] else None
        if track is not None:
            current = track.get("current_level")
            next_level = track.get("next_level")
            if current is not None:
                hero_label = current["label"]
            elif next_level is not None:
                # No level attained yet: the lowest-ordinal level on the
                # ladder is the user's effective starting point (e.g. 독서's
                # 입문 tier has no rule of its own — it's the entry rung, not
                # a "next" target). Show it as the hero and compute the
                # advance line against what's actually reachable from there.
                hero_label = next_level["label"]
                next_level = None
            else:
                hero_label = None
            if next_level is not None:
                if track.get("eligible"):
                    advance_line = f"{next_level['label']} 도전 가능"
                else:
                    advance_line = f"다음: {next_level['label']}"
                # Progress affordance: a quiet 0-100 fill toward the next level
                # for count-gated tracks (the only kind we can express as a bar
                # without leaking gate internals into the template).
                paths = track.get("paths") or []
                count_paths = [p for p in paths if p["gate"].get("gate_type") == "count"]
                if count_paths:
                    gate = count_paths[0]["gate"]
                    required = gate.get("required_count") or 0
                    current_count = gate.get("current_count") or 0
                    pct = min(100, int(100 * current_count / required)) if required else 0
                    progress = {"percent": pct, "leveled": False}
            else:
                advance_line = None
        else:
            hero_label = None
    else:
        hero_label = hero.get("count")

    counts = stats.counts_for_sub_tallies([sub_tally_id], owner_id).get(sub_tally_id, {})
    streak = sub_tally_row["cached_streak"] or 0

    field_defs = _field_defs_for_sub_tally(conn, sub_tally_id)
    fields = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {
            "id": fd["id"],
            "kind": fd["kind"],
            "label": fd["label"],
        }
        if fd["kind"] == "tag_group":
            tags = _tags_for_field(conn, owner_id, fd["id"])
            field_ctx["tags"] = [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "selected": selected_tags is not None and t["id"] in selected_tags,
                }
                for t in tags
            ]
        fields.append(field_ctx)

    return {
        "id": sub_tally_id,
        "category_name": sub_tally_row["category_name"],
        "name": sub_tally_row["name"],
        "count_mode": sub_tally_row["count_mode"],
        "hero_label": hero_label,
        "progress": progress,
        "advance_line": advance_line,
        "lifetime": counts.get("lifetime", sub_tally_row["cached_count"] or 0),
        "streak": streak,
        "fields": fields,
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
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


def _build_heatmap_context(sub_tally_id: int, owner_id: int) -> dict[str, Any]:
    """Trailing-365-day heatmap series, bucketed server-side for ``.heat-cell--N``."""
    series = stats.heatmap(sub_tally_id, owner_id)
    cells = [{"date": day["date"], "bucket": _heat_bucket(day["count"])} for day in series]
    return {"cells": cells}


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last day of *year*-*month*."""
    first = date(year, month, 1)
    last_day = cal.monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _build_calendar_context(
    sub_tally_id: int, owner_id: int, *, year: int, month: int
) -> dict[str, Any]:
    """Month-grid context: weeks of ``.cal-day`` cells, marked + today flags.

    Weeks are Monday-first (matching ``stats._week_start``), padded with
    ``None`` cells for days outside *year*-*month* so the grid stays a regular
    table. Marked days are derived from the sub-tally's entry days for that
    month (one query via ``entries.list_for_sub_tally`` would over-fetch, so we
    use ``stats.heatmap`` only when the month is within the trailing 365 days;
    otherwise we read entries directly).
    """
    first, last = _month_bounds(year, month)
    today = datetime.now(UTC).date()
    # Reuse stats._entry_days via the public heatmap when possible would be
    # awkward for arbitrary months, so read entry days directly (owner-scoped).
    rows = entries.list_for_sub_tally(owner_id, sub_tally_id)
    marked_days: set[date] = set()
    for e in rows:
        d = _kst_day(e["occurred_at"])
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


def _entries_on_day(sub_tally_id: int, owner_id: int, day: date) -> list[dict[str, Any]]:
    """All of a sub-tally's entries (hydrated) whose KST day is *day*."""
    rows = entries.list_for_sub_tally(owner_id, sub_tally_id)
    return [e for e in rows if _kst_day(e["occurred_at"]) == day]


def _build_progression_context(sub_tally_id: int, owner_id: int) -> dict[str, Any] | None:
    """Renderer-shaped progression status, or ``None`` for non-progression sub-tallies."""
    st = progression.status(sub_tally_id, owner_id)
    if not st["is_progression"]:
        return None

    track_labels = {
        "dan": ui_strings.PROGRESSION_TRACK_DAN,
        "shogo": ui_strings.PROGRESSION_TRACK_SHOGO,
        "tier": ui_strings.PROGRESSION_TRACK_TIER,
    }

    tracks = []
    for track in st["tracks"]:
        tracks.append(
            {
                "track": track["track"],
                "track_label": track_labels.get(track["track"], track["track"]),
                "current_level": track.get("current_level"),
                "next_level": track.get("next_level"),
                "eligible": track.get("eligible", False),
                "paths": track.get("paths") or [],
            }
        )
    return {"tracks": tracks}


def _build_field_stats_context(
    sub_tally_id: int, owner_id: int, field_defs: list[sqlite3.Row]
) -> dict[str, Any]:
    """Tag-frequency and scale-distribution sections for the fields that exist."""
    tag_groups = []
    scales = []
    for fd in field_defs:
        if fd["kind"] == "tag_group":
            freq = stats.tag_frequency(sub_tally_id, owner_id, fd["id"])
            tag_groups.append({"label": fd["label"], "tags": freq["tags"]})
        elif fd["kind"] == "scale":
            dist = stats.scale_distribution(sub_tally_id, owner_id, fd["id"])
            scales.append({"label": fd["label"], **dist})
    return {"tag_groups": tag_groups, "scales": scales}


# ---------------------------------------------------------------------------
# Entry screen + home
# ---------------------------------------------------------------------------


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    """The 개인정보처리방침 (privacy policy) page. Reachable logged-out."""
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
        return templates.TemplateResponse(
            request=request,
            name="web/entry.html.jinja2",
            context={},
        )
    return await _render_home(request, user)


@router.get("/home", response_class=HTMLResponse)
async def home(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """The character-sheet home. Redirects to the entry screen with no session."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return await _render_home(request, user)


async def _render_home(request: Request, user: dict[str, Any]) -> HTMLResponse:
    owner_id = int(user["id"])
    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_tallies = _list_sub_tallies(conn, owner_id)
        cards = [_build_card_context(conn, owner_id, row) for row in sub_tallies]

    return templates.TemplateResponse(
        request=request,
        name="web/home.html.jinja2",
        context={"cards": cards},
    )


# ---------------------------------------------------------------------------
# Sub-tally detail
# ---------------------------------------------------------------------------


@router.get("/sub-tallies/{sub_tally_id}", response_class=HTMLResponse)
async def sub_tally_detail(
    request: Request,
    sub_tally_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Sub-tally detail screen: card + (for tournament sub-tallies) competition stats.

    Competition stats only render for sub-tallies whose recipe includes a
    ``match_list`` field (e.g. 검도 / 시합).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name
                 FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (sub_tally_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_sub_tally(conn, sub_tally_id)
        has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
        card = _build_card_context(conn, owner_id, sub_row)

    context: dict[str, Any] = {"card": card, "show_nudge": False, "nudge_level_id": None}

    if has_match_list:
        context["record"] = competition.record(owner_id, sub_tally_id)
        context["timeline"] = competition.results_timeline(owner_id, sub_tally_id)
        context["head_to_head"] = competition.head_to_head(owner_id, sub_tally_id)
    else:
        context["record"] = None
        context["timeline"] = []
        context["head_to_head"] = []

    today = datetime.now(UTC).date()
    context["sub_tally_id"] = sub_tally_id
    context["counts"] = stats.counts(sub_tally_id, owner_id)
    context["streaks"] = stats.streaks(sub_tally_id, owner_id)
    context["heatmap"] = _build_heatmap_context(sub_tally_id, owner_id)
    context["calendar"] = _build_calendar_context(
        sub_tally_id, owner_id, year=today.year, month=today.month
    )
    context["field_stats"] = _build_field_stats_context(sub_tally_id, owner_id, field_defs)
    context["progression"] = _build_progression_context(sub_tally_id, owner_id)

    return templates.TemplateResponse(
        request=request,
        name="web/sub_tally_detail.html.jinja2",
        context=context,
    )


# ---------------------------------------------------------------------------
# Calendar fragments (month navigation + day drill-down)
# ---------------------------------------------------------------------------


@router.get("/sub-tallies/{sub_tally_id}/calendar", response_class=HTMLResponse)
async def calendar_month(
    request: Request,
    sub_tally_id: int,
    year: int,
    month: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the month-calendar fragment for *year*-*month* (HTMX swap target)."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    if not (1 <= month <= 12):
        return HTMLResponse(status_code=400)

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,)):
            return HTMLResponse(status_code=404)

    calendar_ctx = _build_calendar_context(sub_tally_id, owner_id, year=year, month=month)
    return templates.TemplateResponse(
        request=request,
        name="components/calendar.html.jinja2",
        context={"sub_tally_id": sub_tally_id, "calendar": calendar_ctx},
    )


@router.get("/sub-tallies/{sub_tally_id}/calendar/day/{day}", response_class=HTMLResponse)
async def calendar_day(
    request: Request,
    sub_tally_id: int,
    day: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the entries logged on *day* (``YYYY-MM-DD``) as an HTMX fragment."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        target_day = date.fromisoformat(day)
    except ValueError:
        return HTMLResponse(status_code=400)

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,)):
            return HTMLResponse(status_code=404)

    day_entries = _entries_on_day(sub_tally_id, owner_id, target_day)
    return templates.TemplateResponse(
        request=request,
        name="components/day_entries.html.jinja2",
        context={"day": day, "entries": day_entries},
    )


# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------


@router.get("/sub-tallies/{sub_tally_id}/log", response_class=HTMLResponse)
async def log_sheet(
    request: Request,
    sub_tally_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the quick-add sheet fragment for a sub-tally."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,))
        if row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_sub_tally(conn, sub_tally_id)
        fields = []
        for fd in field_defs:
            field_ctx: dict[str, Any] = {"id": fd["id"], "kind": fd["kind"], "label": fd["label"]}
            if fd["kind"] == "tag_group":
                tags = _tags_for_field(conn, owner_id, fd["id"])
                field_ctx["tags"] = [
                    {"id": t["id"], "name": t["name"], "selected": False} for t in tags
                ]
            elif fd["kind"] == "match_list":
                # Quick-add starts with one empty bout row; addable via the
                # /match-rows/{field_id}/add fragment.
                field_ctx["rows"] = [dict(_EMPTY_MATCH_ROW)]
            fields.append(field_ctx)

    context = {
        "sub_tally_id": sub_tally_id,
        "name": row["name"],
        "fields": fields,
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
    }
    return templates.TemplateResponse(
        request=request,
        name="components/log_sheet.html.jinja2",
        context=context,
    )


@router.post("/sub-tallies/{sub_tally_id}/tags", response_class=HTMLResponse)
async def add_tag(
    request: Request,
    sub_tally_id: int,
    field_def_id: Annotated[int, Form()],
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """First-use 'add tag' from quick-add. Returns the refreshed chip group."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    name = name.strip()

    with db.connect() as conn:
        conn.execute("BEGIN")
        # field_def has no owner_id column; verify it belongs to a sub_tally
        # this owner owns, and to the requested sub_tally specifically.
        fd = conn.execute(
            """SELECT fd.id, fd.label FROM field_def fd
                 JOIN sub_tally st ON st.id = fd.sub_tally_id
                WHERE fd.id = ? AND fd.sub_tally_id = ? AND st.owner_id = ?
                  AND fd.kind = 'tag_group'""",
            (field_def_id, sub_tally_id, owner_id),
        ).fetchone()
        if fd is None:
            return HTMLResponse(status_code=404)

        new_tag_id: int | None = None
        if name:
            existing = conn.execute(
                "SELECT id FROM tag WHERE owner_id = ? AND field_def_id = ? AND name = ?",
                (owner_id, field_def_id, name),
            ).fetchone()
            if existing is not None:
                new_tag_id = existing["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO tag (owner_id, field_def_id, name, sort_order)"
                    " VALUES (?, ?, ?,"
                    " (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tag WHERE field_def_id = ?))",
                    (owner_id, field_def_id, name, field_def_id),
                )
                new_tag_id = cur.lastrowid

        tags = _tags_for_field(conn, owner_id, field_def_id)

    field_ctx = {
        "id": field_def_id,
        "kind": "tag_group",
        "label": fd["label"],
        "tags": [
            {"id": t["id"], "name": t["name"], "selected": t["id"] == new_tag_id} for t in tags
        ],
    }
    return templates.TemplateResponse(
        request=request,
        name="components/tag_group.html.jinja2",
        context={"sub_tally_id": sub_tally_id, "field": field_ctx},
    )


def _require_match_list_field(
    conn: sqlite3.Connection, sub_tally_id: int, field_def_id: int
) -> sqlite3.Row | None:
    """The ``match_list`` field_def for *field_def_id* under *sub_tally_id*, or None."""
    return conn.execute(
        "SELECT id, label FROM field_def WHERE id = ? AND sub_tally_id = ? AND kind = 'match_list'",
        (field_def_id, sub_tally_id),
    ).fetchone()


@router.post(
    "/sub-tallies/{sub_tally_id}/match-rows/{field_def_id}/add", response_class=HTMLResponse
)
async def add_match_row(
    request: Request,
    sub_tally_id: int,
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
        if not _db.exists(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, sub_tally_id, field_def_id)
        if fd is None:
            return HTMLResponse(status_code=404)

    form = await request.form()
    rows = _parse_match_rows(form, field_def_id)
    rows.append(dict(_EMPTY_MATCH_ROW))

    return templates.TemplateResponse(
        request=request,
        name="components/match_rows.html.jinja2",
        context={
            "sub_tally_id": sub_tally_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )


@router.post(
    "/sub-tallies/{sub_tally_id}/match-rows/{field_def_id}/remove/{row_index}",
    response_class=HTMLResponse,
)
async def remove_match_row(
    request: Request,
    sub_tally_id: int,
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
        if not _db.exists(conn, "sub_tally", owner_id, where="id = ?", params=(sub_tally_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, sub_tally_id, field_def_id)
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
            "sub_tally_id": sub_tally_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )


@router.post("/sub-tallies/{sub_tally_id}/log", response_class=HTMLResponse)
async def create_log(
    request: Request,
    sub_tally_id: int,
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

    form = await request.form()

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name
                 FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (sub_tally_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_sub_tally(conn, sub_tally_id)

    payload, selected_tags = _payload_from_form(form, field_defs)
    occurred_at = form.get("occurred_at") or None

    # Capture the progression status before the write so a level-up can be
    # detected by comparing current_level ids (used for the guest nudge).
    before_level_ids = (
        _current_level_ids(sub_tally_id, owner_id)
        if sub_row["count_mode"] == "progression"
        else set()
    )

    created = entries.create(owner_id, sub_tally_id, payload, occurred_at=occurred_at)

    # Persist any match-list bouts submitted alongside the entry.
    for fd in field_defs:
        if fd["kind"] != "match_list":
            continue
        rows = _matches_payload_from_rows(_parse_match_rows(form, fd["id"]))
        if rows:
            competition.add_matches(owner_id, created["id"], rows)

    leveled_up = False
    new_level_id: int | None = None
    if sub_row["count_mode"] == "progression":
        after_level_ids = _current_level_ids(sub_tally_id, owner_id)
        newly_attained = after_level_ids - before_level_ids
        if newly_attained:
            leveled_up = True
            new_level_id = next(iter(newly_attained))

    with db.connect() as conn:
        conn.execute("BEGIN")
        # Re-fetch for fresh cached_count/streak after entries.create's cache refresh.
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name
                 FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (sub_tally_id, owner_id),
        ).fetchone()
        card = _build_card_context(conn, owner_id, sub_row, selected_tags=selected_tags)

    if card["progress"] is not None and leveled_up:
        card["progress"]["leveled"] = True

    show_nudge = False
    if leveled_up and user["auth_provider"] == "guest" and new_level_id is not None:
        dismissed_raw = request.cookies.get(NUDGE_COOKIE)
        dismissed_id = int(dismissed_raw) if dismissed_raw and dismissed_raw.isdigit() else None
        show_nudge = dismissed_id != new_level_id

    response = templates.TemplateResponse(
        request=request,
        name="components/activity_card.html.jinja2",
        context={
            "card": card,
            "show_nudge": show_nudge,
            "nudge_level_id": new_level_id,
        },
    )
    return response


def _current_level_ids(sub_tally_id: int, owner_id: int) -> set[int]:
    """The set of currently-attained level ids across all tracks (for level-up diffing)."""
    st = progression.status(sub_tally_id, owner_id)
    out: set[int] = set()
    for track in st["tracks"]:
        current = track.get("current_level")
        if current is not None:
            out.add(current["id"])
    return out


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
        if kind == "tag_group":
            for raw in form.getlist(f"tags_{fid}"):
                if str(raw).isdigit():
                    selected_tags.add(int(raw))
        elif kind in {"count", "scale"}:
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
# Guest upgrade nudge
# ---------------------------------------------------------------------------


@router.post("/nudge/dismiss", response_class=HTMLResponse)
async def dismiss_nudge(
    level_id: Annotated[int, Form()],
) -> HTMLResponse:
    """Dismiss the guest upgrade nudge for *level_id* ("나중에").

    Stored in a small cookie (no schema change in this task) so the nudge
    won't re-fire for the *same* level-up, but will fire again at the next
    milestone. Never blocks logging — this is a no-op fragment response.
    """
    response = HTMLResponse(content="")
    response.set_cookie(
        key=NUDGE_COOKIE,
        value=str(level_id),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response
