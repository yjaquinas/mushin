"""Handler bodies for the entry edit/delete + quick-add-sheet routes.

Internal companion module (route-structure rule, option 2) — the route
declarations stay in ``entries.py``; the handler bodies and the private
render helpers they share live here so ``entries.py`` stays under the
300-line ceiling. Not a route group of its own: no ``APIRouter`` here. Two
sibling companions split off the remaining weight: ``_entries_log_handler.py``
(the create-log body) and ``_entries_match_rows.py`` (the match-list
add/remove-row bodies).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._contexts import _EMPTY_MATCH_ROW, _field_defs_for_activity
from app.routes.web._shared import templates
from app.services import _db, comments, entries, profiles

EntryNotFoundError = entries.EntryNotFoundError
PayloadError = entries.PayloadError


def _render_template_html(name: str, context: dict[str, Any]) -> str:
    return templates.env.get_template(name).render(context)


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
            "expand_comment_entry_id": entry["id"],
        },
    )


async def update_entry_body(
    request: Request,
    activity_id: int,
    entry_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Body of ``POST /activities/{activity_id}/entries/{entry_id}``.

    Parses occurred_at (date-only), memo, tag selections, and scalar values
    from the form. ``time_known`` handling: if a ``time`` field is present and
    non-empty, combine date+time (time_known=1); if the time field is empty or
    absent, use midnight (time_known=0 — Task 6 adds the time UI, so for now
    the field is never submitted and we default to midnight).

    Ownership checks are the caller's responsibility (same as the GET).
    """
    tz = users.get_user_timezone(owner_id)
    now = datetime.now(tz)

    try:
        existing = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if existing["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    form = await request.form()

    # --- occurred_at + time_known -------------------------------------------
    occurred_at, time_known = entries.resolve_occurred_at(
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

    try:
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
    except PayloadError:
        return HTMLResponse(status_code=422)

    user = users.get_user(owner_id)
    username = user.get("username") if user is not None else None

    with db.connect() as conn:
        conn.execute("BEGIN")
        activity_row = profiles.get_activity_for_owner(
            conn, activity_id=activity_id, owner_id=owner_id
        )
        slug = activity_row["slug"] if activity_row is not None else None
        counts = comments.counts_for_entries(conn, [updated["id"]])

    updated = dict(updated)
    updated["comment_count"] = counts.get(updated["id"], 0)
    row_html = _render_template_html(
        "components/entry_row.html.jinja2",
        {
            "activity_id": activity_id,
            "entry": updated,
            "username": username,
            "slug": slug,
            "expand_comment_entry_id": updated["id"],
        },
    )
    row_html = row_html.replace(
        f'<li id="entry-row-{updated["id"]}"',
        f'<li id="entry-row-{updated["id"]}" hx-swap-oob="outerHTML"',
        1,
    )
    dialog_reset = f'<div id="entry-edit-dialog-{updated["id"]}"></div>'
    return HTMLResponse(
        content=f"{row_html}{dialog_reset}",
        status_code=200,
    )


async def log_sheet_body(
    request: Request,
    activity_id: int,
    owner_id: int,
    *,
    inline: bool = False,
) -> HTMLResponse:
    """Body of ``GET /activities/{activity_id}/log`` — the quick-add sheet fragment.

    When *inline* is ``True``, renders the form without the dialog wrapper so it
    expands inline in the activity detail page instead of opening as a modal.
    """
    tz = users.get_user_timezone(owner_id)
    now = datetime.now(tz)

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
        "today": now.strftime("%Y-%m-%d"),
        "time_known": True,
        "time_value": now.strftime("%H:%M"),
        "inline": inline,
    }
    return templates.TemplateResponse(
        request=request,
        name="components/log_sheet.html.jinja2",
        context=context,
    )
