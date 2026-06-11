"""Competition (match-list persistence + W/L/D stats) for the Mushin service layer.

Renderer-agnostic: no HTTP, no Jinja, no HXML. Every function takes ``owner_id``
as a required argument (multi-user isolation is non-negotiable) and returns plain
Python data structures (dicts / lists of dicts) that either renderer can consume.

The fact shape
--------------
A tournament is modelled as a ``sub_tally`` carrying a ``field_def`` of kind
``match_list``. Each *entry* under it (one tournament outing / day) can record
many individual bouts. A bout is **not** scattered into ``entry_value``; it is a
structured multi-column fact in its own ``match`` table — opponent, score, and a
``result`` constrained to ``win`` / ``loss`` / ``draw``. ``match`` carries its own
``owner_id`` so a bout can never reach across tenants.

Owner isolation
---------------
Persistence validates the parent entry belongs to *owner_id* before writing any
match row, and stamps that same ``owner_id`` onto each row. Every read filters by
``owner_id`` — the per-sub-tally stats join ``match -> entry`` and scope **both**
sides to the owner, so a user can never aggregate another user's bouts even if an
id were guessed.

win_rate denominator
--------------------
``win_rate = wins / (wins + losses + draws)`` — the denominator is **all decided
bouts including draws**. A draw is a real outcome that happened on the strip, not
a non-event, so it dilutes the win rate rather than being discarded. The returned
record also exposes ``decided`` (that denominator) so a renderer can show the
basis, and ``win_rate`` is ``None`` when there are no bouts at all (0/0 is
undefined, not zero).
"""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.models import db
from app.services import _db

_RESULTS = frozenset({"win", "loss", "draw"})


class EntryNotFoundError(LookupError):
    """Raised when the parent entry doesn't exist for the given owner."""


class MatchPayloadError(ValueError):
    """Raised when a match row is malformed (bad result, missing field)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_entry(conn: sqlite3.Connection, owner_id: int, entry_id: int) -> int:
    """Assert *entry_id* belongs to *owner_id*; return its sub_tally_id.

    Reads through the owner-scoped ``entry`` accessor so an entry owned by
    another tenant is indistinguishable from one that does not exist.
    """
    row = _db.fetch_one(
        conn, "entry", owner_id, where="id = ?", params=(entry_id,), columns="sub_tally_id"
    )
    if row is None:
        raise EntryNotFoundError(f"entry {entry_id} not found for owner {owner_id}")
    return row["sub_tally_id"]


def _normalize_rows(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, str, str, int]]:
    """Validate + normalize match payload rows into insert tuples.

    Each input row is a mapping with ``opponent``, ``score``, ``result`` and an
    optional ``sort_order``. When ``sort_order`` is omitted, rows are numbered by
    their position in the input so caller-supplied order is preserved.
    """
    normalized: list[tuple[str, str, str, int]] = []
    for index, raw in enumerate(rows):
        result = raw.get("result")
        if result not in _RESULTS:
            raise MatchPayloadError(f"match result {result!r} must be one of {sorted(_RESULTS)}")
        opponent = raw.get("opponent")
        score = raw.get("score")
        if opponent is None or score is None:
            raise MatchPayloadError("match row requires 'opponent' and 'score'")
        sort_order = raw.get("sort_order")
        sort_order = index if sort_order is None else int(sort_order)
        normalized.append((str(opponent), str(score), str(result), sort_order))
    return normalized


def _insert_rows(
    conn: sqlite3.Connection,
    owner_id: int,
    entry_id: int,
    normalized: Sequence[tuple[str, str, str, int]],
) -> None:
    for opponent, score, result, sort_order in normalized:
        conn.execute(
            "INSERT INTO match (entry_id, owner_id, opponent, score, result, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (entry_id, owner_id, opponent, score, result, sort_order),
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "entry_id": row["entry_id"],
        "owner_id": row["owner_id"],
        "opponent": row["opponent"],
        "score": row["score"],
        "result": row["result"],
        "sort_order": row["sort_order"],
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def add_matches(
    owner_id: int, entry_id: int, rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Append match rows to *entry_id* (owned by *owner_id*).

    Validates the parent entry's ownership before inserting, and stamps
    ``owner_id`` onto every row. *rows* is an iterable of mappings with
    ``opponent`` / ``score`` / ``result`` (and optional ``sort_order``). Returns
    the full, ordered match list for the entry after the insert.
    """
    normalized = _normalize_rows(rows)
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_entry(conn, owner_id, entry_id)
        _insert_rows(conn, owner_id, entry_id, normalized)
        return _list_matches(conn, owner_id, entry_id)


