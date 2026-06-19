"""Data-portability export/import for Mushin ("carry over your data").

This module assembles a versioned, JSON-serializable snapshot of everything a
single ``owner_id`` owns, so a renderer (the web route, later HXML) can offer it
as a downloadable file (``export_data``), and accepts that same snapshot back to
**replace** an account's contents (``import_data`` — the guest→real-account and
account→account "carry over" flow).

Public API
----------
``export_data(owner_id: int) -> dict``
    Return the full snapshot for *owner_id* (see "Output shape" below). This
    signature is final — renderers wire a route directly onto it.

``import_data(owner_id: int, payload: dict) -> dict``
    Validate *payload* (the same shape ``export_data`` produces) fully, then —
    in one transaction — wipe *owner_id*'s existing data and re-insert the
    payload's rows with freshly-assigned primary keys and remapped foreign
    keys. Returns a per-table count summary. ``owner_id`` is taken from the
    authenticated caller only — never from the payload (the export shape has no
    ``owner_id`` field). Raises :class:`ImportValidationError` (a ``ValueError``
    subclass) on any validation failure, *before* any write; the route maps it
    to a 4xx. Validation messages carry table names and counts but **never** row
    content (memos are PIPA-scoped personal data and must not land in errors or
    logs).

Output shape
------------
::

    {
        "schema_version": 1,
        "exported_at": "<ISO 8601 UTC timestamp, e.g. 2026-06-12T09:30:00Z>",
        "data": {
            "categories": [...],
            "sub_tallies": [...],
            "field_defs": [...],
            "tags": [...],
            "entries": [...],
            "entry_tags": [...],
            "entry_values": [...],
            "matches": [...],
            "levels": [...],
            "level_rules": [...],
        },
        "social_graph": {
            "fellows": [
                {"username": ..., "display_name": ..., "connected_at": ...,
                 "responded_at": ...},
            ],
            "pending_requests": [
                {"direction": "incoming"|"outgoing", "username": ...,
                 "display_name": ..., "created_at": ...},
            ],
            "blocked": [
                {"username": ...},
            ],
        },
    }

Each value in ``data`` is a list of plain dicts (one per row). Cross-references
keep the *original* primary keys straight from the DB — export does not
renumber anything; import remaps later.

``social_graph`` is a separate top-level section, deliberately **outside**
``data``: ``data`` is the strict, key-exact import payload, and the social graph
is honest self-owned relationship metadata (the access right covers "who I am
connected to"), not importable account content. Each entry names only the
*counterpart's* public handle (``username``) and ``display_name`` plus the
relationship's own timestamps — never any of the counterpart's private content
(entries, memos, levels, block internals). ``import_data`` ignores
``social_graph`` entirely; re-establishing connections requires fresh consent
from both parties, so they are not re-created on import.

What is deliberately excluded
-----------------------------
- ``owner_id`` on every row. The whole export belongs to one owner, so it is
  implicit; re-emitting it would leak the internal user id and invite
  cross-tenant confusion on import.
- Everything in the ``user`` table — ``auth_provider``, ``provider_id``,
  ``password_hash``, ``display_name``, session/device tokens. Auth-plane
  secrets are not "user content" and never belong in a downloadable file.
- Derived/cached columns on ``activity`` (``cached_count``, ``cached_streak``,
  ``last_entry_at``). These are rebuilt from truth on import via ``recompute``.

PIPA note: ``entry.memo`` is personal data and **is** included — the export is
how a user exercises their access right, so memos must be present.

Isolation: every query is scoped to *owner_id*. Child tables that carry no
``owner_id`` column of their own (``field_def``, ``entry_tag``, ``entry_value``,
``match``) are reached only through their owner-scoped parent, so a row from
another account can never appear in the snapshot.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.models import db
from app.models.db import connect
from app.services import entries

SCHEMA_VERSION = 1

# Columns to emit per table, in declaration order. ``owner_id`` and the derived
# cache columns are intentionally absent — see the module docstring.
_CATEGORY_COLUMNS = ("id", "name", "color", "icon", "sort_order", "archived_at", "created_at")
_SUB_TALLY_COLUMNS = (
    "id",
    "category_id",
    "name",
    "count_mode",
    "config_json",
    "sort_order",
    "archived_at",
    "created_at",
)
_FIELD_DEF_COLUMNS = ("id", "activity_id", "kind", "label", "config_json", "sort_order")
_TAG_COLUMNS = ("id", "field_def_id", "name", "sort_order", "archived_at", "created_at")
_ENTRY_COLUMNS = ("id", "activity_id", "occurred_at", "memo", "created_at", "updated_at")
_ENTRY_TAG_COLUMNS = ("entry_id", "tag_id")
_ENTRY_VALUE_COLUMNS = ("entry_id", "field_def_id", "num_value", "text_value")
_MATCH_COLUMNS = ("id", "entry_id", "opponent", "score", "result", "sort_order")
_LEVEL_COLUMNS = ("id", "activity_id", "track", "ordinal", "code", "label", "archived_at")
_LEVEL_RULE_COLUMNS = (
    "id",
    "activity_id",
    "from_level_id",
    "to_level_id",
    "gate_type",
    "gate_value",
    "min_age",
    "prereq_level_id",
)


def export_data(owner_id: int) -> dict[str, Any]:
    """Assemble the full portable snapshot for *owner_id*.

    Returns a versioned, JSON-serializable dict (see the module docstring for the
    exact shape). All ten owned tables are exported; tables with no rows for this
    owner come back as empty lists. ``owner_id``, ``user``-table fields, and the
    derived cache columns are excluded.

    The export also carries a ``social_graph`` section (accepted fellows,
    pending requests both directions, and blocked usernames) — the user's own
    relationship rows, with only the counterpart's public handle/display name
    and the relationship timestamps, never any counterpart private content.

    *owner_id* is required — there is no path that produces an unscoped export.
    """
    with connect() as conn:
        # A single read transaction gives every table a consistent snapshot and
        # gives the connection context manager a transaction to COMMIT on exit.
        conn.execute("BEGIN")
        # Parent tables: directly owner-scoped.
        categories = _select(conn, "category", _CATEGORY_COLUMNS, "owner_id = ?", (owner_id,))
        sub_tallies = _select(conn, "activity", _SUB_TALLY_COLUMNS, "owner_id = ?", (owner_id,))
        tags = _select(conn, "tag", _TAG_COLUMNS, "owner_id = ?", (owner_id,))
        entries = _select(conn, "entry", _ENTRY_COLUMNS, "owner_id = ?", (owner_id,))
        levels = _select(conn, "level", _LEVEL_COLUMNS, "owner_id = ?", (owner_id,))
        level_rules = _select(conn, "level_rule", _LEVEL_RULE_COLUMNS, "owner_id = ?", (owner_id,))
        matches = _select(conn, "match", _MATCH_COLUMNS, "owner_id = ?", (owner_id,))

        # Child tables with no owner_id of their own: reach them through an
        # owner-scoped parent so isolation holds without an owner_id column.
        field_defs = _select(
            conn,
            "field_def",
            _FIELD_DEF_COLUMNS,
            "activity_id IN (SELECT id FROM activity WHERE owner_id = ?)",
            (owner_id,),
        )
        entry_tags = _select(
            conn,
            "entry_tag",
            _ENTRY_TAG_COLUMNS,
            "entry_id IN (SELECT id FROM entry WHERE owner_id = ?)",
            (owner_id,),
        )
        entry_values = _select(
            conn,
            "entry_value",
            _ENTRY_VALUE_COLUMNS,
            "entry_id IN (SELECT id FROM entry WHERE owner_id = ?)",
            (owner_id,),
        )

        social_graph = _export_social_graph(conn, owner_id)

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _now_iso_utc(),
        "data": {
            "categories": categories,
            "sub_tallies": sub_tallies,
            "field_defs": field_defs,
            "tags": tags,
            "entries": entries,
            "entry_tags": entry_tags,
            "entry_values": entry_values,
            "matches": matches,
            "levels": levels,
            "level_rules": level_rules,
        },
        "social_graph": social_graph,
    }


def _export_social_graph(conn: sqlite3.Connection, owner_id: int) -> dict[str, Any]:
    """Assemble *owner_id*'s self-owned social-graph relationships.

    All three lists name only the *counterpart's* public handle (``username``)
    and ``display_name`` plus the relationship's own timestamps — never any of
    the counterpart's private content. Every query is scoped to rows
    *owner_id* is a party to, so no other account's relationships leak.

    * ``fellows`` — accepted + consented connections (the same bar as
      ``profiles.is_connected`` and ``connections.list_fellows``), carrying
      ``connected_at`` (the connection's ``created_at``) and ``responded_at``.
    * ``pending_requests`` — pending rows in both directions, each tagged with
      ``direction`` (``incoming`` = addressed to the user, ``outgoing`` = sent
      by the user) and the row's ``created_at``.
    * ``blocked`` — usernames *owner_id* has blocked (the directed blocks they
      own). Honest disclosure of the user's own list, with no block internals
      beyond the counterpart's handle.
    """
    fellow_rows = conn.execute(
        "SELECT u.username, u.display_name, c.created_at, c.responded_at"
        " FROM connection c JOIN user u ON u.id = CASE WHEN c.user_lo = ?"
        " THEN c.user_hi ELSE c.user_lo END"
        " WHERE (c.user_lo = ? OR c.user_hi = ?)"
        " AND c.status = 'accepted' AND c.sharing_consent_at IS NOT NULL"
        " ORDER BY u.username",
        (owner_id, owner_id, owner_id),
    ).fetchall()
    fellows = [
        {
            "username": r["username"],
            "display_name": r["display_name"],
            "connected_at": r["created_at"],
            "responded_at": r["responded_at"],
        }
        for r in fellow_rows
    ]

    incoming_rows = conn.execute(
        "SELECT u.username, u.display_name, c.created_at"
        " FROM connection c JOIN user u ON u.id = c.requester_id"
        " WHERE c.addressee_id = ? AND c.status = 'pending'"
        " ORDER BY u.username",
        (owner_id,),
    ).fetchall()
    outgoing_rows = conn.execute(
        "SELECT u.username, u.display_name, c.created_at"
        " FROM connection c JOIN user u ON u.id = c.addressee_id"
        " WHERE c.requester_id = ? AND c.status = 'pending'"
        " ORDER BY u.username",
        (owner_id,),
    ).fetchall()
    pending_requests = [
        {
            "direction": "incoming",
            "username": r["username"],
            "display_name": r["display_name"],
            "created_at": r["created_at"],
        }
        for r in incoming_rows
    ] + [
        {
            "direction": "outgoing",
            "username": r["username"],
            "display_name": r["display_name"],
            "created_at": r["created_at"],
        }
        for r in outgoing_rows
    ]

    blocked_rows = conn.execute(
        "SELECT u.username FROM block b JOIN user u ON u.id = b.blocked_id"
        " WHERE b.blocker_id = ? ORDER BY u.username",
        (owner_id,),
    ).fetchall()
    blocked = [{"username": r["username"]} for r in blocked_rows]

    return {
        "fellows": fellows,
        "pending_requests": pending_requests,
        "blocked": blocked,
    }


def _select(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    where: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    """Select an explicit, allow-listed column set from *table*, scoped by *where*.

    Only the columns we intend to export are projected, so excluded columns
    (``owner_id``, cache fields, ``user`` secrets) can never leak by selecting
    ``*``. *table* and *columns* are module constants, never caller input.
    """
    col_sql = ", ".join(columns)
    sql = f"SELECT {col_sql} FROM {table} WHERE {where} ORDER BY id"  # noqa: S608
    if "id" not in columns:
        # entry_tag / entry_value have composite PKs and no single id column.
        sql = f"SELECT {col_sql} FROM {table} WHERE {where}"  # noqa: S608
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _now_iso_utc() -> str:
    """Current UTC time as an ISO 8601 string with a trailing ``Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# Import ("carry over your data") — the replace half.
# ===========================================================================

#: Per-table row ceiling. A personal activity log is small; this is a sanity
#: bound to reject hostile/oversized files before any DB work, not a real-world
#: limit a genuine user would ever approach.
MAX_ROWS_PER_TABLE = 2000

#: Free-text length caps, consistent with what the live forms realistically
#: accept. Names/labels/codes are short; memos and free-text values are roomier.
MAX_NAME_LEN = 100
MAX_TEXT_LEN = 500

# The ten data tables, in the order ``export_data`` emits them. Used to assert
# the payload's ``data`` dict has exactly the expected keys.
_DATA_TABLES = (
    "categories",
    "sub_tallies",
    "field_defs",
    "tags",
    "entries",
    "entry_tags",
    "entry_values",
    "matches",
    "levels",
    "level_rules",
)

# Enum allow-lists, mirroring the CHECK constraints in 0001_initial.sql.
_COUNT_MODES = frozenset({"running", "progression"})
_MATCH_RESULTS = frozenset({"win", "loss", "draw"})
_FIELD_KINDS = frozenset({"tag_group", "scale", "count", "memo", "match_list", "level", "result"})
_GATE_TYPES = frozenset({"time", "count", "event", "manual"})


class ImportValidationError(ValueError):
    """Raised when an import payload fails validation, before any DB write.

    The message identifies the offending table (and counts where useful) but
    never echoes row content — memos and other free text are PIPA-scoped and
    must not leak into error strings or logs. The route maps this to a 4xx with
    a user-facing message.
    """


# --- column specs ----------------------------------------------------------
# For each table: the exact set of allowed keys (must match the export
# allow-list), the integer columns, the nullable-int columns (FK refs that may
# be None), the float columns, the text columns that are NOT NULL, and the
# nullable text columns. These drive per-row shape + type validation. Length
# caps for specific free-text columns are applied separately.

_INT = "int"  # required integer
_NULL_INT = "null_int"  # integer or None
_FLOAT = "null_float"  # float or None (all REAL columns in scope are nullable)
_TEXT = "text"  # required (NOT NULL) string
_NULL_TEXT = "null_text"  # string or None


# (column -> type-tag). Order is irrelevant for validation; the export tuples
# above remain the authority for *which* columns exist.
_TABLE_SPECS: dict[str, dict[str, str]] = {
    "categories": {
        "id": _INT,
        "name": _TEXT,
        "color": _NULL_TEXT,
        "icon": _NULL_TEXT,
        "sort_order": _INT,
        "archived_at": _NULL_TEXT,
        "created_at": _TEXT,
    },
    "sub_tallies": {
        "id": _INT,
        "category_id": _INT,
        "name": _TEXT,
        "count_mode": _TEXT,
        "config_json": _NULL_TEXT,
        "sort_order": _INT,
        "archived_at": _NULL_TEXT,
        "created_at": _TEXT,
    },
    "field_defs": {
        "id": _INT,
        "activity_id": _INT,
        "kind": _TEXT,
        "label": _TEXT,
        "config_json": _NULL_TEXT,
        "sort_order": _INT,
    },
    "tags": {
        "id": _INT,
        "field_def_id": _INT,
        "name": _TEXT,
        "sort_order": _INT,
        "archived_at": _NULL_TEXT,
        "created_at": _TEXT,
    },
    "entries": {
        "id": _INT,
        "activity_id": _INT,
        "occurred_at": _TEXT,
        "memo": _NULL_TEXT,
        "created_at": _TEXT,
        "updated_at": _TEXT,
    },
    "entry_tags": {
        "entry_id": _INT,
        "tag_id": _INT,
    },
    "entry_values": {
        "entry_id": _INT,
        "field_def_id": _INT,
        "num_value": _FLOAT,
        "text_value": _NULL_TEXT,
    },
    "matches": {
        "id": _INT,
        "entry_id": _INT,
        "opponent": _TEXT,
        "score": _TEXT,
        "result": _TEXT,
        "sort_order": _INT,
    },
    "levels": {
        "id": _INT,
        "activity_id": _INT,
        "track": _TEXT,
        "ordinal": _INT,
        "code": _TEXT,
        "label": _TEXT,
        "archived_at": _NULL_TEXT,
    },
    "level_rules": {
        "id": _INT,
        "activity_id": _INT,
        "from_level_id": _NULL_INT,
        "to_level_id": _INT,
        "gate_type": _TEXT,
        "gate_value": _FLOAT,
        "min_age": _NULL_INT,
        "prereq_level_id": _NULL_INT,
    },
}

# Per-table length caps: column -> max length. Only listed columns are capped.
_LENGTH_CAPS: dict[str, dict[str, int]] = {
    "categories": {"name": MAX_NAME_LEN},
    "sub_tallies": {"name": MAX_NAME_LEN},
    "tags": {"name": MAX_NAME_LEN},
    "field_defs": {"label": MAX_NAME_LEN},
    "entries": {"memo": MAX_TEXT_LEN},
    "entry_values": {"text_value": MAX_TEXT_LEN},
    "matches": {"opponent": MAX_NAME_LEN, "score": MAX_NAME_LEN},
    "levels": {"code": MAX_NAME_LEN, "label": MAX_NAME_LEN},
}

# Per-table enum constraints: column -> allowed value set.
_ENUM_CAPS: dict[str, dict[str, frozenset[str]]] = {
    "sub_tallies": {"count_mode": _COUNT_MODES},
    "field_defs": {"kind": _FIELD_KINDS},
    "matches": {"result": _MATCH_RESULTS},
    "level_rules": {"gate_type": _GATE_TYPES},
}


def import_data(owner_id: int, payload: dict[str, Any]) -> dict[str, int]:
    """Replace *owner_id*'s data with the contents of *payload*.

    *payload* is the envelope ``export_data`` produces:
    ``{"schema_version": 1, "exported_at": ..., "data": {<ten tables>}}``.
    The whole payload is validated first (schema version, exact table keys, row
    caps, per-row shape/type/enum/length, and payload-internal referential
    integrity). Only if validation fully passes does any write happen, and the
    write is a single transaction: every existing owned row for *owner_id* is
    deleted, then the payload's rows are inserted with **fresh** primary keys and
    foreign keys remapped to those fresh keys. Every inserted row gets
    ``owner_id = owner_id`` (the authenticated caller's id) set explicitly —
    nothing in the payload can override the owner. Finally, each imported
    sub-tally's cache (``cached_count`` / ``cached_streak`` / ``last_entry_at``)
    is rebuilt from the imported entries.

    Returns a per-table count of inserted rows.

    Raises :class:`ImportValidationError` (a ``ValueError``) on any validation
    failure, before touching the database. Any error during the write phase
    propagates and the transaction rolls back (``db.connect()`` rolls back on
    exception), leaving the account's prior data intact.
    """
    data = _validate_payload(payload)

    with db.connect() as conn:
        conn.execute("BEGIN")
        _delete_owner_data(conn, owner_id)
        summary, activity_ids = _insert_payload(conn, owner_id, data)
        # Rebuild caches from the imported entries, inside this same transaction
        # (entries.recompute opens its own connection and would not see these
        # still-uncommitted rows). _refresh_cache uses the identical truth-from-
        # entries computation that recompute does, so values match exactly.
        for new_sub_id in activity_ids:
            entries._refresh_cache(conn, new_sub_id, owner_id)

    return summary


# --- validation ------------------------------------------------------------


def _validate_payload(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Fully validate *payload* and return its ``data`` mapping.

    Raises :class:`ImportValidationError` with a content-free message on the
    first problem found.
    """
    if not isinstance(payload, dict):
        raise ImportValidationError("payload must be a dict")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ImportValidationError(
            f"unsupported schema_version (expected {SCHEMA_VERSION}, "
            f"got {payload.get('schema_version')!r})"
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ImportValidationError("payload['data'] must be a dict")

    keys = set(data.keys())
    expected = set(_DATA_TABLES)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise ImportValidationError(
            f"payload['data'] keys mismatch (missing={missing}, extra={extra})"
        )

    for table in _DATA_TABLES:
        rows = data[table]
        if not isinstance(rows, list):
            raise ImportValidationError(f"{table} must be a list")
        if len(rows) > MAX_ROWS_PER_TABLE:
            raise ImportValidationError(
                f"{table} has {len(rows)} rows, exceeding the cap of {MAX_ROWS_PER_TABLE}"
            )

    for table in _DATA_TABLES:
        _validate_rows(table, data[table])

    _validate_references(data)
    return data


def _validate_rows(table: str, rows: list[Any]) -> None:
    """Validate every row's shape, types, enums, and length caps for *table*."""
    spec = _TABLE_SPECS[table]
    expected_keys = set(spec.keys())
    length_caps = _LENGTH_CAPS.get(table, {})
    enum_caps = _ENUM_CAPS.get(table, {})

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ImportValidationError(f"{table}[{i}] is not a dict")
        row_keys = set(row.keys())
        if row_keys != expected_keys:
            missing = sorted(expected_keys - row_keys)
            extra = sorted(row_keys - expected_keys)
            raise ImportValidationError(
                f"{table}[{i}] key mismatch (missing={missing}, extra={extra})"
            )

        for col, type_tag in spec.items():
            _check_type(table, i, col, type_tag, row[col])

        for col, cap in length_caps.items():
            value = row[col]
            if isinstance(value, str) and len(value) > cap:
                raise ImportValidationError(f"{table}[{i}].{col} exceeds the {cap}-character limit")

        for col, allowed in enum_caps.items():
            if row[col] not in allowed:
                raise ImportValidationError(f"{table}[{i}].{col} is not one of {sorted(allowed)}")


def _check_type(table: str, i: int, col: str, type_tag: str, value: Any) -> None:
    """Type-check one cell. Booleans are rejected where an int is expected
    (``bool`` is an ``int`` subclass in Python, but never a valid id/ordinal)."""
    if type_tag == _INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ImportValidationError(f"{table}[{i}].{col} must be an integer")
    elif type_tag == _NULL_INT:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ImportValidationError(f"{table}[{i}].{col} must be an integer or null")
    elif type_tag == _FLOAT:
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ImportValidationError(f"{table}[{i}].{col} must be a number or null")
    elif type_tag == _TEXT:
        if not isinstance(value, str):
            raise ImportValidationError(f"{table}[{i}].{col} must be a string")
    elif type_tag == _NULL_TEXT:
        if value is not None and not isinstance(value, str):
            raise ImportValidationError(f"{table}[{i}].{col} must be a string or null")
    else:  # pragma: no cover - guards against a spec typo
        raise ImportValidationError(f"{table}[{i}].{col} has an unknown type spec")


def _validate_references(data: dict[str, list[dict[str, Any]]]) -> None:
    """Check every payload-internal foreign-key reference resolves within the
    payload's own tables (these are pre-remap export ids, not live-DB ids)."""
    category_ids = {r["id"] for r in data["categories"]}
    activity_ids = {r["id"] for r in data["sub_tallies"]}
    field_def_ids = {r["id"] for r in data["field_defs"]}
    tag_ids = {r["id"] for r in data["tags"]}
    entry_ids = {r["id"] for r in data["entries"]}
    level_ids = {r["id"] for r in data["levels"]}

    def _require(table: str, i: int, col: str, value: Any, universe: set[int]) -> None:
        if value not in universe:
            raise ImportValidationError(
                f"{table}[{i}].{col} references an id not present in the payload"
            )

    for i, r in enumerate(data["sub_tallies"]):
        _require("sub_tallies", i, "category_id", r["category_id"], category_ids)
    for i, r in enumerate(data["field_defs"]):
        _require("field_defs", i, "activity_id", r["activity_id"], activity_ids)
    for i, r in enumerate(data["tags"]):
        _require("tags", i, "field_def_id", r["field_def_id"], field_def_ids)
    for i, r in enumerate(data["entries"]):
        _require("entries", i, "activity_id", r["activity_id"], activity_ids)
    for i, r in enumerate(data["entry_tags"]):
        _require("entry_tags", i, "entry_id", r["entry_id"], entry_ids)
        _require("entry_tags", i, "tag_id", r["tag_id"], tag_ids)
    for i, r in enumerate(data["entry_values"]):
        _require("entry_values", i, "entry_id", r["entry_id"], entry_ids)
        _require("entry_values", i, "field_def_id", r["field_def_id"], field_def_ids)
    for i, r in enumerate(data["matches"]):
        _require("matches", i, "entry_id", r["entry_id"], entry_ids)
    for i, r in enumerate(data["levels"]):
        _require("levels", i, "activity_id", r["activity_id"], activity_ids)
    for i, r in enumerate(data["level_rules"]):
        _require("level_rules", i, "activity_id", r["activity_id"], activity_ids)
        _require("level_rules", i, "to_level_id", r["to_level_id"], level_ids)
        if r["from_level_id"] is not None:
            _require("level_rules", i, "from_level_id", r["from_level_id"], level_ids)
        if r["prereq_level_id"] is not None:
            _require("level_rules", i, "prereq_level_id", r["prereq_level_id"], level_ids)


# --- write -----------------------------------------------------------------


def _delete_owner_data(conn: sqlite3.Connection, owner_id: int) -> None:
    """Delete all of *owner_id*'s rows.

    Deleting ``category`` cascades (ON DELETE CASCADE, with ``foreign_keys=ON``
    set by ``db.py``) to ``activity`` → ``field_def`` / ``level`` /
    ``level_rule`` / ``entry`` → ``entry_tag`` / ``entry_value`` / ``match``, and
    ``tag`` via ``field_def``. The remaining explicit deletes are defensive: they
    cover any owner-scoped row that a (hypothetical) future detachment from the
    category cascade would leave behind, and they are no-ops when the cascade has
    already removed the rows.
    """
    conn.execute("DELETE FROM category WHERE owner_id = ?", (owner_id,))
    # Defensive sweep of every directly owner-scoped table (no-op after cascade).
    for table in ("match", "level_rule", "level", "tag", "entry", "activity"):
        conn.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner_id,))  # noqa: S608


