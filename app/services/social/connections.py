"""Connection ("fellow") service: the request → accept/decline lifecycle,
blocking, a single relationship-state helper, and a minimal request throttle.

Renderer-agnostic — no HTTP, no templates. Every public mutation opens its own
``db.connect()``, runs ``BEGIN`` so the whole unit of work is one transaction,
and returns plain Python data (ids, ``None``, or lists of dicts).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal

from app.models import db
from app.services.social import notifications, profiles

RelationshipState = Literal[
    "self",
    "blocked",
    "fellow",
    "pending_outgoing",
    "pending_incoming",
    "none",
]


MAX_PENDING_REQUESTS_PER_DAY = 20


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
    """Raised when the targeted row is absent."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


# ---------------------------------------------------------------------------
# Request lifecycle
# ---------------------------------------------------------------------------


def send_request(requester_id: int, addressee_id: int) -> int:
    """Send a connection request from *requester_id* to *addressee_id*."""
    if requester_id == addressee_id:
        raise SelfConnectionError("cannot connect to yourself")

    lo, hi = _canonical_pair(requester_id, addressee_id)
    now = _now_iso()

    with db.connect() as conn:
        conn.execute("BEGIN")

        if profiles.is_blocked(conn, requester_id, addressee_id):
            raise BlockedError("a block prevents this connection")

        # Check rate limit.
        cutoff = _now_iso()
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM connection"
            " WHERE requester_id = ? AND created_at >= ?",
            (requester_id, cutoff),
        ).fetchone()
        if recent["n"] >= MAX_PENDING_REQUESTS_PER_DAY:
            raise RateLimitedError("rate limit exceeded")

        existing = conn.execute(
            "SELECT id, status FROM connection WHERE user_lo = ? AND user_hi = ?",
            (lo, hi),
        ).fetchone()

        if existing is not None:
            if existing["status"] in ("pending", "accepted"):
                raise AlreadyExistsError("a pending or accepted connection already exists")
            # Reuse a declined row.
            conn.execute(
                "UPDATE connection SET requester_id = ?, addressee_id = ?, status = 'pending',"
                " responded_at = NULL, sharing_consent_at = NULL, created_at = ?"
                " WHERE id = ?",
                (requester_id, addressee_id, now, existing["id"]),
            )
            notifications.create(
                conn,
                user_id=addressee_id,
                type="connection_request",
                actor_id=requester_id,
                created_at=now,
            )
            return existing["id"]

        cur = conn.execute(
            "INSERT INTO connection"
            " (requester_id, addressee_id, user_lo, user_hi, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (requester_id, addressee_id, lo, hi, now),
        )
        notifications.create(
            conn,
            user_id=addressee_id,
            type="connection_request",
            actor_id=requester_id,
            created_at=now,
        )
        return cur.lastrowid


def accept_request(connection_id: int, acceptor_id: int) -> dict:
    """Accept a pending connection request by connection ID."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM connection WHERE id = ? AND addressee_id = ? AND status = 'pending'",
            (connection_id, acceptor_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"connection {connection_id} not found or not pending")
        now = _now_iso()
        conn.execute(
            "UPDATE connection SET status = 'accepted', sharing_consent_at = ?, responded_at = ?"
            " WHERE id = ?",
            (now, now, connection_id),
        )
        notifications.create(
            conn,
            user_id=int(row["requester_id"]),
            type="connection_accepted",
            actor_id=acceptor_id,
            created_at=now,
        )
        return dict(row)


def accept(owner_id: int, other_id: int) -> dict:
    """Accept a pending connection request from *other_id* to *owner_id*.

    Finds the pending connection between the two users and accepts it.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM connection"
            " WHERE user_lo = ? AND user_hi = ? AND status = 'pending' AND addressee_id = ?",
            (min(owner_id, other_id), max(owner_id, other_id), owner_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no pending connection between {owner_id} and {other_id}")
        now = _now_iso()
        conn.execute(
            "UPDATE connection SET status = 'accepted', sharing_consent_at = ?, responded_at = ?"
            " WHERE id = ?",
            (now, now, row["id"]),
        )
        notifications.create(
            conn,
            user_id=int(row["requester_id"]),
            type="connection_accepted",
            actor_id=owner_id,
            created_at=now,
        )
        return dict(row)



def decline(owner_id: int, other_id: int) -> dict:
    """Decline a pending connection request from *other_id* to *owner_id*.

    Finds the pending connection between the two users and declines it.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM connection"
            " WHERE user_lo = ? AND user_hi = ? AND status = 'pending' AND addressee_id = ?",
            (min(owner_id, other_id), max(owner_id, other_id), owner_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no pending connection between {owner_id} and {other_id}")
        now = _now_iso()
        conn.execute(
            "UPDATE connection SET status = 'declined', responded_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        return dict(row)


def cancel(owner_id: int, other_id: int) -> None:
    """Cancel an outgoing pending connection request to *other_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection"
            " WHERE user_lo = ? AND user_hi = ? AND requester_id = ? AND status = 'pending'",
            (min(owner_id, other_id), max(owner_id, other_id), owner_id),
        )


