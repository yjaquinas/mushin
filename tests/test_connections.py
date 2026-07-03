from pathlib import Path

from app.models import db
from app.services import connections


def _init_connections_db(path: Path) -> None:
    with db.connect_to(path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                suspended_at TEXT NULL,
                deleted_at TEXT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE connection (
                id INTEGER PRIMARY KEY,
                user_lo INTEGER NOT NULL,
                user_hi INTEGER NOT NULL,
                status TEXT NOT NULL,
                sharing_consent_at TEXT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO user (id, username, suspended_at, deleted_at) VALUES (1, 'alice', NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO user (id, username, suspended_at, deleted_at) VALUES (2, 'bravo', NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO user (id, username, suspended_at, deleted_at) VALUES (3, 'charlie', NULL, '2026-07-03T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO connection (user_lo, user_hi, status, sharing_consent_at) VALUES (1, 2, 'accepted', '2026-07-03T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO connection (user_lo, user_hi, status, sharing_consent_at) VALUES (1, 3, 'accepted', '2026-07-03T00:00:00+00:00')"
        )


def test_list_fellows_excludes_deleted_users(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "connections.db"
    _init_connections_db(db_path)
    monkeypatch.setattr(connections.db, "connect", lambda: db.connect_to(db_path))

    fellows = connections.list_fellows(1)

    assert fellows == [{"id": 2, "username": "bravo"}]
