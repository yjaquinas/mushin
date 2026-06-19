"""Connection ("fellow") service: the request → accept/decline lifecycle,
blocking, a single relationship-state helper, and a minimal request throttle.

Renderer-agnostic — no HTTP, no templates. Every public mutation opens its own
``db.connect()``, runs ``BEGIN`` so the whole unit of work is one transaction,
and returns plain Python data (ids, ``None``, or lists of dicts). Mirrors the
service style in ``app/auth/users.py``.

THE CANONICAL PAIR
------------------
``connection`` carries both the directed handshake (``requester_id`` ->
``addressee_id``) and a directionless canonical pair ``(user_lo, user_hi) =
(MIN, MAX)`` with ``UNIQUE(user_lo, user_hi)``. That unique index means A→B and
B→A can never both exist, so:

* a duplicate / reverse-duplicate request is caught *before* the insert and
  surfaced as ``AlreadyExistsError`` — never a leaked ``sqlite3.IntegrityError``;
* a re-request after a ``declined`` row **reuses** the same row (reset to
  pending) rather than inserting a colliding pair.

CONSENT
-------
``sharing_consent_at`` is stamped on ``accept`` (the deliberate
consequence-screen confirm). ``profiles.is_connected`` requires BOTH
``status='accepted'`` AND a non-null ``sharing_consent_at`` to call a pair
"fellows" — so accept here is what flips the fellow bit.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.models import db
from app.services import profiles

# Throttle: max pending/handshake requests a single requester may create in a
# rolling 24h window. SQLite-only (counts the requester's own connection rows),
# no extra table. A re-request that reuses a declined row also counts.
MAX_PENDING_REQUESTS_PER_DAY = 20

RelationshipState = Literal[
    "self",
    "blocked",
    "fellow",
    "pending_outgoing",
    "pending_incoming",
    "none",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConnectionError(Exception):
    """Base class for connection-layer errors."""


class SelfConnectionError(ConnectionError):
    """Raised when a user tries to connect to / block themselves."""


class AlreadyExistsError(ConnectionError):
    """Raised when a pending or accepted connection already exists for the pair."""


class BlockedError(ConnectionError):
    """Raised when a block in either direction forbids the request."""


class RateLimitedError(ConnectionError):
    """Raised when the requester has exceeded the per-day request throttle."""


class NotFoundError(ConnectionError):
    """Raised when the targeted row (e.g. a pending request to accept) is absent."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    """Return the directionless canonical pair ``(lo, hi) = (MIN(a,b), MAX(a,b))``.

    Computed identically to ``profiles`` (and the ``connection`` unique index),
    so a lookup by canonical pair always hits the one row for a given pair
    regardless of who requested whom.
    """
    return (a, b) if a < b else (b, a)


# ---------------------------------------------------------------------------
# Request lifecycle
# ---------------------------------------------------------------------------


def send_request(requester_id: int, addressee_id: int) -> int:
    """Send a connection request from *requester_id* to *addressee_id*.

    Returns the connection id. Raises:

    * ``SelfConnectionError`` — requester == addressee.
    * ``BlockedError`` — a block exists in either direction.
    * ``AlreadyExistsError`` — a ``pending`` or ``accepted`` row already covers
      the pair (in either direction).
    * ``RateLimitedError`` — the requester created
      ``MAX_PENDING_REQUESTS_PER_DAY`` rows in the last 24h.

    A prior ``declined`` row for the pair is **reused**: it is reset to
    ``pending`` with the new requester/addressee orientation, a fresh
    ``created_at``, and a cleared ``responded_at`` / ``sharing_consent_at``.
    This both honours the unique-pair index and lets a declined party be
    re-approached. ``sqlite3.IntegrityError`` is never leaked.
    """
    if requester_id == addressee_id:
        raise SelfConnectionError("cannot connect to yourself")

    lo, hi = _canonical_pair(requester_id, addressee_id)
    now = _now_iso()

    with db.connect() as conn:
        conn.execute("BEGIN")

        if profiles.is_blocked(conn, requester_id, addressee_id):
            # No existence oracle: a generic block error, same either direction.
            raise BlockedError("a block prevents this connection")

        existing = conn.execute(
            "SELECT id, status FROM connection WHERE user_lo = ? AND user_hi = ?",
            (lo, hi),
        ).fetchone()

        if existing is not None and existing["status"] in ("pending", "accepted"):
            raise AlreadyExistsError("a connection already exists for this pair")

        # Throttle: count this requester's rows created in the last 24h. Done
        # after the cheap rejections so a self/blocked/dup request never trips
        # (or is masked by) the limit.
        cutoff = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM connection WHERE requester_id = ? AND created_at >= ?",
            (requester_id, cutoff),
        ).fetchone()
        if recent["n"] >= MAX_PENDING_REQUESTS_PER_DAY:
            raise RateLimitedError("too many connection requests; try again later")

        if existing is not None:
            # Reuse the declined row (the only non-pending/accepted state left).
            conn.execute(
                "UPDATE connection SET requester_id = ?, addressee_id = ?,"
                " status = 'pending', created_at = ?, responded_at = NULL,"
                " sharing_consent_at = NULL WHERE id = ?",
                (requester_id, addressee_id, now, existing["id"]),
            )
            return int(existing["id"])

        cur = conn.execute(
            "INSERT INTO connection"
            " (requester_id, addressee_id, status, user_lo, user_hi, created_at)"
            " VALUES (?, ?, 'pending', ?, ?, ?)",
            (requester_id, addressee_id, lo, hi, now),
        )
        return int(cur.lastrowid)


def accept(addressee_id: int, requester_id: int) -> None:
    """Accept a pending incoming request. Only the addressee may accept.

    Sets ``status='accepted'`` and stamps both ``sharing_consent_at`` and
    ``responded_at`` to now — accepting *is* the sharing-consent confirm, so
    this is what makes the pair fellows. Raises ``NotFoundError`` when there is
    no ``pending`` row addressed to *addressee_id* from *requester_id*.
    """
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "UPDATE connection SET status = 'accepted', sharing_consent_at = ?,"
            " responded_at = ? WHERE addressee_id = ? AND requester_id = ?"
            " AND status = 'pending'",
            (now, now, addressee_id, requester_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError("no pending request to accept")


def decline(addressee_id: int, requester_id: int) -> None:
    """Decline a pending incoming request → terminal ``declined`` row.

    Only the addressee may decline. Leaves the row in place (so the pair can
    re-request via ``send_request``, which reuses it). Raises ``NotFoundError``
    when there is no matching ``pending`` row.
    """
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "UPDATE connection SET status = 'declined', responded_at = ?"
            " WHERE addressee_id = ? AND requester_id = ? AND status = 'pending'",
            (now, addressee_id, requester_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError("no pending request to decline")


def cancel(requester_id: int, addressee_id: int) -> None:
    """Withdraw one's own pending outgoing request.

    Deletes the ``pending`` row so the pair is clear and can be re-sent later.
    No-op-safe: if there is no such pending row (already accepted, declined, or
    never existed), nothing happens.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection WHERE requester_id = ? AND addressee_id = ?"
            " AND status = 'pending'",
            (requester_id, addressee_id),
        )