def list_matches(owner_id: int, entry_id: int) -> list[dict[str, Any]]:
    """List an entry's match rows, scoped to *owner_id*, in ``sort_order``.

    Validates entry ownership first so reading another tenant's entry id raises
    rather than silently returning an empty list.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_entry(conn, owner_id, entry_id)
        return _list_matches(conn, owner_id, entry_id)


def _list_matches(conn: sqlite3.Connection, owner_id: int, entry_id: int) -> list[dict[str, Any]]:
    rows = _db.fetch_all(
        conn,
        "match",
        owner_id,
        where="entry_id = ?",
        params=(entry_id,),
        order_by="sort_order ASC, id ASC",
    )
    return [_row_to_dict(r) for r in rows]


def replace_matches(
    owner_id: int, entry_id: int, rows: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Fully replace an entry's match rows (edit path), scoped to *owner_id*.

    Deletes the entry's existing bouts and inserts the new set in one
    transaction. Returns the resulting ordered match list.
    """
    normalized = _normalize_rows(rows)
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_entry(conn, owner_id, entry_id)
        _db.delete(conn, "match", owner_id, where="entry_id = ?", params=(entry_id,))
        _insert_rows(conn, owner_id, entry_id, normalized)
        return _list_matches(conn, owner_id, entry_id)


def delete_matches(owner_id: int, entry_id: int) -> int:
    """Delete all of an entry's match rows, scoped to *owner_id*.

    Returns the number of rows removed. Validates entry ownership first.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _require_entry(conn, owner_id, entry_id)
        return _db.delete(conn, "match", owner_id, where="entry_id = ?", params=(entry_id,))


# ---------------------------------------------------------------------------
# Stats (per sub_tally, owner-scoped, across its tournament entries' matches)
# ---------------------------------------------------------------------------


def _scoped_matches_for_sub_tally(
    conn: sqlite3.Connection, owner_id: int, sub_tally_id: int
) -> list[sqlite3.Row]:
    """All match rows under a sub-tally's entries, owner-scoped on both sides.

    Joins ``match -> entry`` so a bout is only counted when *both* the match and
    its parent entry belong to *owner_id* and the entry sits under
    *sub_tally_id*. Ordered oldest-first by the entry's ``occurred_at`` (then
    ``sort_order``) so the results timeline is chronological.
    """
    return conn.execute(
        """
        SELECT m.id, m.entry_id, m.opponent, m.score, m.result, m.sort_order,
               e.occurred_at
          FROM match m
          JOIN entry e ON e.id = m.entry_id
         WHERE m.owner_id = ?
           AND e.owner_id = ?
           AND e.sub_tally_id = ?
         ORDER BY e.occurred_at ASC, m.sort_order ASC, m.id ASC
        """,
        (owner_id, owner_id, sub_tally_id),
    ).fetchall()


def record(owner_id: int, sub_tally_id: int) -> dict[str, Any]:
    """W/L/D record + win rate for a tournament sub-tally, scoped to *owner_id*.

    Returns ``{wins, losses, draws, total, decided, win_rate}`` where ``decided``
    is ``wins + losses + draws`` (every bout is decided, so ``decided == total``;
    both are exposed for clarity), and ``win_rate = wins / decided`` including
    draws in the denominator, or ``None`` when there are no bouts.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        matches = _scoped_matches_for_sub_tally(conn, owner_id, sub_tally_id)
    return _record_from_matches(matches)


def _record_from_matches(matches: Sequence[sqlite3.Row]) -> dict[str, Any]:
    wins = sum(1 for m in matches if m["result"] == "win")
    losses = sum(1 for m in matches if m["result"] == "loss")
    draws = sum(1 for m in matches if m["result"] == "draw")
    decided = wins + losses + draws
    win_rate = (wins / decided) if decided else None
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "total": len(matches),
        "decided": decided,
        "win_rate": win_rate,
    }


def results_timeline(owner_id: int, sub_tally_id: int) -> list[dict[str, Any]]:
    """Chronological list of bout results for a tournament sub-tally.

    Each item is ``{occurred_at, opponent, result, score}`` ordered oldest-first
    by the parent entry's ``occurred_at`` (ties broken by ``sort_order``), so a
    renderer can draw a form line / W-L streak directly.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        matches = _scoped_matches_for_sub_tally(conn, owner_id, sub_tally_id)
        return [
            {
                "occurred_at": m["occurred_at"],
                "opponent": m["opponent"],
                "result": m["result"],
                "score": m["score"],
            }
            for m in matches
        ]


def head_to_head(owner_id: int, sub_tally_id: int) -> list[dict[str, Any]]:
    """W/L/D vs each opponent for a tournament sub-tally, scoped to *owner_id*.

    Groups every bout under the sub-tally by ``opponent`` — the same opponent met
    across different tournament entries aggregates into one record. Returns a list
    of ``{opponent, wins, losses, draws, total, win_rate}`` ordered by most bouts
    played (then opponent name) so the biggest rivalries surface first.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        matches = _scoped_matches_for_sub_tally(conn, owner_id, sub_tally_id)

    grouped: OrderedDict[str, list[sqlite3.Row]] = OrderedDict()
    for m in matches:
        grouped.setdefault(m["opponent"], []).append(m)

    h2h = []
    for opponent, bouts in grouped.items():
        rec = _record_from_matches(bouts)
        h2h.append(
            {
                "opponent": opponent,
                "wins": rec["wins"],
                "losses": rec["losses"],
                "draws": rec["draws"],
                "total": rec["total"],
                "win_rate": rec["win_rate"],
            }
        )
    h2h.sort(key=lambda r: (-r["total"], r["opponent"]))
    return h2h
