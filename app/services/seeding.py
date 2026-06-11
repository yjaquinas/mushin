"""Onboarding template seeding for Mushin.

Public entry point
------------------
``seed_account(owner_id)`` — idempotent. Inserts the v1 starter templates
(검도 + 독서) for *owner_id*. Re-running is a no-op: the guard key is the
presence of a category named exactly as in the template under that owner_id.
Every inserted row carries the passed *owner_id*; another owner's seed is
completely independent.

Called by
---------
* ``app.auth.routes._lazy_seed`` — on the guest's first interaction.
* Real-account signup paths may call it immediately after user creation.

Level rules (Task 7 seam)
-------------------------
``seed_level_rules(owner_id, conn, level_ids)`` is the forward seam for Task 7.
It currently inserts nothing (empty stub). Task 7 fills it in with the
authoritative KKA dan/shōgō gate values and reading-tier thresholds.

TODO(task-7): fill ``seed_level_rules`` with the following level_rule rows:

  KKA dan ladder (gate_type='time', gate_value in fractional years):
  ┌────────────────┬────────────────┬──────────────┬─────────┬──────────┐
  │ from_code      │ to_code        │ gate_value   │ min_age │ notes    │
  ├────────────────┼────────────────┼──────────────┼─────────┼──────────┤
  │ 1gup           │ chodan         │ 0.25         │ 13      │ 3 months │
  │ chodan         │ 2dan           │ 1.0          │ None    │          │
  │ 2dan           │ 3dan           │ 2.0          │ 16      │ KKA      │
  │ 3dan           │ 4dan           │ 3.0          │ None    │          │
  │ 4dan           │ 5dan           │ 4.0          │ None    │          │
  │ 5dan           │ 6dan           │ 5.0          │ None    │          │
  │ 6dan           │ 7dan           │ 6.0          │ None    │          │
  │ 7dan           │ 8dan           │ 10.0         │ 46      │          │
  │ 8dan           │ 9dan           │ 10.0         │ 65      │ KKA-only │
  └────────────────┴────────────────┴──────────────┴─────────┴──────────┘

  Shōgō / 칭호 (parallel track='shogo'; prereq_level_id points to the required
  dan-track level, gate_type='time', gate_value in years):
  ┌──────────┬──────────────────────────────────────────────────────────────┐
  │ to_code  │ rule description                                             │
  ├──────────┼──────────────────────────────────────────────────────────────┤
  │ yeonsa   │ prereq=5단(5dan), 5단 held ≥ 3 yrs                           │
  │ gyosa    │ path A: prereq=연사(yeonsa), 연사 held ≥ 7 yrs                 │
  │          │ path B: prereq=6단(6dan)+연사, 6단 held ≥ 4 yrs  (OR of A/B) │
  │ beomsa   │ prereq=교사(gyosa)+8단, 8단 ≥ 8 yrs AND 교사 ≥ 10 yrs, age≥60│
  └──────────┴──────────────────────────────────────────────────────────────┘

  Reading tiers (gate_type='count', gate_value = books needed to reach tier):
  ┌──────────┬────────────┐
  │ to_code  │ gate_value │
  ├──────────┼────────────┤
  │ chogup   │ 10         │
  │ junggup  │ 25         │
  │ gogup    │ 50         │
  │ dain     │ 100        │
  └──────────┴────────────┘
  (입문/ibmun is the entry tier; no rule needed to enter it.)
"""

from __future__ import annotations

import sqlite3

import structlog

