"""Declarative template definitions for onboarding seeding.

Each template is a plain Python data structure that ``seeding.py`` iterates to
insert rows — no per-activity code in the seeding loop. The shapes mirror the
DB schema exactly:

  category (internal 1:1 wrapper, same name as its activity)
    └── activity
          ├── field_def  (kind, label, sort_order)
          └── levels[]   (track, ordinal, code, label)

Level-rule specs live in ``LEVEL_RULES`` at the bottom of this module, keyed by
``(category_name, activity_name)``. ``seeding.seed_level_rules`` resolves the
``from_code``/``to_code``/``prereq_code`` fields to live row ids at seed time.

v1 templates: Kendo + Reading. Each template is a single activity carrying a
combined recipe — Kendo mixes a running practice log, a match-list, and the dan
+ shōgō level ladder on one entry stream. Hero/progression status is derived
from the presence of a ``level``-kind ``field_def``, never from ``count_mode``.
Deferred: cooking, knitting, travel.
"""

from __future__ import annotations

from typing import TypedDict

# ---------------------------------------------------------------------------
# TypedDicts for the template shapes (no runtime enforcement — documentation)
# ---------------------------------------------------------------------------


class FieldDefSpec(TypedDict):
    kind: str  # tag_group | scale | count | memo | match_list | level | result
    label: str
    sort_order: int


class LevelRuleSpec(TypedDict, total=False):
    """Declarative spec for one level_rule row.

    ``from_code`` / ``to_code`` / ``prereq_code`` are level *codes* within the
    same sub-tally; ``seeding.seed_level_rules`` resolves them to row ids.
    ``to_code`` is required (``total=False`` lets optional keys be absent).
    All fields mirror the ``level_rule`` table columns; absent optional keys
    produce ``NULL`` in the row.
    """

    to_code: str  # required
    from_code: str  # NULL when absent → cross-track clock driven by prereq
    prereq_code: str  # NULL when absent
    gate_type: str  # time | count | event | manual
    gate_value: float  # years (time) or books (count)
    min_age: int


class LevelSpec(TypedDict):
    track: str
    ordinal: int
    code: str
    label: str


class SubTallySpec(TypedDict):
    name: str
    count_mode: str  # running | progression
    sort_order: int
    field_defs: list[FieldDefSpec]
    levels: list[LevelSpec]


class CategorySpec(TypedDict):
    name: str
    color: str | None
    sort_order: int
    sub_tallies: list[SubTallySpec]


# ---------------------------------------------------------------------------
# Kendo — primary track: 1st Kyu → 9th Dan; parallel track: Renshi/Kyoshi/Hanshi
# ---------------------------------------------------------------------------
#
# Dan ladder codes follow the pattern used throughout: "1kyu", "1dan"-"9dan".
# Shōgō codes: "renshi", "kyoshi", "hanshi" — the traditional kendo teaching
# titles, used here as generic terminology (no specific federation implied).
#
# Ordinals are contiguous and 1-based within each track so that the progression
# engine can ORDER BY ordinal to walk the ladder.

_KENDO_GRADING_LEVELS: list[LevelSpec] = [
    # --- Primary dan track ---------------------------------------------------
    {"track": "dan", "ordinal": 1, "code": "1kyu", "label": "1st Kyu"},
    {"track": "dan", "ordinal": 2, "code": "1dan", "label": "1st Dan"},
    {"track": "dan", "ordinal": 3, "code": "2dan", "label": "2nd Dan"},
    {"track": "dan", "ordinal": 4, "code": "3dan", "label": "3rd Dan"},
    {"track": "dan", "ordinal": 5, "code": "4dan", "label": "4th Dan"},
    {"track": "dan", "ordinal": 6, "code": "5dan", "label": "5th Dan"},
    {"track": "dan", "ordinal": 7, "code": "6dan", "label": "6th Dan"},
    {"track": "dan", "ordinal": 8, "code": "7dan", "label": "7th Dan"},
    {"track": "dan", "ordinal": 9, "code": "8dan", "label": "8th Dan"},
    {"track": "dan", "ordinal": 10, "code": "9dan", "label": "9th Dan"},
    # --- Parallel shōgō / honorific title track ------------------------------
    # Ordinals are independent of the dan track (separate track namespace).
    {"track": "shogo", "ordinal": 1, "code": "renshi", "label": "Renshi"},
    {"track": "shogo", "ordinal": 2, "code": "kyoshi", "label": "Kyoshi"},
    {"track": "shogo", "ordinal": 3, "code": "hanshi", "label": "Hanshi"},
]

