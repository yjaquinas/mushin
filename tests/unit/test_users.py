"""Unit tests for the auth user repository (``app/auth/users.py``).

Covers the username-identity redesign (Task 2, auth-entry-flow):
``find_by_username``, ``create_username_user``, the repointed ``find_by_email``,
and ``attach_provider`` with the new ``username`` / ``email`` kwargs.

Each test gets a fresh tmp_path-scoped SQLite DB with all migrations applied,
and points ``app.models.db.DATABASE_PATH`` at it via monkeypatch so the repo's
``db.connect()`` hits the test database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app.models.db as db_module
from app.auth import users
from app.auth.users import IdentityTakenError
from app.models.migrate import run_migrations


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "test.db"
    run_migrations(path)
    import app.models.db as _db_module

    monkeypatch.setattr(_db_module, "DATABASE_PATH", str(path))
    return path


# ---------------------------------------------------------------------------
# find_by_username
# ---------------------------------------------------------------------------


def test_find_by_username_hit(db_path: Path) -> None:
    uid = users.create_username_user("alice", "hash$1")
    found = users.find_by_username("alice")
    assert found is not None
    assert found["id"] == uid
    assert found["username"] == "alice"
    assert found["auth_provider"] == "email"


def test_find_by_username_miss(db_path: Path) -> None:
    assert users.find_by_username("nobody") is None


# ---------------------------------------------------------------------------
# create_username_user
# ---------------------------------------------------------------------------


def test_create_username_user_success(db_path: Path) -> None:
    uid = users.create_username_user("bob", "hash$2", email="bob@example.com")
    row = users.get_user(uid)
    assert row is not None
    assert row["auth_provider"] == "email"
    assert row["username"] == "bob"
    assert row["password_hash"] == "hash$2"
    assert row["email"] == "bob@example.com"
    assert row["display_name"] == "bob"
    assert row["provider_id"] is None


def test_create_username_user_without_email(db_path: Path) -> None:
    uid = users.create_username_user("carol", "hash$3")
    row = users.get_user(uid)
    assert row is not None
    assert row["email"] is None


def test_create_username_user_duplicate_username_raises(db_path: Path) -> None:
    users.create_username_user("dave", "hash$4")
    with pytest.raises(IdentityTakenError):
        users.create_username_user("dave", "hash$5")


def test_create_username_user_duplicate_email_raises(db_path: Path) -> None:
    users.create_username_user("erin", "hash$6", email="dup@example.com")
    with pytest.raises(IdentityTakenError):
        users.create_username_user("frank", "hash$7", email="dup@example.com")


# ---------------------------------------------------------------------------
# find_by_email (recovery-email uniqueness check, not login)
# ---------------------------------------------------------------------------


def test_find_by_email_queries_email_column(db_path: Path) -> None:
    uid = users.create_username_user("grace", "hash$8", email="grace@example.com")
    found = users.find_by_email("grace@example.com")
    assert found is not None
    assert found["id"] == uid


def test_find_by_email_miss(db_path: Path) -> None:
    # username matching an email-shaped value must not be found by find_by_email
    users.create_username_user("heidi", "hash$9")
    assert users.find_by_email("heidi") is None


# ---------------------------------------------------------------------------
# attach_provider (email upgrade-in-place)
# ---------------------------------------------------------------------------


def test_attach_provider_email_success(db_path: Path) -> None:
    guest_id = users.create_guest()
    row = users.attach_provider(
        guest_id,
        "email",
        password_hash="hash$10",
        username="ivan",
        email="ivan@example.com",
    )
    assert row["id"] == guest_id  # upgrade-in-place: same row
    assert row["auth_provider"] == "email"
    assert row["username"] == "ivan"
    assert row["email"] == "ivan@example.com"
    assert row["display_name"] == "ivan"
    assert row["password_hash"] == "hash$10"


def test_attach_provider_email_duplicate_username_raises(db_path: Path) -> None:
    users.create_username_user("judy", "hash$11")
    guest_id = users.create_guest()
    with pytest.raises(IdentityTakenError):
        users.attach_provider(
            guest_id,
            "email",
            password_hash="hash$12",
            username="judy",
        )


def test_attach_provider_email_duplicate_email_raises(db_path: Path) -> None:
    users.create_username_user("ken", "hash$13", email="clash@example.com")
    guest_id = users.create_guest()
    with pytest.raises(IdentityTakenError):
        users.attach_provider(
            guest_id,
            "email",
            password_hash="hash$14",
            username="leo",
            email="clash@example.com",
        )


def test_attach_provider_oauth_unchanged(db_path: Path) -> None:
    guest_id = users.create_guest()
    row = users.attach_provider(
        guest_id,
        "google",
        provider_id="google-123",
        display_name="Google User",
    )
    assert row["id"] == guest_id
    assert row["auth_provider"] == "google"
    assert row["provider_id"] == "google-123"
    assert row["display_name"] == "Google User"
    assert row["username"] is None


# ---------------------------------------------------------------------------
# Timezone validation + storage at creation
# ---------------------------------------------------------------------------


def test_normalize_timezone_valid() -> None:
    assert users._normalize_timezone("America/New_York") == "America/New_York"


def test_normalize_timezone_strips_whitespace() -> None:
    assert users._normalize_timezone("  Europe/London  ") == "Europe/London"


@pytest.mark.parametrize(
    "bad",
    [None, "", "   ", "Not/AZone", "Mars/Olympus_Mons", "'; DROP TABLE user; --", "utc"],
)
def test_normalize_timezone_falls_back_to_utc(bad: str | None) -> None:
    # Missing/blank/garbage (and the wrong-case "utc") all fall back to UTC and
    # never raise.
    assert users._normalize_timezone(bad) == "UTC"


def test_create_guest_stores_valid_timezone(db_path: Path) -> None:
    uid = users.create_guest(timezone="America/Los_Angeles")
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "America/Los_Angeles"


def test_create_guest_defaults_to_utc_when_absent(db_path: Path) -> None:
    uid = users.create_guest()
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "UTC"


def test_create_guest_garbage_timezone_falls_back_to_utc(db_path: Path) -> None:
    uid = users.create_guest(timezone="Totally/Bogus")
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "UTC"


def test_create_username_user_stores_timezone(db_path: Path) -> None:
    uid = users.create_username_user("tzuser", "hash$tz", timezone="Asia/Tokyo")
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "Asia/Tokyo"


def test_create_username_user_defaults_timezone_to_utc(db_path: Path) -> None:
    uid = users.create_username_user("tzuser2", "hash$tz2")
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "UTC"


def test_create_oauth_user_stores_timezone(db_path: Path) -> None:
    uid = users.create_oauth_user(
        "google", "g-tz-1", "TZ User", timezone="Europe/Paris"
    )
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "Europe/Paris"


def test_create_oauth_user_garbage_timezone_falls_back_to_utc(db_path: Path) -> None:
    uid = users.create_oauth_user("google", "g-tz-2", "TZ User", timezone="???")
    row = users.get_user(uid)
    assert row is not None
    assert row["timezone"] == "UTC"


# ---------------------------------------------------------------------------
# get_user_timezone
# ---------------------------------------------------------------------------


def test_get_user_timezone_returns_zoneinfo(db_path: Path) -> None:
    uid = users.create_guest(timezone="America/Chicago")
    tz = users.get_user_timezone(uid)
    assert isinstance(tz, ZoneInfo)
    assert tz == ZoneInfo("America/Chicago")


def test_get_user_timezone_missing_user_falls_back_to_utc(db_path: Path) -> None:
    tz = users.get_user_timezone(999999)
    assert tz == ZoneInfo("UTC")


def test_get_user_timezone_invalid_stored_value_falls_back_to_utc(db_path: Path) -> None:
    # Force an unloadable timezone into the row, bypassing the creation-time
    # validation, to prove get_user_timezone never raises on bad stored data.
    uid = users.create_guest()
    conn = sqlite3.connect(db_module.DATABASE_PATH, isolation_level=None)
    try:
        conn.execute("UPDATE user SET timezone = 'Bogus/Zone' WHERE id = ?", (uid,))
    finally:
        conn.close()

    tz = users.get_user_timezone(uid)
    assert tz == ZoneInfo("UTC")