from app.models import db
from app.services.seed_data import LEVEL_RULES, V1_TEMPLATES, CategorySpec, LevelRuleSpec

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def seed_account(owner_id: int) -> None:
    """Seed the v1 starter templates for *owner_id*.

    Idempotent: if the owner already has any category whose name matches a
    template category name, that category (and all its children) is skipped.
    Re-running inserts nothing new. Every seeded row carries *owner_id*.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        _seed_templates(owner_id, conn)
    log.info("seeding.complete", owner_id=owner_id)


# ---------------------------------------------------------------------------
# Internal seeding logic
# ---------------------------------------------------------------------------


def _seed_templates(owner_id: int, conn: sqlite3.Connection) -> None:
    """Insert all V1_TEMPLATES for *owner_id*, skipping already-present ones."""
    existing_names = _existing_category_names(owner_id, conn)

    for cat_spec in V1_TEMPLATES:
        if cat_spec["name"] in existing_names:
            log.debug("seeding.category.skip", owner_id=owner_id, name=cat_spec["name"])
            continue
        _insert_category(owner_id, conn, cat_spec)


def _existing_category_names(owner_id: int, conn: sqlite3.Connection) -> set[str]:
    """Return the set of category names already seeded for this owner."""
    rows = conn.execute(
        "SELECT name FROM category WHERE owner_id = ?",
        (owner_id,),
    ).fetchall()
    return {row[0] for row in rows}


def _insert_category(
    owner_id: int,
    conn: sqlite3.Connection,
    cat_spec: CategorySpec,
) -> None:
    """Insert a category and all its sub-tallies, field_defs, levels."""
    cur = conn.execute(
        "INSERT INTO category (owner_id, name, color, sort_order) VALUES (?, ?, ?, ?)",
        (owner_id, cat_spec["name"], cat_spec["color"], cat_spec["sort_order"]),
    )
    category_id = cur.lastrowid
    log.debug("seeding.category.insert", owner_id=owner_id, name=cat_spec["name"])

    for st_spec in cat_spec["sub_tallies"]:
        cur = conn.execute(
            "INSERT INTO sub_tally"
            " (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                owner_id,
                category_id,
                st_spec["name"],
                st_spec["count_mode"],
                st_spec["sort_order"],
            ),
        )
        sub_tally_id = cur.lastrowid

        for fd_spec in st_spec["field_defs"]:
            conn.execute(
                "INSERT INTO field_def (sub_tally_id, kind, label, sort_order) VALUES (?, ?, ?, ?)",
                (sub_tally_id, fd_spec["kind"], fd_spec["label"], fd_spec["sort_order"]),
            )

        # Collect inserted level ids keyed by code for the rule seam.
        level_ids: dict[str, int] = {}
        for lv_spec in st_spec["levels"]:
            cur = conn.execute(
                "INSERT INTO level (sub_tally_id, owner_id, track, ordinal, code, label)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sub_tally_id,
                    owner_id,
                    lv_spec["track"],
                    lv_spec["ordinal"],
                    lv_spec["code"],
                    lv_spec["label"],
                ),
            )
            level_ids[lv_spec["code"]] = cur.lastrowid

        if level_ids:
            seed_level_rules(
                owner_id,
                conn,
                sub_tally_id,
                level_ids,
                category_name=cat_spec["name"],
                sub_tally_name=st_spec["name"],
            )


# ---------------------------------------------------------------------------
# Task 7 — level_rule insertion
# ---------------------------------------------------------------------------


def seed_level_rules(
    owner_id: int,
    conn: sqlite3.Connection,
    sub_tally_id: int,
    level_ids: dict[str, int],
    *,
    category_name: str,
    sub_tally_name: str,
) -> None:
    """Insert ``level_rule`` rows for *sub_tally_id*.

    Rule specs are looked up from ``seed_data.LEVEL_RULES`` by
    ``(category_name, sub_tally_name)``. If no spec exists for this sub-tally
    the function is a no-op (running sub-tallies, etc.).

    **Idempotent**: rows are inserted only when ``level_rule`` has no existing
    row for this owner + sub-tally. A partial re-seed (e.g. one category was
    already present and was skipped) is safe because ``_seed_templates`` skips
    the whole category when any category with that name exists — so this
    function is never called for a partially-seeded sub-tally.

    Column semantics (mirrors progression engine / test fixtures):
    - ``from_code`` absent  → ``from_level_id = NULL``;  engine clock runs from
      ``prereq_level_id`` attainment (cross-track prestige gates).
    - ``prereq_code`` absent → ``prereq_level_id = NULL``.
    - ``min_age`` absent     → ``min_age = NULL``.
    """
    rule_specs: list[LevelRuleSpec] | None = LEVEL_RULES.get((category_name, sub_tally_name))
    if not rule_specs:
        return

    # Guard: if any level_rule row already exists for this owner+sub_tally,
    # skip the whole batch (idempotency — re-seeding never duplicates).
    existing = conn.execute(
        "SELECT COUNT(*) FROM level_rule WHERE owner_id = ? AND sub_tally_id = ?",
        (owner_id, sub_tally_id),
    ).fetchone()[0]
    if existing:
        log.debug(
            "seeding.level_rules.skip",
            owner_id=owner_id,
            sub_tally_id=sub_tally_id,
            existing=existing,
        )
        return

    for spec in rule_specs:
        to_id = level_ids[spec["to_code"]]
        from_id = level_ids.get(spec.get("from_code", ""))  # type: ignore[arg-type]
        prereq_id = level_ids.get(spec.get("prereq_code", ""))  # type: ignore[arg-type]
        gate_type = spec.get("gate_type", "manual")
        gate_value = spec.get("gate_value")
        min_age = spec.get("min_age")

        conn.execute(
            "INSERT INTO level_rule"
            " (owner_id, sub_tally_id, from_level_id, to_level_id,"
            "  gate_type, gate_value, min_age, prereq_level_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (owner_id, sub_tally_id, from_id, to_id, gate_type, gate_value, min_age, prereq_id),
        )
        log.debug(
            "seeding.level_rule.insert",
            owner_id=owner_id,
            sub_tally_id=sub_tally_id,
            to_code=spec["to_code"],
            gate_type=gate_type,
        )
