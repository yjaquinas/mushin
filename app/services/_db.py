"""Owner-scoped data-access helpers for the Mushin service layer.

Multi-user isolation is the project's non-negotiable invariant: **every** read
and write is scoped by ``owner_id``. The helpers here are designed so the
natural way to query already carries a ``WHERE owner_id = ?`` predicate — a
query that forgets it is impossible by construction, because ``owner_id`` is a
required positional argument and the helper injects the predicate itself.

These helpers are thin wrappers over the ``app.models.db`` connection context
manager. Raw, parameterized SQL only — no ORM, no string interpolation of
values. They operate on an *already-open* connection (the caller owns the
transaction boundary) so that cache maintenance can happen in the same
transaction as the entry write.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

# Tables in this layer that carry an ``owner_id`` column directly. The accessor
# refuses to scope-query anything not on this list, so a typo can't silently
# produce an unscoped query against the wrong table.
_OWNED_TABLES = frozenset(
    {
        "category",
        "sub_tally",
        "entry",
        "tag",
        "match",
        "level",
        "level_rule",
    }
)


class OwnerScopeError(ValueError):
    """Raised when a scoped query is attempted against an unknown/unowned table."""


def _assert_owned_table(table: str) -> None:
    if table not in _OWNED_TABLES:
        raise OwnerScopeError(
            f"{table!r} is not an owner-scoped table; "
            f"owner-scoped tables are {sorted(_OWNED_TABLES)}"
        )


def fetch_one(
    conn: sqlite3.Connection,
    table: str,
    owner_id: int,
    *,
    where: str = "",
    params: Iterable[Any] = (),
    columns: str = "*",
) -> sqlite3.Row | None:
    """Fetch a single row from *table*, always scoped to *owner_id*.

    ``owner_id`` is required and prepended to the WHERE clause; *where* holds any
    additional predicate (e.g. ``"id = ?"``) with its own *params*. There is no
    code path that omits the ``owner_id`` predicate.
    """
    _assert_owned_table(table)
    clause, all_params = _scoped_where(owner_id, where, params)
    sql = f"SELECT {columns} FROM {table} WHERE {clause}"  # noqa: S608 - table is allow-listed
    return conn.execute(sql, all_params).fetchone()


def fetch_all(
    conn: sqlite3.Connection,
    table: str,
    owner_id: int,
    *,
    where: str = "",
    params: Iterable[Any] = (),
    columns: str = "*",
    order_by: str = "",
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Fetch rows from *table*, always scoped to *owner_id*."""
    _assert_owned_table(table)
    clause, all_params = _scoped_where(owner_id, where, params)
    sql = f"SELECT {columns} FROM {table} WHERE {clause}"  # noqa: S608 - table is allow-listed
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += " LIMIT ?"
        all_params = (*all_params, limit)
    return conn.execute(sql, all_params).fetchall()


def exists(
    conn: sqlite3.Connection,
    table: str,
    owner_id: int,
    *,
    where: str = "",
    params: Iterable[Any] = (),
) -> bool:
    """Return whether at least one owner-scoped row matches."""
    row = fetch_one(conn, table, owner_id, where=where, params=params, columns="1")
    return row is not None


def update(
    conn: sqlite3.Connection,
    table: str,
    owner_id: int,
    *,
    assignments: str,
    assignment_params: Iterable[Any] = (),
    where: str = "",
    params: Iterable[Any] = (),
) -> int:
    """Run an owner-scoped UPDATE. Returns the affected row count.

    *assignments* is the ``SET`` body (e.g. ``"memo = ?, updated_at = ?"``); the
    ``owner_id`` predicate is always appended to the WHERE clause so a write can
    never escape the owner's partition.
    """
    _assert_owned_table(table)
    clause, where_params = _scoped_where(owner_id, where, params)
    sql = f"UPDATE {table} SET {assignments} WHERE {clause}"  # noqa: S608 - table is allow-listed
    cur = conn.execute(sql, (*tuple(assignment_params), *where_params))
    return cur.rowcount


def delete(
    conn: sqlite3.Connection,
    table: str,
    owner_id: int,
    *,
    where: str = "",
    params: Iterable[Any] = (),
) -> int:
    """Run an owner-scoped DELETE. Returns the affected row count."""
    _assert_owned_table(table)
    clause, all_params = _scoped_where(owner_id, where, params)
    sql = f"DELETE FROM {table} WHERE {clause}"  # noqa: S608 - table is allow-listed
    cur = conn.execute(sql, all_params)
    return cur.rowcount


def _scoped_where(owner_id: int, where: str, params: Iterable[Any]) -> tuple[str, tuple[Any, ...]]:
    """Build a WHERE clause that always begins with ``owner_id = ?``.

    Returns the clause text and the full parameter tuple in matching order.
    """
    clause = "owner_id = ?"
    all_params: tuple[Any, ...] = (owner_id, *tuple(params))
    if where:
        clause += f" AND ({where})"
    return clause, all_params
