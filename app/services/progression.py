"""Progression engine for the Mushin service layer.

Renderer-agnostic, owner-scoped, returns plain Python data structures. No HTTP,
no Jinja, no HXML — both renderers consume the dicts produced here.

What this module computes
-------------------------
For a ``progression`` sub-tally, *status is derived, never stored*. From three
sources of truth:

* the ordered ``level`` rows (the ladder(s); ``track`` separates parallel
  ladders such as kendo dan vs the shōgō prestige track),
* the user's **level-entry history** — entries that recorded a ``level``-kind
  value (the ``code`` of a ``level`` row) with their ``occurred_at``, and
* the ``level_rule`` rows gating each transition,

we compute, per track:

* **current stage** — the highest-ordinal level the user has actually recorded
  attaining (by their level entries), and *when* they attained it (the earliest
  ``occurred_at`` at which that level appears).
* **progress in the current stage** — time since attainment (for time gates) and
  the relevant count accumulated since the baseline (for count gates).
* **eligibility + what's needed** for the next stage, evaluating the
  ``level_rule`` from current → next.

Derived, never cached
---------------------
The current stage is cheap and stable (it only changes when a new level entry is
logged), so a renderer *may* cache it. **Eligibility is recomputed live on every
call** and is never stored: a ``time`` gate flips from not-eligible to eligible
with the mere passage of time and no new entry, so a cached eligibility boolean
would silently drift. The reference instant ("now") is injectable (``now=``) so
the math is deterministic in tests.

Gate types
----------
``time``    — eligible when ``(now - attained_at) >= gate_value`` **years**.
              Reports the eligibility date and the remaining countdown.
``count``   — eligible when the relevant count since the baseline ``>= gate_value``.
              For the reading tiers the count is *books read* == the lifetime
              number of entries on the sub-tally (each entry is one book); the
              tier thresholds (10/25/50/100) are cumulative, so we compare the
              **lifetime entry count** against ``gate_value``. See
              ``_count_for_gate`` for the documented choice.
``event``   — eligible when a passing attempt exists: a ``result``-kind entry
              whose value is a "pass" marker, logged at/after the attainment of
              the current level (the gate's ``from`` level).
``manual``  — always "available to declare" (the user asserts it).

prereq_level_id
---------------
A rule may require *holding another level first*, possibly on another track (the
shōgō track gates on dan levels). The prerequisite is checked **before** the
rule's own gate: if the user does not currently hold the prereq level, the
transition is not eligible regardless of the time/count/event clock, and the
unmet prerequisite is surfaced.

min_age / age gates
-------------------
The schema carries ``min_age`` on a rule but Mushin stores **no birthdate**. So
this engine accepts an optional ``age: int | None``:

* ``age`` provided  → the age requirement is enforced (must be ``>= min_age``).
* ``age`` is ``None`` → the engine **does not** silently pass or fail. It surfaces
  the requirement transparently (``age_requirement: <min_age>``,
  ``age_known: False``) and treats the age condition as *unsatisfied for the
  purpose of the eligible bool* — so a renderer can show "만46세 이상" without the
  engine ever fabricating eligibility, and the user is told exactly what's
  outstanding. The non-age portion of the gate is still reported (e.g. the time
  clock may be met even while age is unknown).

Batching
--------
``status_for_sub_tallies`` takes a list of activity ids and reads each table
(``level``, ``level_rule``, level entries) with **one** ``WHERE activity_id IN
(...)`` query apiece — no N+1 fan-out when a category renders many progression
sub-tallies at once.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db
from app.services import _db

# Default reference zone for progression time math. The ``now=`` parameter is
# normally supplied by the caller (tests inject a fixed instant; the renderer
# passes the user's clock), so this default is only the bare-call fallback.
KST = ZoneInfo("Asia/Seoul")

# Seconds in a (Julian) year — the unit ``time`` gate_values are expressed in.
# 365.25 days absorbs leap years so a "1 year" gate lands on roughly the same
# calendar date a year later regardless of which year it is.
_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60

# Values of a ``result``-kind field that mark a *passing* grading attempt. Stored
# as text on entry_value; we accept the common spellings/locales.
_PASS_MARKERS = frozenset({"pass", "passed", "합격", "합", "true", "1"})


# ---------------------------------------------------------------------------
# Reference clock (injectable for deterministic tests)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Current instant, KST, timezone-aware. Overridable via the ``now=`` param."""
    return datetime.now(KST)


