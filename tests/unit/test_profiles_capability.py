"""Unit-test matrix for the single visibility authority (social-graph Task 2).

This is THE security boundary for the fellows feature. The matrix covers every
viewer-state x profile-visibility cell and asserts the fail-closed precedence in
``profiles.viewer_capability``:

    owner > blocked > connected > public > limited

Key invariants proved here:
- ``sharing_consent_at`` gates ``connected``: accepted-WITHOUT-consent is NOT a
  fellow (falls through to public/limited per the profile's visibility).
- ``is_blocked`` is symmetric: a block in EITHER direction yields ``"blocked"``,
  even when the profile is public (no existence oracle).
- pending/declined connections never reach ``connected``.
- anonymous viewers fall through to public/limited, never owner/blocked/connected.

Each test uses its own fresh migrated SQLite in ``tmp_path``. State for the
``connection``/``block`` tables is inserted directly (the connection service is
a separate task) — the canonical ``(user_lo, user_hi)`` pair is computed here
the same way the service will: ``(MIN(a,b), MAX(a,b))``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.migrate import run_migrations
from app.services import profiles

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _raw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _make_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    visibility: str = "private",
    auth_provider: str = "email",
) -> int:
    cur = conn.execute(
        "INSERT INTO user (auth_provider, username, visibility) VALUES (?, ?, ?)",
        (auth_provider, username, visibility),
    )
    conn.commit()
    return cur.lastrowid


def _profile_dict(uid: int, visibility: str) -> dict:
    """Minimal profile_user dict as get_public_user would return."""
    return {"id": uid, "visibility": visibility}


def _make_connection(
    conn: sqlite3.Connection,
    requester_id: int,
    addressee_id: int,
    *,
    status: str,
    consented: bool,
) -> None:
    lo, hi = (
        (requester_id, addressee_id)
        if requester_id < addressee_id
        else (addressee_id, requester_id)
    )
    conn.execute(
        "INSERT INTO connection"
        " (requester_id, addressee_id, status, user_lo, user_hi, sharing_consent_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            requester_id,
            addressee_id,
            status,
            lo,
            hi,
            "2026-01-01T00:00:00Z" if consented else None,
        ),
    )
    conn.commit()


def _make_block(conn: sqlite3.Connection, blocker_id: int, blocked_id: int) -> None:
    conn.execute(
        "INSERT INTO block (blocker_id, blocked_id) VALUES (?, ?)",
        (blocker_id, blocked_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# is_connected — requires accepted AND consent
# ---------------------------------------------------------------------------


def test_is_connected_accepted_with_consent(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    _make_connection(conn, a, b, status="accepted", consented=True)
    assert profiles.is_connected(conn, a, b) is True
    # Directionless — argument order must not matter.
    assert profiles.is_connected(conn, b, a) is True
    conn.close()


def test_is_connected_accepted_without_consent_is_false(tmp_path: Path):
    """The sharing_consent_at gate: accepted alone is NOT a fellow."""
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    _make_connection(conn, a, b, status="accepted", consented=False)
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_is_connected_pending_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    # Even an accidentally-consented pending row is not a connection.
    _make_connection(conn, a, b, status="pending", consented=True)
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_is_connected_declined_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    _make_connection(conn, a, b, status="declined", consented=True)
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


def test_is_connected_no_row_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    assert profiles.is_connected(conn, a, b) is False
    conn.close()


# ---------------------------------------------------------------------------
# is_blocked — symmetric (either direction)
# ---------------------------------------------------------------------------


def test_is_blocked_forward_direction(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    _make_block(conn, a, b)  # a blocks b
    assert profiles.is_blocked(conn, a, b) is True
    conn.close()


def test_is_blocked_is_symmetric(tmp_path: Path):
    """A block in one direction is seen from both directions."""
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    _make_block(conn, a, b)  # a blocks b
    # b querying against a must also report blocked (no existence oracle).
    assert profiles.is_blocked(conn, b, a) is True
    conn.close()


def test_is_blocked_no_row_is_false(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    a = _make_user(conn, username="a")
    b = _make_user(conn, username="b")
    assert profiles.is_blocked(conn, a, b) is False
    assert profiles.is_blocked(conn, b, a) is False
    conn.close()


# ---------------------------------------------------------------------------
# viewer_capability — the full matrix
# ---------------------------------------------------------------------------


def test_owner_sees_owner_on_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="me", visibility="public")
    cap = profiles.viewer_capability(
        conn, current_user_id=uid, profile_user=_profile_dict(uid, "public")
    )
    conn.close()
    assert cap == "owner"


def test_owner_sees_owner_on_private(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="me", visibility="private")
    cap = profiles.viewer_capability(
        conn, current_user_id=uid, profile_user=_profile_dict(uid, "private")
    )
    conn.close()
    assert cap == "owner"


def test_anonymous_on_public_is_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="p", visibility="public")
    cap = profiles.viewer_capability(
        conn, current_user_id=None, profile_user=_profile_dict(uid, "public")
    )
    conn.close()
    assert cap == "public"


def test_anonymous_on_private_is_limited(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="p", visibility="private")
    cap = profiles.viewer_capability(
        conn, current_user_id=None, profile_user=_profile_dict(uid, "private")
    )
    conn.close()
    assert cap == "limited"


def test_connected_with_consent_is_connected_on_private(tmp_path: Path):
    """Accepted + consent grants 'connected' even when the profile is private."""
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="accepted", consented=True)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert cap == "connected"


def test_connected_with_consent_is_connected_on_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    _make_connection(conn, viewer, owner, status="accepted", consented=True)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "public")
    )
    conn.close()
    assert cap == "connected"


def test_accepted_without_consent_falls_to_limited_on_private(tmp_path: Path):
    """Proves the sharing_consent_at gate at the capability level."""
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="accepted", consented=False)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert cap == "limited"


def test_accepted_without_consent_falls_to_public_on_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    _make_connection(conn, viewer, owner, status="accepted", consented=False)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "public")
    )
    conn.close()
    assert cap == "public"


def test_pending_connection_falls_to_limited_on_private(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="pending", consented=False)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert cap == "limited"


def test_declined_connection_falls_to_limited_on_private(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="declined", consented=False)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert cap == "limited"


def test_blocker_sees_blocked_even_on_public(tmp_path: Path):
    """A block overrides public visibility (no existence oracle)."""
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    _make_block(conn, viewer, owner)  # viewer blocked owner
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "public")
    )
    conn.close()
    assert cap == "blocked"


def test_blocked_by_sees_blocked_even_on_public(tmp_path: Path):
    """The other direction: owner blocked viewer; viewer still gets 'blocked'."""
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    _make_block(conn, owner, viewer)  # owner blocked viewer
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "public")
    )
    conn.close()
    assert cap == "blocked"


def test_block_overrides_connection(tmp_path: Path):
    """Precedence: blocked is evaluated before connected."""
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="accepted", consented=True)
    _make_block(conn, owner, viewer)
    cap = profiles.viewer_capability(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert cap == "blocked"


# ---------------------------------------------------------------------------
# can_view_activity_detail — True only for owner/connected/public
# ---------------------------------------------------------------------------


def test_detail_true_for_owner(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="me", visibility="private")
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=uid, profile_user=_profile_dict(uid, "private")
    )
    conn.close()
    assert ok is True


def test_detail_true_for_connected(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="accepted", consented=True)
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert ok is True


def test_detail_true_for_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="p", visibility="public")
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=None, profile_user=_profile_dict(uid, "public")
    )
    conn.close()
    assert ok is True


def test_detail_false_for_limited(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    uid = _make_user(conn, username="p", visibility="private")
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=None, profile_user=_profile_dict(uid, "private")
    )
    conn.close()
    assert ok is False


def test_detail_false_for_accepted_without_consent(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="private")
    _make_connection(conn, viewer, owner, status="accepted", consented=False)
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "private")
    )
    conn.close()
    assert ok is False


def test_detail_false_for_blocked_even_on_public(tmp_path: Path):
    conn = _raw(_make_db(tmp_path))
    viewer = _make_user(conn, username="v")
    owner = _make_user(conn, username="o", visibility="public")
    _make_block(conn, owner, viewer)
    ok = profiles.can_view_activity_detail(
        conn, current_user_id=viewer, profile_user=_profile_dict(owner, "public")
    )
    conn.close()
    assert ok is False
