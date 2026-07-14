"""Plan configuration queries and limit enforcement for the Mushin service layer.

Renderer-agnostic: no HTTP, no templates. Every function takes an open DB
connection (the caller owns the transaction boundary) and a required
``owner_id`` for multi-user isolation.

Plan config is stored in the ``plan_config`` table and editable via the admin
dashboard. Limits are checked before writes in the service layer and raise
custom exceptions that route handlers translate to user-facing responses.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import db


class PlanLimitError(Exception):
    """Base exception for plan-related limit enforcement."""


class ActivityLimitError(PlanLimitError):
    """Raised when the user has reached their plan's max activities."""


class EntryDateLimitError(PlanLimitError):
    """Raised when the user has reached their plan's max entries per date."""


class SecretActivityForbiddenError(PlanLimitError):
    """Raised when the user's plan does not allow secret activities."""


def _plan_config_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "plan": row["plan"],
        "name": row["name"],
        "max_activities": row["max_activities"],
        "max_entries_per_date": row["max_entries_per_date"],
        "secret_activities": bool(row["secret_activities"]),
        "price_monthly": row["price_monthly"],
        "price_yearly": row["price_yearly"],
    }


def get_plan_config(conn: sqlite3.Connection, plan: str) -> dict[str, Any] | None:
    """Fetch a single plan config by *plan* identifier, or ``None``."""
    row = conn.execute(
        "SELECT * FROM plan_config WHERE plan = ?", (plan,)
    ).fetchone()
    return _plan_config_row(row)


def get_all_plan_configs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch every plan config ordered by plan name."""
    rows = conn.execute(
        "SELECT * FROM plan_config ORDER BY plan"
    ).fetchall()
    return [_plan_config_row(r) for r in rows]


def get_user_plan(conn: sqlite3.Connection, owner_id: int) -> str:
    """Return the plan identifier for *owner_id* (defaults to ``"basic"``)."""
    row = conn.execute(
        "SELECT plan FROM user WHERE id = ?", (owner_id,)
    ).fetchone()
    return row["plan"] if row else "basic"


def get_user_plan_config(conn: sqlite3.Connection, owner_id: int) -> dict[str, Any] | None:
    """Return the full plan config for *owner_id*."""
    plan = get_user_plan(conn, owner_id)
    return get_plan_config(conn, plan)


def set_user_plan(conn: sqlite3.Connection, owner_id: int, plan: str) -> bool:
    """Set a user's plan. Returns ``True`` if the plan exists in config."""
    existing = conn.execute(
        "SELECT 1 FROM plan_config WHERE plan = ?", (plan,)
    ).fetchone()
    if existing is None:
        return False
    conn.execute("UPDATE user SET plan = ? WHERE id = ?", (plan, owner_id))
    return True


def update_plan_config(
    conn: sqlite3.Connection,
    plan: str,
    *,
    name: str | None = None,
    max_activities: int | None = None,
    max_entries_per_date: int | None = None,
    secret_activities: bool | None = None,
    price_monthly: int | None = None,
    price_yearly: int | None = None,
) -> None:
    """Update a plan config's editable fields."""
    assignments: list[str] = []
    params: list[Any] = []
    if name is not None:
        assignments.append("name = ?")
        params.append(name)
    if max_activities is not None:
        assignments.append("max_activities = ?")
        params.append(max_activities)
    if max_entries_per_date is not None:
        assignments.append("max_entries_per_date = ?")
        params.append(max_entries_per_date)
    if secret_activities is not None:
        assignments.append("secret_activities = ?")
        params.append(int(secret_activities))
    if price_monthly is not None:
        assignments.append("price_monthly = ?")
        params.append(price_monthly)
    if price_yearly is not None:
        assignments.append("price_yearly = ?")
        params.append(price_yearly)

    if not assignments:
        return
    assignments.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    params.append(plan)
    conn.execute(
        f"UPDATE plan_config SET {', '.join(assignments)} WHERE plan = ?",
        params,
    )


def get_user_payments(
    conn: sqlite3.Connection, owner_id: int
) -> list[sqlite3.Row]:
    """Return payment records for *owner_id* ordered newest first."""
    return conn.execute(
        """SELECT id, plan, amount_cents, currency, status,
                  payment_method, payment_provider_id,
                  period_start, period_end, created_at
           FROM payment
           WHERE user_id = ?
           ORDER BY created_at DESC""",
        (owner_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Limit checkers (raise on violation)
# ---------------------------------------------------------------------------


def check_activity_limit(conn: sqlite3.Connection, owner_id: int) -> None:
    """Raise ``ActivityLimitError`` if *owner_id* has reached their limit."""
    cfg = get_user_plan_config(conn, owner_id)
    if cfg is None:
        return
    max_activities = cfg["max_activities"]
    count = conn.execute(
        "SELECT COUNT(*) FROM activity"
        " WHERE owner_id = ? AND archived_at IS NULL",
        (owner_id,),
    ).fetchone()[0]
    if count >= max_activities:
        raise ActivityLimitError(
            f"Plan limit reached: {max_activities} activities"
        )


def check_secret_activity_allowed(conn: sqlite3.Connection, owner_id: int) -> None:
    """Raise ``SecretActivityForbiddenError`` if *owner_id*'s plan forbids secrets."""
    cfg = get_user_plan_config(conn, owner_id)
    if cfg is None or not cfg["secret_activities"]:
        raise SecretActivityForbiddenError(
            "Your plan does not support secret activities"
        )


def check_entry_date_limit(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_id: int,
    occurred_at: str,
    tz: ZoneInfo,
) -> None:
    """Raise ``EntryDateLimitError`` if *owner_id* has reached their per-date limit.

    Uses the same ``_local_day()`` function as the rest of the entry system
    for consistent date bucketing.
    """
    cfg = get_user_plan_config(conn, owner_id)
    if cfg is None:
        return
    max_per_date = cfg["max_entries_per_date"]
    from app.services.entries.entries import _local_day
    day: date = _local_day(occurred_at, tz)
    end = day + timedelta(days=1)
    count = conn.execute(
        "SELECT COUNT(*) FROM entry"
        " WHERE owner_id = ? AND activity_id = ?"
        " AND occurred_at >= ? AND occurred_at < ?",
        (owner_id, activity_id, day.isoformat(), end.isoformat()),
    ).fetchone()[0]
    if count >= max_per_date:
        raise EntryDateLimitError(
            f"Plan limit reached: {max_per_date} entries per date"
        )