def disconnect(user_id: int, other_id: int) -> None:
    """Remove an accepted connection. Either party may call this.

    Deletes the canonical-pair row when it is ``accepted`` (revoking fellow
    access in both directions immediately). Idempotent: a no-op when no
    accepted row exists.
    """
    lo, hi = _canonical_pair(user_id, other_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection WHERE user_lo = ? AND user_hi = ? AND status = 'accepted'",
            (lo, hi),
        )


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


def block(blocker_id: int, blocked_id: int) -> None:
    """Block *blocked_id*. Idempotent; also tears down any connection.

    Inserts a ``block`` row (ignored if it already exists) and deletes any
    ``connection`` row for the pair in either direction — a block revokes a
    fellow relationship and cancels any pending handshake immediately, both
    ways. Raises ``SelfConnectionError`` on self-block.
    """
    if blocker_id == blocked_id:
        raise SelfConnectionError("cannot block yourself")

    lo, hi = _canonical_pair(blocker_id, blocked_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT OR IGNORE INTO block (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
            (blocker_id, blocked_id, _now_iso()),
        )
        # Tear down the connection for the pair regardless of status/direction.
        conn.execute(
            "DELETE FROM connection WHERE user_lo = ? AND user_hi = ?",
            (lo, hi),
        )


def unblock(blocker_id: int, blocked_id: int) -> None:
    """Lift a block *blocker_id* placed on *blocked_id*. Idempotent.

    Deletes only the directed ``block`` row this blocker owns; it does not
    restore any prior connection (that requires a fresh request).
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM block WHERE blocker_id = ? AND blocked_id = ?",
            (blocker_id, blocked_id),
        )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _other_user_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
    }


def list_fellows(user_id: int) -> list[dict]:
    """List *user_id*'s fellows (accepted + consented), each the OTHER user.

    Returns ``[{id, username, display_name}, ...]`` ordered by username for a
    stable display. A fellow requires ``status='accepted' AND
    sharing_consent_at IS NOT NULL`` — the same bar as
    ``profiles.is_connected``.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT u.id, u.username, u.display_name FROM connection c"
            " JOIN user u ON u.id = CASE WHEN c.user_lo = ? THEN c.user_hi"
            " ELSE c.user_lo END"
            " WHERE (c.user_lo = ? OR c.user_hi = ?)"
            " AND c.status = 'accepted' AND c.sharing_consent_at IS NOT NULL"
            " ORDER BY u.username",
            (user_id, user_id, user_id),
        ).fetchall()
        return [_other_user_dict(r) for r in rows]