def disconnect(user_id: int, other_id: int) -> None:
    """Remove an accepted connection with *other_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection"
            " WHERE user_lo = ? AND user_hi = ? AND status = 'accepted'",
            (min(user_id, other_id), max(user_id, other_id)),
        )


def unblock(blocker_id: int, blocked_id: int) -> None:
    """Remove a block (alias for ``cancel_block``)."""
    cancel_block(blocker_id, blocked_id)


def decline_request(connection_id: int, acceptor_id: int) -> dict:
    """Decline a pending connection request."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM connection WHERE id = ? AND addressee_id = ? AND status = 'pending'",
            (connection_id, acceptor_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"connection {connection_id} not found or not pending")
        now = _now_iso()
        conn.execute(
            "UPDATE connection SET status = 'declined', responded_at = ? WHERE id = ?",
            (now, connection_id),
        )
        return dict(row)


def withdraw_request(connection_id: int, requester_id: int) -> None:
    """Withdraw a pending connection request."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection WHERE id = ? AND requester_id = ? AND status = 'pending'",
            (connection_id, requester_id),
        )


def remove_connection(connection_id: int, user_id: int) -> None:
    """Remove a connection (either party can remove)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM connection WHERE id = ? AND (requester_id = ? OR addressee_id = ?)"
            " AND status = 'accepted'",
            (connection_id, user_id, user_id),
        )


def cancel_block(blocker_id: int, blocked_id: int) -> None:
    """Remove a block."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM block WHERE blocker_id = ? AND blocked_id = ?",
            (blocker_id, blocked_id),
        )


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------


def block_user(blocker_id: int, blocked_id: int) -> None:
    """Block another user."""
    if blocker_id == blocked_id:
        raise SelfConnectionError("cannot block yourself")

    with db.connect() as conn:
        conn.execute("BEGIN")
        if profiles.is_blocked(conn, blocked_id, blocker_id):
            raise BlockedError("a block in the other direction prevents this")

        # Remove any existing connection.
        conn.execute(
            "DELETE FROM connection WHERE (requester_id = ? AND addressee_id = ?)"
            " OR (requester_id = ? AND addressee_id = ?)",
            (blocker_id, blocked_id, blocked_id, blocker_id),
        )

        conn.execute(
            "INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)",
            (blocker_id, blocked_id),
        )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _other_user_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
    }


def list_fellows(user_id: int) -> list[dict]:
    """List *user_id*'s fellows (accepted + consented)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT u.id, u.username FROM connection c"
            " JOIN user u ON u.id = CASE WHEN c.user_lo = ? THEN c.user_hi"
            " ELSE c.user_lo END"
            " WHERE (c.user_lo = ? OR c.user_hi = ?)"
            " AND c.status = 'accepted' AND c.sharing_consent_at IS NOT NULL"
            " AND u.deleted_at IS NULL AND u.suspended_at IS NULL"
            " ORDER BY u.username",
            (user_id, user_id, user_id),
        ).fetchall()
        return [_other_user_dict(r) for r in rows]


def list_incoming_pending(user_id: int) -> list[dict]:
    """List pending requests *addressed to* *user_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT c.id AS connection_id, u.id, u.username"
            " FROM connection c JOIN user u ON u.id = c.requester_id"
            " WHERE c.addressee_id = ? AND c.status = 'pending'"
            " ORDER BY u.username",
            (user_id,),
        ).fetchall()
        return [{"connection_id": r["connection_id"], **_other_user_dict(r)} for r in rows]


def list_outgoing_pending(user_id: int) -> list[dict]:
    """List pending requests *sent by* *user_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT c.id AS connection_id, u.id, u.username"
            " FROM connection c JOIN user u ON u.id = c.addressee_id"
            " WHERE c.requester_id = ? AND c.status = 'pending'"
            " ORDER BY u.username",
            (user_id,),
        ).fetchall()
        return [{"connection_id": r["connection_id"], **_other_user_dict(r)} for r in rows]


def pending_count(user_id: int) -> int:
    """Count pending requests addressed to *user_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM connection WHERE addressee_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
        return int(row["n"])


def relationship_state(user_id: int, other_id: int) -> RelationshipState:
    """Resolve *user_id*'s relationship to *other_id*."""
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


# ---------------------------------------------------------------------------
# Aliases for handler convenience
# ---------------------------------------------------------------------------

block = block_user  # alias: handler calls connections.block()