KENDO: CategorySpec = {
    "name": "Kendo",
    "color": None,
    "sort_order": 0,
    "sub_tallies": [
        # One activity, one entry stream. The old three-activity split
        # (Practice / Tournament / Grading) collapses into a single recipe that
        # mixes a running tag/count/memo log, a match-list, and the dan + shōgō
        # level ladder. Hero/progression status is derived from the presence of
        # the `level`-kind field_def below — `count_mode` is back-compat only.
        # The activity shares its name with the category ("Kendo") so the card
        # breadcrumb (category_name != name) stays suppressed.
        {
            "name": "Kendo",
            # Derived value for back-compat columns only; nothing reads it to
            # decide hero/progression (the `level` field_def does that).
            "count_mode": "progression",
            "sort_order": 0,
            "field_defs": [
                # Running practice log (from the old "Practice" activity).
                {"kind": "tag_group", "label": "Technique", "sort_order": 0},
                {"kind": "tag_group", "label": "Location", "sort_order": 1},
                {"kind": "count", "label": "Reps", "sort_order": 2},
                {"kind": "memo", "label": "Memo", "sort_order": 3},
                # Tournament results (from the old "Tournament" activity).
                {"kind": "match_list", "label": "Match List", "sort_order": 4},
                # Dan + shōgō grading ladder (from the old "Grading" activity).
                {"kind": "level", "label": "Rank", "sort_order": 5},
                {"kind": "result", "label": "Result", "sort_order": 6},
            ],
            "levels": _KENDO_GRADING_LEVELS,
        },
    ],
}


# ---------------------------------------------------------------------------
# Reading — count-gated tier progression
# ---------------------------------------------------------------------------
#
# Reading tiers gate on the total number of books logged (gate_type='count').
# Five tiers give meaningful milestones without overwhelming a new reader.
#
# Tier thresholds (confirmed by seed-author, referenced by Task 7 level_rules):
#   Beginner     →  10 books
#   Novice       →  25 books
#   Intermediate →  50 books
#   Advanced     → 100 books
#   Master       →  no upper limit (final tier)
#
# Ordinals are 1-based. Task 7 seeds the level_rule rows with gate_value equal
# to the *threshold to reach that tier* (i.e. to enter Novice you need 10 books).

_READING_LEVELS: list[LevelSpec] = [
    {"track": "tier", "ordinal": 1, "code": "beginner", "label": "Beginner"},
    {"track": "tier", "ordinal": 2, "code": "novice", "label": "Novice"},
    {"track": "tier", "ordinal": 3, "code": "intermediate", "label": "Intermediate"},
    {"track": "tier", "ordinal": 4, "code": "advanced", "label": "Advanced"},
    {"track": "tier", "ordinal": 5, "code": "master", "label": "Master"},
]

READING: CategorySpec = {
    "name": "Reading",
    "color": None,
    "sort_order": 1,
    "sub_tallies": [
        {
            "name": "Reading",  # single sub-tally (same name as category)
            "count_mode": "progression",
            "sort_order": 0,
            "field_defs": [
                {"kind": "count", "label": "Pages", "sort_order": 0},
                {"kind": "tag_group", "label": "Genre", "sort_order": 1},
                {"kind": "tag_group", "label": "Author", "sort_order": 2},
                {"kind": "level", "label": "Tier", "sort_order": 3},
                {"kind": "memo", "label": "Memo", "sort_order": 4},
            ],
            "levels": _READING_LEVELS,
        },
    ],
}


# ---------------------------------------------------------------------------
# The ordered list of templates to seed for every new account
# ---------------------------------------------------------------------------

V1_TEMPLATES: list[CategorySpec] = [KENDO, READING]