def list_incoming_pending(user_id: int) -> list[dict]:
    """List pending requests *addressed to* *user_id*.

    Returns ``[{connection_id, id, username, display_name}, ...]`` — the other
    user (the requester) plus the connection id — ordered by username.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT c.id AS connection_id, u.id, u.username, u.display_name"
            " FROM connection c JOIN user u ON u.id = c.requester_id"
            " WHERE c.addressee_id = ? AND c.status = 'pending'"
            " ORDER BY u.username",
            (user_id,),
        ).fetchall()
        return [{"connection_id": r["connection_id"], **_other_user_dict(r)} for r in rows]


def list_outgoing_pending(user_id: int) -> list[dict]:
    """List pending requests *sent by* *user_id*.

    Returns ``[{connection_id, id, username, display_name}, ...]`` — the other
    user (the addressee) plus the connection id — ordered by username.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT c.id AS connection_id, u.id, u.username, u.display_name"
            " FROM connection c JOIN user u ON u.id = c.addressee_id"
            " WHERE c.requester_id = ? AND c.status = 'pending'"
            " ORDER BY u.username",
            (user_id,),
        ).fetchall()
        return [{"connection_id": r["connection_id"], **_other_user_dict(r)} for r in rows]


def pending_count(user_id: int) -> int:
    """Count pending requests addressed to *user_id* (the inbox badge number)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM connection WHERE addressee_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
        return int(row["n"])


def relationship_state(user_id: int, other_id: int) -> RelationshipState:
    """Resolve *user_id*'s relationship to *other_id* in one call.

    Returns one of ``"self" | "blocked" | "fellow" | "pending_outgoing" |
    "pending_incoming" | "none"``, evaluated in this precedence (first wins):

    1. ``"self"``             — same user.
    2. ``"blocked"``          — a block in either direction (from the actor's POV
       a block is a block; no existence oracle).
    3. ``"fellow"``           — accepted + consented connection.
    4. ``"pending_outgoing"`` — a pending request *user_id* sent.
    5. ``"pending_incoming"`` — a pending request *user_id* received.
    6. ``"none"``             — anything else (incl. a declined row).

    The UI (Task 6) and search (Task 9) use this to pick the Connect /
    Requested / Respond / "You're fellows" affordance.
    """
    if user_id == other_id:
        return "self"

    lo, hi = _canonical_pair(user_id, other_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if profiles.is_blocked(conn, user_id, other_id):
            return "blocked"
        if profiles.is_connected(conn, user_id, other_id):
            return "fellow"
        row = conn.execute(
            "SELECT requester_id, status FROM connection WHERE user_lo = ? AND user_hi = ?",
            (lo, hi),
        ).fetchone()

    if row is not None and row["status"] == "pending":
        if row["requester_id"] == user_id:
            return "pending_outgoing"
        return "pending_incoming"
    return "none"