def _parse_ts(occurred_at: str) -> datetime:
    """Parse an entry ``occurred_at`` to a tz-aware datetime.

    Mirrors ``entries._local_day``: a naive timestamp is interpreted as
    wall-clock in the reference zone; an aware one is converted to that zone so
    comparisons against the reference clock are sound.
    """
    dt = datetime.fromisoformat(occurred_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


# ---------------------------------------------------------------------------
# Loading the three sources of truth (owner-scoped; batched)
# ---------------------------------------------------------------------------


def _load_levels(
    conn: sqlite3.Connection, owner_id: int, activity_ids: list[int]
) -> dict[int, list[sqlite3.Row]]:
    """All active ``level`` rows for the given sub-tallies, grouped by activity.

    One query (``WHERE activity_id IN (...)``). Ordered by track then ordinal so
    callers can rely on ascending ladder order within each track.
    """
    placeholders = ",".join("?" for _ in activity_ids)
    rows = _db.fetch_all(
        conn,
        "level",
        owner_id,
        where=f"activity_id IN ({placeholders}) AND archived_at IS NULL",
        params=tuple(activity_ids),
        order_by="activity_id, track, ordinal",
    )
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        grouped[r["activity_id"]].append(r)
    return grouped


def _load_rules(
    conn: sqlite3.Connection, owner_id: int, activity_ids: list[int]
) -> dict[int, list[sqlite3.Row]]:
    """All ``level_rule`` rows for the given sub-tallies, grouped by activity.

    One query. A given ``to_level_id`` may have several rules (the shōgō 교사
    OR-paths); callers evaluate them as alternatives.
    """
    placeholders = ",".join("?" for _ in activity_ids)
    rows = _db.fetch_all(
        conn,
        "level_rule",
        owner_id,
        where=f"activity_id IN ({placeholders})",
        params=tuple(activity_ids),
    )
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        grouped[r["activity_id"]].append(r)
    return grouped


def _load_level_entries(
    conn: sqlite3.Connection, owner_id: int, activity_ids: list[int]
) -> dict[int, list[tuple[str, str]]]:
    """Level-entry history per sub-tally as ``(level_code, occurred_at)`` tuples.

    A "level entry" is an ``entry_value`` whose ``field_def`` is of kind
    ``level``, carrying the attained level's ``code`` in ``text_value``, joined
    back through the **owner-scoped** ``entry`` table so a value can never reach
    across tenants. One query (``WHERE e.activity_id IN (...)``).
    """
    placeholders = ",".join("?" for _ in activity_ids)
    rows = conn.execute(
        f"""SELECT e.activity_id AS activity_id,
                   ev.text_value  AS code,
                   e.occurred_at  AS occurred_at
              FROM entry_value ev
              JOIN entry e     ON e.id = ev.entry_id
              JOIN field_def fd ON fd.id = ev.field_def_id
             WHERE e.owner_id = ?
               AND e.activity_id IN ({placeholders})
               AND fd.kind = 'level'
               AND ev.text_value IS NOT NULL""",  # noqa: S608 - placeholders are '?'
        (owner_id, *activity_ids),
    ).fetchall()
    grouped: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        grouped[r["activity_id"]].append((r["code"], r["occurred_at"]))
    return grouped


def _load_result_events(
    conn: sqlite3.Connection, owner_id: int, activity_ids: list[int]
) -> dict[int, list[tuple[str, str]]]:
    """Result-entry history per sub-tally as ``(result_value, occurred_at)``.

    A ``result``-kind entry_value carries the outcome of a grading attempt
    (pass/fail). Used by the ``event`` gate. Owner-scoped, one query.
    """
    placeholders = ",".join("?" for _ in activity_ids)
    rows = conn.execute(
        f"""SELECT e.activity_id AS activity_id,
                   ev.text_value  AS result,
                   e.occurred_at  AS occurred_at
              FROM entry_value ev
              JOIN entry e     ON e.id = ev.entry_id
              JOIN field_def fd ON fd.id = ev.field_def_id
             WHERE e.owner_id = ?
               AND e.activity_id IN ({placeholders})
               AND fd.kind = 'result'
               AND ev.text_value IS NOT NULL""",  # noqa: S608 - placeholders are '?'
        (owner_id, *activity_ids),
    ).fetchall()
    grouped: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        grouped[r["activity_id"]].append((r["result"], r["occurred_at"]))
    return grouped


def _load_entry_counts(
    conn: sqlite3.Connection, owner_id: int, activity_ids: list[int]
) -> dict[int, int]:
    """Lifetime entry count per sub-tally (owner-scoped, one query).

    This is the *book count* for the reading tiers: each entry is one book read,
    and the tier thresholds (10/25/50/100) are cumulative lifetime counts.
    """
    placeholders = ",".join("?" for _ in activity_ids)
    rows = conn.execute(
        f"""SELECT activity_id, COUNT(*) AS n
              FROM entry
             WHERE owner_id = ?
               AND activity_id IN ({placeholders})
             GROUP BY activity_id""",  # noqa: S608 - placeholders are '?'
        (owner_id, *activity_ids),
    ).fetchall()
    return {r["activity_id"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# Current-stage derivation
# ---------------------------------------------------------------------------


def _attainment(
    levels: list[sqlite3.Row], level_entries: list[tuple[str, str]]
) -> dict[int, datetime]:
    """Map ``level.id -> earliest attainment instant`` from the entry history.

    A level is "attained" if the user has logged a level entry whose ``code``
    matches it; the attainment instant is the **earliest** such entry (later
    re-logs don't reset the clock). Codes that don't match any active level are
    ignored (e.g. an archived/renamed level).
    """
    code_to_id = {lvl["code"]: lvl["id"] for lvl in levels}
    attained: dict[int, datetime] = {}
    for code, occurred_at in level_entries:
        lvl_id = code_to_id.get(code)
        if lvl_id is None:
            continue
        when = _parse_ts(occurred_at)
        if lvl_id not in attained or when < attained[lvl_id]:
            attained[lvl_id] = when
    return attained


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def _count_for_gate(entry_count: int) -> int:
    """The count a ``count`` gate compares against ``gate_value``.

    Documented choice: for the reading tiers the count gate is **cumulative books
    read**, which is the lifetime entry count on the sub-tally (one entry == one
    book). Tier thresholds (초급=10 … 달인=100) are therefore absolute lifetime
    counts, not per-tier increments, so we hand back the lifetime entry count
    directly. (A future count-field-summed variant can plug in here without
    changing callers.)
    """
    return entry_count


def _eval_time_gate(
    rule: sqlite3.Row, attained_at: datetime | None, now: datetime
) -> dict[str, Any]:
    """Evaluate a ``time`` gate: years held at the current (``from``) level."""
    required_years = rule["gate_value"]
    detail: dict[str, Any] = {
        "gate_type": "time",
        "required_years": required_years,
    }
    if attained_at is None:
        # No baseline — the user doesn't hold the from-level; not satisfiable yet.
        detail["satisfied"] = False
        detail["reason"] = "from_level_not_held"
        return detail

    eligible_at = _add_years(attained_at, required_years)
    held_seconds = (now - attained_at).total_seconds()
    held_years = held_seconds / _SECONDS_PER_YEAR
    remaining_seconds = max(0.0, (eligible_at - now).total_seconds())

    detail.update(
        {
            "satisfied": now >= eligible_at,
            "attained_at": attained_at.isoformat(),
            "eligible_at": eligible_at.isoformat(),
            "years_held": round(held_years, 4),
            "years_remaining": round(remaining_seconds / _SECONDS_PER_YEAR, 4),
            "days_remaining": round(remaining_seconds / 86400, 2),
        }
    )
    return detail


def _eval_count_gate(rule: sqlite3.Row, current_count: int) -> dict[str, Any]:
    """Evaluate a ``count`` gate against the current relevant count."""
    required = rule["gate_value"]
    remaining = max(0, int(required) - current_count) if required is not None else 0
    return {
        "gate_type": "count",
        "required_count": required,
        "current_count": current_count,
        "count_remaining": remaining,
        "satisfied": required is not None and current_count >= required,
    }


def _eval_event_gate(
    rule: sqlite3.Row,
    result_events: list[tuple[str, str]],
    attained_at: datetime | None,
) -> dict[str, Any]:
    """Evaluate an ``event`` gate: a passing attempt at/after the from-level.

    Eligible when there exists a ``result``-kind entry marking a *pass*, logged
    at or after the instant the current (``from``) level was attained. (When the
    rule has no from-level — an entry-point transition — any passing attempt
    qualifies.)
    """
    baseline = attained_at
    passing = [
        when
        for value, when_raw in result_events
        if str(value).strip().lower() in _PASS_MARKERS or str(value).strip() in _PASS_MARKERS
        for when in (_parse_ts(when_raw),)
        if baseline is None or when >= baseline
    ]
    return {
        "gate_type": "event",
        "satisfied": bool(passing),
        "passing_attempts": len(passing),
        "last_pass_at": max(passing).isoformat() if passing else None,
    }


def _eval_manual_gate(rule: sqlite3.Row) -> dict[str, Any]:
    """Evaluate a ``manual`` gate: always available for the user to declare."""
    return {"gate_type": "manual", "satisfied": True, "declarable": True}


def _add_years(dt: datetime, years: float) -> datetime:
    """``dt`` advanced by a fractional number of (Julian) years.

    Uses the same 365.25-day year as the gate math so ``_eval_time_gate``'s
    countdown and eligibility date are internally consistent.
    """
    return dt.fromtimestamp(dt.timestamp() + years * _SECONDS_PER_YEAR, tz=dt.tzinfo)


# ---------------------------------------------------------------------------
# Per-rule transition evaluation (prereq → gate → age)
# ---------------------------------------------------------------------------


def _eval_rule(
    rule: sqlite3.Row,
    *,
    levels_by_id: dict[int, sqlite3.Row],
    attained: dict[int, datetime],
    current_count: int,
    result_events: list[tuple[str, str]],
    age: int | None,
    now: datetime,
) -> dict[str, Any]:
    """Evaluate one ``level_rule`` (one path to a target level) end-to-end.

    Order of checks: **prerequisite → own gate → age**. The returned dict always
    carries an ``eligible`` bool (the conjunction of every condition) plus a
    transparent breakdown so a renderer can show exactly what's outstanding.
    ``age`` unknown never fabricates eligibility (see module docstring).
    """
    from_level_id = rule["from_level_id"]
    attained_at = attained.get(from_level_id) if from_level_id is not None else None

    # --- prerequisite (possibly cross-track) -------------------------------
    prereq_id = rule["prereq_level_id"]
    prereq_info: dict[str, Any] | None = None
    prereq_ok = True
    prereq_at: datetime | None = None
    if prereq_id is not None:
        prereq_at = attained.get(prereq_id)
        prereq_ok = prereq_at is not None
        prereq_lvl = levels_by_id.get(prereq_id)
        prereq_info = {
            "level_id": prereq_id,
            "code": prereq_lvl["code"] if prereq_lvl else None,
            "label": prereq_lvl["label"] if prereq_lvl else None,
            "held": prereq_ok,
            "attained_at": prereq_at.isoformat() if prereq_at else None,
        }

    # --- the rule's own gate ----------------------------------------------
    # For a time gate, the "held" clock runs from the from-level *or*, when the
    # rule is a cross-track prestige gate keyed on a prereq (e.g. shōgō: "5단 held
    # ≥ 3y"), from the prereq level's attainment.
    gate_type = rule["gate_type"]
    if gate_type == "time":
        clock_base = attained_at if from_level_id is not None else prereq_at
        gate = _eval_time_gate(rule, clock_base, now)
    elif gate_type == "count":
        gate = _eval_count_gate(rule, current_count)
    elif gate_type == "event":
        gate = _eval_event_gate(rule, result_events, attained_at)
    elif gate_type == "manual":
        gate = _eval_manual_gate(rule)
    else:  # defensive — schema CHECK already constrains this
        gate = {"gate_type": gate_type, "satisfied": False, "reason": "unknown_gate_type"}

    # --- age requirement ---------------------------------------------------
    min_age = rule["min_age"]
    age_satisfied = True
    age_info: dict[str, Any] | None = None
    if min_age is not None:
        age_known = age is not None
        # age unknown => requirement surfaced, treated as NOT satisfied for the
        # eligible bool (never fabricate eligibility).
        age_satisfied = age_known and age >= min_age
        age_info = {
            "age_requirement": min_age,
            "age_known": age_known,
            "age": age if age_known else None,
            "satisfied": age_satisfied,
        }

    eligible = bool(prereq_ok and gate.get("satisfied", False) and age_satisfied)

    result: dict[str, Any] = {
        "rule_id": rule["id"],
        "eligible": eligible,
        "gate": gate,
    }
    if prereq_info is not None:
        result["prerequisite"] = prereq_info
    if age_info is not None:
        result["age"] = age_info
    return result


# ---------------------------------------------------------------------------
# Per-track next-step evaluation
# ---------------------------------------------------------------------------


def _next_level_in_track(
    track_levels: list[sqlite3.Row], current: sqlite3.Row | None
) -> sqlite3.Row | None:
    """The level immediately above ``current`` in an ascending-ordinal track.

    With no current level, the next step is the lowest level the user must still
    *attain*. We treat the lowest-ordinal level as the entry target only when it
    is itself a rule target; otherwise the lowest level is the natural starting
    rung. Callers resolve "is there a rule into this level" separately.
    """
    if current is None:
        return track_levels[0] if track_levels else None
    for lvl in track_levels:
        if lvl["ordinal"] > current["ordinal"]:
            return lvl
    return None


def _evaluate_track(
    track: str,
    track_levels: list[sqlite3.Row],
    *,
    levels_by_id: dict[int, sqlite3.Row],
    rules_by_to: dict[int, list[sqlite3.Row]],
    attained: dict[int, datetime],
    current_count: int,
    result_events: list[tuple[str, str]],
    age: int | None,
    now: datetime,
) -> dict[str, Any]:
    """Build the status block for a single track."""
    current = _current_by_track_from(track_levels, attained)
    next_level = _next_level_in_track(track_levels, current)

    block: dict[str, Any] = {
        "track": track,
        "current_level": _level_brief(current, attained) if current is not None else None,
    }

    if next_level is None:
        block["next_level"] = None
        block["eligible"] = False
        block["paths"] = []
        return block

    # A target may have multiple rules (OR-paths, e.g. shōgō 교사). Evaluate each;
    # the transition is eligible if ANY path is eligible.
    rules = rules_by_to.get(next_level["id"], [])
    paths = [
        _eval_rule(
            rule,
            levels_by_id=levels_by_id,
            attained=attained,
            current_count=current_count,
            result_events=result_events,
            age=age,
            now=now,
        )
        for rule in rules
    ]

    block["next_level"] = _level_brief(next_level, attained)
    block["paths"] = paths
    block["eligible"] = any(p["eligible"] for p in paths) if paths else False
    # No rule into the next level: ladder defines the level but not how to reach
    # it programmatically (e.g. manual-only with no row). Surface that honestly.
    block["has_rule"] = bool(rules)
    return block


def _current_by_track_from(
    track_levels: list[sqlite3.Row], attained: dict[int, datetime]
) -> sqlite3.Row | None:
    """Highest attained level within a single (already-track-filtered) list."""
    best: sqlite3.Row | None = None
    for lvl in track_levels:
        if lvl["id"] in attained and (best is None or lvl["ordinal"] > best["ordinal"]):
            best = lvl
    return best


def _level_brief(level: sqlite3.Row, attained: dict[int, datetime]) -> dict[str, Any]:
    """A compact, renderer-friendly view of a level row."""
    attained_at = attained.get(level["id"])
    return {
        "id": level["id"],
        "track": level["track"],
        "ordinal": level["ordinal"],
        "code": level["code"],
        "label": level["label"],
        "attained_at": attained_at.isoformat() if attained_at else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def status_for_sub_tallies(
    activity_ids: Iterable[int],
    owner_id: int,
    *,
    age: int | None = None,
    now: datetime | None = None,
) -> dict[int, dict[str, Any]]:
    """Derived progression status for many sub-tallies, batched (no N+1).

    Reads ``level``, ``level_rule`` and the level/result entry history with one
    ``WHERE activity_id IN (...)`` query per table. Returns ``{activity_id:
    status}`` for every requested id; an id with no levels gets an empty
    ``tracks`` list (it isn't a progression ladder, or hasn't been seeded yet).

    ``age`` is optional (no birthdate is stored); when ``None`` any age-gated
    rule surfaces its requirement without fabricating eligibility. ``now`` is
    injectable for deterministic time math; it defaults to the current KST
    instant. **Eligibility is computed live here every call — never cached.**
    """
    ids = list(dict.fromkeys(int(s) for s in activity_ids))  # de-dupe, keep order
    if not ids:
        return {}

    reference = now if now is not None else _now()
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=KST)

    with db.connect() as conn:
        conn.execute("BEGIN")
        levels_by_sub = _load_levels(conn, owner_id, ids)
        rules_by_sub = _load_rules(conn, owner_id, ids)
        level_entries_by_sub = _load_level_entries(conn, owner_id, ids)
        result_events_by_sub = _load_result_events(conn, owner_id, ids)
        entry_counts = _load_entry_counts(conn, owner_id, ids)

    out: dict[int, dict[str, Any]] = {}
    for sid in ids:
        levels = levels_by_sub.get(sid, [])
        out[sid] = _build_status(
            levels=levels,
            rules=rules_by_sub.get(sid, []),
            level_entries=level_entries_by_sub.get(sid, []),
            result_events=result_events_by_sub.get(sid, []),
            entry_count=entry_counts.get(sid, 0),
            age=age,
            now=reference,
        )
    return out


def status(
    activity_id: int,
    owner_id: int,
    *,
    age: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Derived progression status for a single sub-tally (see
    ``status_for_sub_tallies`` for semantics)."""
    return status_for_sub_tallies([activity_id], owner_id, age=age, now=now)[int(activity_id)]


def _build_status(
    *,
    levels: list[sqlite3.Row],
    rules: list[sqlite3.Row],
    level_entries: list[tuple[str, str]],
    result_events: list[tuple[str, str]],
    entry_count: int,
    age: int | None,
    now: datetime,
) -> dict[str, Any]:
    """Assemble the full per-sub-tally status from its loaded truth."""
    if not levels:
        return {"is_progression": False, "tracks": []}

    levels_by_id = {lvl["id"]: lvl for lvl in levels}
    attained = _attainment(levels, level_entries)
    current_count = _count_for_gate(entry_count)

    rules_by_to: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for rule in rules:
        rules_by_to[rule["to_level_id"]].append(rule)

    # Group levels by track, preserving the ascending-ordinal order from SQL.
    levels_by_track: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for lvl in levels:
        levels_by_track[lvl["track"]].append(lvl)

    tracks = [
        _evaluate_track(
            track,
            track_levels,
            levels_by_id=levels_by_id,
            rules_by_to=rules_by_to,
            attained=attained,
            current_count=current_count,
            result_events=result_events,
            age=age,
            now=now,
        )
        for track, track_levels in levels_by_track.items()
    ]

    return {"is_progression": True, "tracks": tracks}


# ---------------------------------------------------------------------------
# Hero-field helper (the renderer seam)
# ---------------------------------------------------------------------------


def hero_field(activity_id: int, owner_id: int) -> dict[str, Any]:
    """Which field is the headline for a sub-tally, so renderers don't infer it.

    * ``count_mode == 'progression'`` → the **current level** is the hero
      (``hero: "level"``), with the current level per track and its label.
    * ``count_mode == 'running'`` → the **count** is the hero
      (``hero: "count"``), with the cached lifetime count.

    Returns a plain dict; raises ``SubTallyNotFoundError`` (from ``entries``) is
    *not* used here — instead a missing sub-tally yields ``None`` fields so a
    renderer degrades gracefully. The decision lives here, never in a template.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(
            conn,
            "activity",
            owner_id,
            where="id = ?",
            params=(activity_id,),
            columns="id, count_mode, cached_count",
        )

    if row is None:
        return {"activity_id": int(activity_id), "hero": None}

    if row["count_mode"] == "progression":
        st = status(activity_id, owner_id)
        current_levels = [
            t["current_level"] for t in st["tracks"] if t.get("current_level") is not None
        ]
        return {
            "activity_id": row["id"],
            "hero": "level",
            "count_mode": "progression",
            "current_levels": current_levels,
        }

    return {
        "activity_id": row["id"],
        "hero": "count",
        "count_mode": "running",
        "count": row["cached_count"],
    }