# ---------------------------------------------------------------------------
# Level-rule specs — Task 7
#
# Keyed by (category_name, activity_name) → list[LevelRuleSpec].
#
# Engine column contracts (from progression.py + test_progression.py fixtures):
#
#   time gate clock baseline:
#     from_level_id IS NOT NULL  → clock from from_level attainment
#     from_level_id IS NULL      → clock from prereq_level attainment
#
#   prereq_level_id IS NOT NULL  → that level must be currently held
#     (engine checks attained.get(prereq_id) is not None — held check only;
#     it does NOT check how long the prereq has been held)
#
#   Multiple rules sharing the same to_level_id → OR-combined eligibility.
#
# Shōgō shape notes (matching engine test fixture _seed_kendo_full exactly):
#   renshi:    from_code=None,   prereq_code='5dan',   time=3y
#              clock: 5th Dan held ≥ 3y (from_level_id=NULL → clock = prereq_at)
#   kyoshi A:  from_code=None,   prereq_code='renshi', time=7y
#              clock: Renshi held ≥ 7y
#   kyoshi B:  from_code=None,   prereq_code='6dan',   time=4y
#              clock: 6th Dan held ≥ 4y  (also requires Renshi by ordinal — the
#              shogo-track current_level check means this path is only reached
#              after Renshi is attained; the engine doesn't enforce a separate
#              Renshi prereq column on path B, matching the fixture)
#   hanshi:    from_code='kyoshi', prereq_code='8dan',  time=10y, min_age=60
#              clock: Kyoshi held ≥ 10y; prereq: 8th Dan held (existence check only)
#              LIMITATION: the "8th Dan held ≥ 8y" requirement found in some
#              kendo grading regulations cannot be expressed as a separate
#              "prereq held-for-N-years" in a single level_rule row. The engine
#              has no such column; only the Kyoshi ≥ 10y clock is enforced. This
#              matches the engine's own test fixture
#              (test_shogo_beomsa_dual_clock_and_age) which tests a user with
#              8th Dan 9y + Kyoshi 11y and passes — the "dual clock" in the test
#              name refers to the two date-checks in the test scenario, not two
#              separate engine-level time gates. A future engine enhancement can
#              add a prereq_min_years column; for now we match the fixture shape.
# ---------------------------------------------------------------------------

LEVEL_RULES: dict[tuple[str, str], list[LevelRuleSpec]] = {
    # -------------------------------------------------------------------------
    # Kendo — dan ladder (time gates) + shōgō prestige track, on the single
    # merged Kendo activity (activity_name == category_name == "Kendo").
    # -------------------------------------------------------------------------
    ("Kendo", "Kendo"): [
        # Dan ladder — gate_type='time', gate_value=years at previous grade
        # min_age is on the TARGET level
        {
            "to_code": "1dan",
            "from_code": "1kyu",
            "gate_type": "time",
            "gate_value": 0.25,
            "min_age": 13,
        },  # noqa: E501
        {"to_code": "2dan", "from_code": "1dan", "gate_type": "time", "gate_value": 1.0},
        {
            "to_code": "3dan",
            "from_code": "2dan",
            "gate_type": "time",
            "gate_value": 2.0,
            "min_age": 16,
        },  # noqa: E501
        {"to_code": "4dan", "from_code": "3dan", "gate_type": "time", "gate_value": 3.0},
        {"to_code": "5dan", "from_code": "4dan", "gate_type": "time", "gate_value": 4.0},
        {"to_code": "6dan", "from_code": "5dan", "gate_type": "time", "gate_value": 5.0},
        {"to_code": "7dan", "from_code": "6dan", "gate_type": "time", "gate_value": 6.0},
        {
            "to_code": "8dan",
            "from_code": "7dan",
            "gate_type": "time",
            "gate_value": 10.0,
            "min_age": 46,
        },  # noqa: E501
        {
            "to_code": "9dan",
            "from_code": "8dan",
            "gate_type": "time",
            "gate_value": 10.0,
            "min_age": 65,
        },  # noqa: E501
        # Shōgō track — from_code absent → clock runs from prereq attainment
        # renshi: prereq 5th Dan, 5th Dan held ≥ 3y
        {"to_code": "renshi", "prereq_code": "5dan", "gate_type": "time", "gate_value": 3.0},
        # kyoshi path A (OR with path B): prereq Renshi, Renshi held ≥ 7y
        {"to_code": "kyoshi", "prereq_code": "renshi", "gate_type": "time", "gate_value": 7.0},
        # kyoshi path B (OR with path A): prereq 6th Dan, 6th Dan held ≥ 4y
        {"to_code": "kyoshi", "prereq_code": "6dan", "gate_type": "time", "gate_value": 4.0},
        # hanshi: prereq 8th Dan (held check), clock from Kyoshi
        # attainment ≥ 10y, age ≥ 60
        {
            "to_code": "hanshi",
            "from_code": "kyoshi",
            "prereq_code": "8dan",
            "gate_type": "time",
            "gate_value": 10.0,
            "min_age": 60,
        },  # noqa: E501
    ],
    # -------------------------------------------------------------------------
    # Reading — count-gated tier progression
    # gate_value = cumulative lifetime book count to reach that tier
    # -------------------------------------------------------------------------
    ("Reading", "Reading"): [
        {"to_code": "novice", "from_code": "beginner", "gate_type": "count", "gate_value": 10.0},
        {
            "to_code": "intermediate",
            "from_code": "novice",
            "gate_type": "count",
            "gate_value": 25.0,
        },
        {
            "to_code": "advanced",
            "from_code": "intermediate",
            "gate_type": "count",
            "gate_value": 50.0,
        },
        {
            "to_code": "master",
            "from_code": "advanced",
            "gate_type": "count",
            "gate_value": 100.0,
        },
    ],
}