def _insert_payload(
    conn: sqlite3.Connection,
    owner_id: int,
    data: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, int], list[int]]:
    """Insert every payload row with fresh PKs and remapped FKs.

    Returns ``(summary, new_activity_ids)`` where *summary* is a per-table
    inserted-row count and *new_activity_ids* are the freshly-assigned sub-tally
    ids (for the post-insert cache rebuild). Insert order respects dependencies:
    categories → sub_tallies → (field_defs, levels) → (tags, level_rules) →
    entries → (entry_tags, entry_values, matches).
    """
    cat_map: dict[int, int] = {}
    sub_map: dict[int, int] = {}
    field_map: dict[int, int] = {}
    tag_map: dict[int, int] = {}
    entry_map: dict[int, int] = {}
    level_map: dict[int, int] = {}

    for r in data["categories"]:
        cur = conn.execute(
            "INSERT INTO category"
            " (owner_id, name, color, icon, sort_order, archived_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                r["name"],
                r["color"],
                r["icon"],
                r["sort_order"],
                r["archived_at"],
                r["created_at"],
            ),
        )
        cat_map[r["id"]] = cur.lastrowid

    for r in data["sub_tallies"]:
        cur = conn.execute(
            "INSERT INTO activity"
            " (owner_id, category_id, name, count_mode, config_json, sort_order,"
            "  archived_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                cat_map[r["category_id"]],
                r["name"],
                r["count_mode"],
                r["config_json"],
                r["sort_order"],
                r["archived_at"],
                r["created_at"],
            ),
        )
        sub_map[r["id"]] = cur.lastrowid

    for r in data["field_defs"]:
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, config_json, sort_order)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                sub_map[r["activity_id"]],
                r["kind"],
                r["label"],
                r["config_json"],
                r["sort_order"],
            ),
        )
        field_map[r["id"]] = cur.lastrowid

    for r in data["levels"]:
        cur = conn.execute(
            "INSERT INTO level"
            " (activity_id, owner_id, track, ordinal, code, label, archived_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sub_map[r["activity_id"]],
                owner_id,
                r["track"],
                r["ordinal"],
                r["code"],
                r["label"],
                r["archived_at"],
            ),
        )
        level_map[r["id"]] = cur.lastrowid

    for r in data["tags"]:
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order, archived_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                field_map[r["field_def_id"]],
                r["name"],
                r["sort_order"],
                r["archived_at"],
                r["created_at"],
            ),
        )
        tag_map[r["id"]] = cur.lastrowid

    for r in data["level_rules"]:
        from_level = r["from_level_id"]
        prereq = r["prereq_level_id"]
        conn.execute(
            "INSERT INTO level_rule"
            " (owner_id, activity_id, from_level_id, to_level_id, gate_type,"
            "  gate_value, min_age, prereq_level_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                sub_map[r["activity_id"]],
                level_map[from_level] if from_level is not None else None,
                level_map[r["to_level_id"]],
                r["gate_type"],
                r["gate_value"],
                r["min_age"],
                level_map[prereq] if prereq is not None else None,
            ),
        )

    for r in data["entries"]:
        cur = conn.execute(
            "INSERT INTO entry"
            " (owner_id, activity_id, occurred_at, memo, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                sub_map[r["activity_id"]],
                r["occurred_at"],
                r["memo"],
                r["created_at"],
                r["updated_at"],
            ),
        )
        entry_map[r["id"]] = cur.lastrowid

    for r in data["entry_tags"]:
        conn.execute(
            "INSERT INTO entry_tag (entry_id, tag_id) VALUES (?, ?)",
            (entry_map[r["entry_id"]], tag_map[r["tag_id"]]),
        )

    for r in data["entry_values"]:
        conn.execute(
            "INSERT INTO entry_value (entry_id, field_def_id, num_value, text_value)"
            " VALUES (?, ?, ?, ?)",
            (
                entry_map[r["entry_id"]],
                field_map[r["field_def_id"]],
                r["num_value"],
                r["text_value"],
            ),
        )

    for r in data["matches"]:
        conn.execute(
            "INSERT INTO match (entry_id, owner_id, opponent, score, result, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry_map[r["entry_id"]],
                owner_id,
                r["opponent"],
                r["score"],
                r["result"],
                r["sort_order"],
            ),
        )

    summary = {table: len(data[table]) for table in _DATA_TABLES}
    return summary, list(sub_map.values())
