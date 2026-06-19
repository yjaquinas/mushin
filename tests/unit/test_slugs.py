"""Unit tests for app.services.slugs (public-profile Phase 1, Task 5).

Acceptance criteria
-------------------
1. ``slugify`` matches the 0006 migration backfill semantics: accent folding,
   non-[a-z0-9] -> '-', collapse/trim, non-empty fallback.
2. ``unique_slug`` disambiguates collisions per owner with numeric suffixes,
   and does NOT collide across owners (each owner's namespace is independent).

Each test uses its own fresh migrated SQLite in ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.migrate import run_migrations
from app.services import slugs

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


def _make_user(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO user (auth_provider) VALUES ('email')")
    conn.commit()
    return cur.lastrowid


def _make_category(conn: sqlite3.Connection, owner_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'C', 0)",
        (owner_id,),
    )
    conn.commit()
    return cur.lastrowid


def _insert_activity(
    conn: sqlite3.Connection,
    owner_id: int,
    category_id: int,
    slug: str,
    *,
    archived: bool = False,
) -> int:
    cur = conn.execute(
        "INSERT INTO activity"
        " (owner_id, category_id, name, slug, count_mode, sort_order, archived_at)"
        " VALUES (?, ?, ?, ?, 'running', 0, ?)",
        (owner_id, category_id, slug, slug, "2020-01-01T00:00:00Z" if archived else None),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 1. slugify — pure function edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Workout", "workout"),
        ("Morning Workout", "morning-workout"),
        ("UPPER CASE", "upper-case"),
        ("trailing  spaces   ", "trailing-spaces"),
        ("  leading", "leading"),
        ("multiple---dashes", "multiple-dashes"),
        ("under_score", "under-score"),
        ("punctuation!!!here", "punctuation-here"),
        ("dots.and,commas", "dots-and-commas"),
        ("digits123ok", "digits123ok"),
        # Accented Latin folds to ASCII (matches the migration REPLACE chain).
        ("Café", "cafe"),
        ("Pâtisserie Niçoise", "patisserie-nicoise"),
        ("jalapeño", "jalapeno"),
        ("résumé", "resume"),
    ],
)
def test_slugify_basic_and_accents(name, expected):
    assert slugs.slugify(name) == expected


def test_slugify_uppercase_accents_match_migration():
    """The 0006 REPLACE chain only targets lowercase accented chars, and runs
    BEFORE LOWER(); uppercase accented chars are therefore never folded and map
    to '-'. A name made only of them collapses to the fallback — slugify must
    reproduce that, not fold them."""
    assert slugs.slugify("ÀÉÎÕÜ") == slugs.FALLBACK_SLUG
    # A real word with a leading uppercase accent: only the ASCII tail survives.
    assert slugs.slugify("Élan") == "lan"


def test_slugify_empty_string_falls_back():
    assert slugs.slugify("") == slugs.FALLBACK_SLUG


def test_slugify_punctuation_only_falls_back():
    assert slugs.slugify("!!!") == slugs.FALLBACK_SLUG
    assert slugs.slugify("   ") == slugs.FALLBACK_SLUG
    assert slugs.slugify("---") == slugs.FALLBACK_SLUG


def test_slugify_non_latin_script_falls_back():
    # Hangul / CJK are not transliterated; they map to '-' and collapse away,
    # leaving nothing, so we get the fallback — same as the migration.
    assert slugs.slugify("무심") == slugs.FALLBACK_SLUG
    assert slugs.slugify("剣道") == slugs.FALLBACK_SLUG


def test_slugify_mixed_latin_and_non_latin_keeps_latin():
    assert slugs.slugify("Kendo 검도 practice") == "kendo-practice"


def test_slugify_matches_migration_for_known_names():
    """Spot-check the exact transforms the 0006 migration documents."""
    assert slugs.slugify("Workout") == "workout"
    # Pathological collapse: '!!!' -> all dashes -> trimmed empty -> fallback.
    assert slugs.slugify("@#$%") == slugs.FALLBACK_SLUG


# ---------------------------------------------------------------------------
# 2. unique_slug — per-owner collision handling
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_with_owners(tmp_path: Path):
    db_path = _make_db(tmp_path)
    conn = _raw(db_path)
    owner_a = _make_user(conn)
    owner_b = _make_user(conn)
    cat_a = _make_category(conn, owner_a)
    cat_b = _make_category(conn, owner_b)
    conn.close()
    return db_path, owner_a, owner_b, cat_a, cat_b


def test_unique_slug_no_collision_returns_base(db_with_owners):
    db_path, owner_a, _, _, _ = db_with_owners
    conn = _raw(db_path)
    assert slugs.unique_slug(conn, owner_a, "Workout") == "workout"
    conn.close()


def test_unique_slug_appends_suffix_on_collision(db_with_owners):
    db_path, owner_a, _, cat_a, _ = db_with_owners
    conn = _raw(db_path)
    _insert_activity(conn, owner_a, cat_a, "workout")
    assert slugs.unique_slug(conn, owner_a, "Workout") == "workout-2"
    conn.close()


def test_unique_slug_increments_through_multiple_collisions(db_with_owners):
    db_path, owner_a, _, cat_a, _ = db_with_owners
    conn = _raw(db_path)
    _insert_activity(conn, owner_a, cat_a, "workout")
    _insert_activity(conn, owner_a, cat_a, "workout-2")
    assert slugs.unique_slug(conn, owner_a, "Workout") == "workout-3"
    conn.close()


def test_unique_slug_independent_across_owners(db_with_owners):
    """The same base slug under two different owners both get the base slug."""
    db_path, owner_a, owner_b, cat_a, cat_b = db_with_owners
    conn = _raw(db_path)
    _insert_activity(conn, owner_a, cat_a, "workout")
    # Owner B has no 'workout' yet, so it gets the base slug — no cross-owner
    # collision with owner A's existing 'workout'.
    assert slugs.unique_slug(conn, owner_b, "Workout") == "workout"
    conn.close()


def test_unique_slug_ignores_archived_rows(db_with_owners):
    """An archived activity with the slug doesn't block reuse of the slug."""
    db_path, owner_a, _, cat_a, _ = db_with_owners
    conn = _raw(db_path)
    _insert_activity(conn, owner_a, cat_a, "workout", archived=True)
    # The unique partial index excludes archived rows, so the base slug is free.
    assert slugs.unique_slug(conn, owner_a, "Workout") == "workout"
    conn.close()
