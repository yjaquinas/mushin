"""Unit tests for the connection ("fellow") service (social-graph Task 3).

Covers the full request lifecycle (request → pending → accept/decline), cancel,
disconnect, blocking + teardown, the single ``relationship_state`` helper, and
the per-day request throttle.

Each test gets a fresh tmp_path-scoped SQLite DB with all migrations applied,
with ``app.models.db.DATABASE_PATH`` monkeypatched at it so the service's own
``db.connect()`` hits the test database (the ``test_users.py`` pattern).
``profiles.is_connected`` is exercised end-to-end to prove accept stamps
``sharing_consent_at``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.auth import users
from app.models.migrate import run_migrations
from app.services import connections, profiles


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "test.db"
    run_migrations(path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(path))
    return path


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_user(db_path: Path, username: str) -> int:
    conn = _raw(db_path)
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, display_name) VALUES ('email', ?, ?)",
        (username, username.title()),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _row_status(db_path: Path, lo: int, hi: int) -> sqlite3.Row | None:
    if lo > hi:
        lo, hi = hi, lo
    conn = _raw(db_path)
    row = conn.execute(
        "SELECT * FROM connection WHERE user_lo = ? AND user_hi = ?", (lo, hi)
    ).fetchone()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Full lifecycle: request → pending → accept
# ---------------------------------------------------------------------------


def test_send_request_creates_pending(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    cid = connections.send_request(a, b)
    assert isinstance(cid, int)
    row = _row_status(db_path, a, b)
    assert row["status"] == "pending"
    assert row["sharing_consent_at"] is None


def test_pending_visible_only_to_addressee(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    # b is the addressee: sees it incoming; a sees it outgoing.
    incoming = connections.list_incoming_pending(b)
    outgoing = connections.list_outgoing_pending(a)
    assert [u["id"] for u in incoming] == [a]
    assert [u["id"] for u in outgoing] == [b]
    # The reverse views are empty.
    assert connections.list_incoming_pending(a) == []
    assert connections.list_outgoing_pending(b) == []
    assert connections.pending_count(b) == 1
    assert connections.pending_count(a) == 0


def test_accept_makes_fellows_and_stamps_consent(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    row = _row_status(db_path, a, b)
    assert row["status"] == "accepted"
    assert row["sharing_consent_at"] is not None
    assert row["responded_at"] is not None
    # profiles.is_connected (the fellow authority) now reports true both ways.
    conn = _raw(db_path)
    assert profiles.is_connected(conn, a, b) is True
    assert profiles.is_connected(conn, b, a) is True
    conn.close()
    # And both list each other as a fellow.
    assert [u["id"] for u in connections.list_fellows(a)] == [b]
    assert [u["id"] for u in connections.list_fellows(b)] == [a]


def test_accept_by_non_addressee_raises(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    # The requester cannot accept their own request.
    with pytest.raises(connections.NotFoundError):
        connections.accept(a, b)


def test_accept_without_pending_raises(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    with pytest.raises(connections.NotFoundError):
        connections.accept(b, a)


# ---------------------------------------------------------------------------
# Decline + re-request
# ---------------------------------------------------------------------------


def test_decline_leaves_terminal_declined_row(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.decline(b, a)
    row = _row_status(db_path, a, b)
    assert row["status"] == "declined"
    assert row["responded_at"] is not None
    conn = _raw(db_path)
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_decline_without_pending_raises(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    with pytest.raises(connections.NotFoundError):
        connections.decline(b, a)


def test_rerequest_after_decline_reuses_row(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    cid1 = connections.send_request(a, b)
    connections.decline(b, a)
    cid2 = connections.send_request(a, b)
    # Same row reused — no duplicate pair.
    assert cid1 == cid2
    conn = _raw(db_path)
    n = conn.execute("SELECT COUNT(*) AS n FROM connection").fetchone()["n"]
    conn.close()
    assert n == 1
    row = _row_status(db_path, a, b)
    assert row["status"] == "pending"
    assert row["responded_at"] is None


def test_rerequest_after_decline_can_flip_direction(db_path: Path) -> None:
    """The previously-declined addressee may re-approach the original requester."""
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.decline(b, a)
    # Now b requests a — reuses the same canonical-pair row, new orientation.
    cid = connections.send_request(b, a)
    row = _row_status(db_path, a, b)
    assert row["id"] == cid
    assert row["status"] == "pending"
    assert row["requester_id"] == b
    assert row["addressee_id"] == a


# ---------------------------------------------------------------------------
# Duplicate / reverse-duplicate rejection (never IntegrityError)
# ---------------------------------------------------------------------------


def test_duplicate_request_rejected_cleanly(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    with pytest.raises(connections.AlreadyExistsError):
        connections.send_request(a, b)


def test_reverse_duplicate_request_rejected_cleanly(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    # b → a collides on the canonical pair; must NOT leak IntegrityError.
    with pytest.raises(connections.AlreadyExistsError):
        connections.send_request(b, a)


def test_request_against_accepted_rejected(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    with pytest.raises(connections.AlreadyExistsError):
        connections.send_request(b, a)


def test_self_request_rejected(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    with pytest.raises(connections.SelfConnectionError):
        connections.send_request(a, a)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_removes_pending(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.cancel(a, b)
    assert _row_status(db_path, a, b) is None
    # The pair is clear, so a fresh request succeeds.
    connections.send_request(a, b)
    assert _row_status(db_path, a, b)["status"] == "pending"


def test_cancel_is_noop_safe(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    # No pending row — must not raise.
    connections.cancel(a, b)
    assert _row_status(db_path, a, b) is None


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


def test_disconnect_removes_accepted(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    # Either party may disconnect.
    connections.disconnect(b, a)
    assert _row_status(db_path, a, b) is None
    conn = _raw(db_path)
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_disconnect_is_idempotent(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    connections.disconnect(a, b)
    # Second call is a no-op, not an error.
    connections.disconnect(a, b)
    assert _row_status(db_path, a, b) is None


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


def test_block_tears_down_connection(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    connections.block(a, b)
    # Connection row gone; block row present.
    assert _row_status(db_path, a, b) is None
    conn = _raw(db_path)
    assert profiles.is_blocked(conn, a, b) is True
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_block_tears_down_pending(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.block(b, a)  # addressee blocks requester
    assert _row_status(db_path, a, b) is None


def test_block_prevents_request(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.block(a, b)
    # Blocker cannot request.
    with pytest.raises(connections.BlockedError):
        connections.send_request(a, b)
    # Blocked party also cannot request (no existence oracle).
    with pytest.raises(connections.BlockedError):
        connections.send_request(b, a)


def test_block_is_idempotent(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.block(a, b)
    connections.block(a, b)  # no IntegrityError, no extra row
    conn = _raw(db_path)
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM block WHERE blocker_id = ? AND blocked_id = ?",
        (a, b),
    ).fetchone()["n"]
    conn.close()
    assert n == 1


def test_self_block_rejected(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    with pytest.raises(connections.SelfConnectionError):
        connections.block(a, a)


def test_unblock_restores_ability_to_request(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.block(a, b)
    connections.unblock(a, b)
    conn = _raw(db_path)
    assert profiles.is_blocked(conn, a, b) is False
    conn.close()
    # A fresh request now succeeds (block did not auto-restore the old row).
    connections.send_request(a, b)
    assert _row_status(db_path, a, b)["status"] == "pending"


def test_unblock_is_idempotent(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    # No block present — must not raise.
    connections.unblock(a, b)


# ---------------------------------------------------------------------------
# relationship_state
# ---------------------------------------------------------------------------


def test_relationship_state_self(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    assert connections.relationship_state(a, a) == "self"


def test_relationship_state_none(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    assert connections.relationship_state(a, b) == "none"


def test_relationship_state_pending_outgoing_and_incoming(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    assert connections.relationship_state(a, b) == "pending_outgoing"
    assert connections.relationship_state(b, a) == "pending_incoming"


def test_relationship_state_fellow(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.accept(b, a)
    assert connections.relationship_state(a, b) == "fellow"
    assert connections.relationship_state(b, a) == "fellow"


def test_relationship_state_blocked_both_directions(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.block(a, b)
    assert connections.relationship_state(a, b) == "blocked"
    assert connections.relationship_state(b, a) == "blocked"


def test_relationship_state_declined_is_none(db_path: Path) -> None:
    a = _make_user(db_path, "alice")
    b = _make_user(db_path, "bob")
    connections.send_request(a, b)
    connections.decline(b, a)
    assert connections.relationship_state(a, b) == "none"


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


def test_throttle_blocks_past_cap(db_path: Path) -> None:
    requester = _make_user(db_path, "spammer")
    # Send up to the cap to distinct addressees.
    for i in range(connections.MAX_PENDING_REQUESTS_PER_DAY):
        target = _make_user(db_path, f"target{i}")
        connections.send_request(requester, target)
    # The next one trips the limit.
    over = _make_user(db_path, "overflow")
    with pytest.raises(connections.RateLimitedError):
        connections.send_request(requester, over)


def test_throttle_does_not_count_other_requesters(db_path: Path) -> None:
    """The cap is per-requester, not global."""
    busy = _make_user(db_path, "busy")
    for i in range(connections.MAX_PENDING_REQUESTS_PER_DAY):
        target = _make_user(db_path, f"t{i}")
        connections.send_request(busy, target)
    # A different requester is unaffected.
    fresh = _make_user(db_path, "fresh")
    other = _make_user(db_path, "other")
    cid = connections.send_request(fresh, other)
    assert isinstance(cid, int)


# ---------------------------------------------------------------------------
# Account deletion cascades the social-graph tables (social-graph Task 8)
# ---------------------------------------------------------------------------


def _count_refs(db_path: Path, table: str, columns: tuple[str, ...], uid: int) -> int:
    """Count rows in *table* that reference *uid* in any of *columns*."""
    conn = _raw(db_path)
    where = " OR ".join(f"{col} = ?" for col in columns)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE {where}",  # noqa: S608 - fixed col names
        tuple(uid for _ in columns),
    ).fetchone()
    conn.close()
    return int(row["n"])


def test_delete_user_cascades_connection_and_block_both_columns(db_path: Path) -> None:
    """Deleting a user removes every connection + block row referencing them in
    EITHER column (requester/addressee, blocker/blocked), while counterparts'
    own unrelated rows survive."""
    me = _make_user(db_path, "me")
    # Counterparts: one where I'm the requester, one where I'm the addressee,
    # one I block, one who blocks me.
    out_target = _make_user(db_path, "out_target")  # me -> them (requester)
    in_source = _make_user(db_path, "in_source")  # them -> me (addressee)
    i_blocked = _make_user(db_path, "i_blocked")  # me blocks them
    blocked_me = _make_user(db_path, "blocked_me")  # they block me

    # Bystanders with no relationship to me — their rows must survive. The
    # connection pair and the block pair are distinct (a block tears down a
    # connection for the same pair), so both rows coexist.
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")
    carol = _make_user(db_path, "carol")
    dave = _make_user(db_path, "dave")

    connections.send_request(me, out_target)  # connection: me is requester
    connections.send_request(in_source, me)  # connection: me is addressee
    connections.block(me, i_blocked)  # block: me is blocker
    connections.block(blocked_me, me)  # block: me is blocked

    # Unrelated rows that must NOT be touched by deleting me.
    connections.send_request(alice, bob)  # bystander connection
    connections.block(carol, dave)  # bystander block (distinct pair)

    # Sanity: I am referenced in both columns of both tables before deletion.
    assert _count_refs(db_path, "connection", ("requester_id", "addressee_id"), me) == 2
    assert _count_refs(db_path, "block", ("blocker_id", "blocked_id"), me) == 2

    removed = users.delete_user(me)
    assert removed is True

    # Zero connection/block rows reference me in either column.
    assert _count_refs(db_path, "connection", ("requester_id", "addressee_id"), me) == 0
    assert _count_refs(db_path, "connection", ("user_lo", "user_hi"), me) == 0
    assert _count_refs(db_path, "block", ("blocker_id", "blocked_id"), me) == 0

    # The bystanders' own unrelated rows survive intact.
    conn = _raw(db_path)
    surviving_conn = conn.execute(
        "SELECT COUNT(*) AS n FROM connection WHERE requester_id = ? AND addressee_id = ?",
        (alice, bob),
    ).fetchone()["n"]
    surviving_block = conn.execute(
        "SELECT COUNT(*) AS n FROM block WHERE blocker_id = ? AND blocked_id = ?",
        (carol, dave),
    ).fetchone()["n"]
    conn.close()
    assert surviving_conn == 1
    assert surviving_block == 1
