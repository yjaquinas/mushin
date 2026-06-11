"""Declarative template definitions for onboarding seeding.

Each template is a plain Python data structure that ``seeding.py`` iterates to
insert rows — no per-activity code in the seeding loop. The shapes mirror the
DB schema exactly:

  category
    └── sub_tally (count_mode)
          ├── field_def  (kind, label, sort_order)
          └── levels[]   (track, ordinal, code, label)

Level-rule specs live in ``LEVEL_RULES`` at the bottom of this module, keyed by
category name + sub-tally name. ``seeding.seed_level_rules`` resolves the
``from_code``/``to_code``/``prereq_code`` fields to live row ids at seed time.

v1 templates: 검도 (kendo) + 독서 (reading).
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
# 검도 (kendo) — primary track: 1급 → 9단; parallel track: 연사/교사/범사
# ---------------------------------------------------------------------------
#
# KKA dan ladder codes follow the pattern used throughout: 1급 = "1gup";
# 초단 (= 1단) = "chodan"; 2단–9단 = "2dan"–"9dan".
# Shōgō codes: "yeonsа", "gyosa", "beomsа" (romanisation of 연사/교사/범사).
#
# Ordinals are contiguous and 1-based within each track so that the progression
# engine can ORDER BY ordinal to walk the ladder.

_KENDO_GRADING_LEVELS: list[LevelSpec] = [
    # --- Primary dan track ---------------------------------------------------
    {"track": "dan", "ordinal": 1, "code": "1gup", "label": "1급"},
    {"track": "dan", "ordinal": 2, "code": "chodan", "label": "초단"},
    {"track": "dan", "ordinal": 3, "code": "2dan", "label": "2단"},
    {"track": "dan", "ordinal": 4, "code": "3dan", "label": "3단"},
    {"track": "dan", "ordinal": 5, "code": "4dan", "label": "4단"},
    {"track": "dan", "ordinal": 6, "code": "5dan", "label": "5단"},
    {"track": "dan", "ordinal": 7, "code": "6dan", "label": "6단"},
    {"track": "dan", "ordinal": 8, "code": "7dan", "label": "7단"},
    {"track": "dan", "ordinal": 9, "code": "8dan", "label": "8단"},
    {"track": "dan", "ordinal": 10, "code": "9dan", "label": "9단"},
    # --- Parallel shōgō / 칭호 track -----------------------------------------
    # Ordinals are independent of the dan track (separate track namespace).
    {"track": "shogo", "ordinal": 1, "code": "yeonsa", "label": "연사"},
    {"track": "shogo", "ordinal": 2, "code": "gyosa", "label": "교사"},
    {"track": "shogo", "ordinal": 3, "code": "beomsa", "label": "범사"},
]

KENDO: CategorySpec = {
    "name": "검도",
    "color": None,
    "sort_order": 0,
    "sub_tallies": [
        {
            "name": "수련",  # practice
            "count_mode": "running",
            "sort_order": 0,
            "field_defs": [
                {"kind": "tag_group", "label": "기술", "sort_order": 0},
                {"kind": "tag_group", "label": "장소", "sort_order": 1},
                {"kind": "count", "label": "횟수", "sort_order": 2},
                {"kind": "memo", "label": "메모", "sort_order": 3},
            ],
            "levels": [],
        },
        {
            "name": "시합",  # tournament
            "count_mode": "running",
            "sort_order": 1,
            "field_defs": [
                {"kind": "match_list", "label": "경기 목록", "sort_order": 0},
                {"kind": "memo", "label": "메모", "sort_order": 1},
            ],
            "levels": [],
        },
        {
            "name": "심사",  # grading
            "count_mode": "progression",
            "sort_order": 2,
            "field_defs": [
                {"kind": "level", "label": "단위", "sort_order": 0},
                {"kind": "result", "label": "결과", "sort_order": 1},
                {"kind": "memo", "label": "메모", "sort_order": 2},
            ],
            "levels": _KENDO_GRADING_LEVELS,
        },
    ],
}


# ---------------------------------------------------------------------------
# 독서 (reading) — count-gated tier progression
# ---------------------------------------------------------------------------
#
# Reading tiers gate on the total number of books logged (gate_type='count').
# Five tiers give meaningful milestones without overwhelming a new reader.
#
# Tier thresholds (confirmed by seed-author, referenced by Task 7 level_rules):
#   입문 →  10 books
#   초급 →  25 books
#   중급 →  50 books
#   고급 → 100 books
#   달인 →  no upper limit (final tier)
#
# Ordinals are 1-based. Task 7 seeds the level_rule rows with gate_value equal
# to the *threshold to reach that tier* (i.e. to enter 초급 you need 10 books).

_READING_LEVELS: list[LevelSpec] = [
    {"track": "tier", "ordinal": 1, "code": "ibmun", "label": "입문"},  # beginner
    {"track": "tier", "ordinal": 2, "code": "chogup", "label": "초급"},  # elementary
    {"track": "tier", "ordinal": 3, "code": "junggup", "label": "중급"},  # intermediate
    {"track": "tier", "ordinal": 4, "code": "gogup", "label": "고급"},  # advanced
    {"track": "tier", "ordinal": 5, "code": "dain", "label": "달인"},  # master
]

READING: CategorySpec = {
    "name": "독서",
    "color": None,
    "sort_order": 1,
    "sub_tallies": [
        {
            "name": "독서",  # single sub-tally (same name as category)
            "count_mode": "progression",
            "sort_order": 0,
            "field_defs": [
                {"kind": "count", "label": "페이지", "sort_order": 0},
                {"kind": "tag_group", "label": "장르", "sort_order": 1},
                {"kind": "tag_group", "label": "저자", "sort_order": 2},
                {"kind": "level", "label": "단계", "sort_order": 3},
                {"kind": "memo", "label": "메모", "sort_order": 4},
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
# Keyed by (category_name, sub_tally_name) → list[LevelRuleSpec].
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
#   yeonsa:    from_code=None,   prereq_code='5dan',   time=3y
#              clock: 5단 held ≥ 3y (from_level_id=NULL → clock = prereq_at)
#   gyosa A:   from_code=None,   prereq_code='yeonsa', time=7y
#              clock: 연사 held ≥ 7y
#   gyosa B:   from_code=None,   prereq_code='6dan',   time=4y
#              clock: 6단 held ≥ 4y  (also requires 연사 by ordinal — the
#              shogo-track current_level check means this path is only reached
#              after 연사 is attained; the engine doesn't enforce a separate 연사
#              prereq column on path B, matching the fixture)
#   beomsa:    from_code='gyosa', prereq_code='8dan',  time=10y, min_age=60
#              clock: 교사 held ≥ 10y; prereq: 8단 held (existence check only)
#              LIMITATION: the 8단 ≥ 8y requirement stated in KKA regulations
#              cannot be expressed as a separate "prereq held-for-N-years" in a
#              single level_rule row. The engine has no such column; only the
#              교사 ≥ 10y clock is enforced. This matches the engine's own test
#              fixture (test_shogo_beomsa_dual_clock_and_age) which tests a user
#              with 8단 9y + 교사 11y and passes — the "dual clock" in the test
#              name refers to the two date-checks in the test scenario, not two
#              separate engine-level time gates. A future engine enhancement can
#              add a prereq_min_years column; for now we match the fixture shape.
# ---------------------------------------------------------------------------

LEVEL_RULES: dict[tuple[str, str], list[LevelRuleSpec]] = {
    # -------------------------------------------------------------------------
    # 검도 / 심사 — KKA dan ladder (time gates) + shōgō prestige track
    # -------------------------------------------------------------------------
    ("검도", "심사"): [
        # Dan ladder — gate_type='time', gate_value=years at previous grade
        # min_age is on the TARGET level per KKA 심사규정
        {
            "to_code": "chodan",
            "from_code": "1gup",
            "gate_type": "time",
            "gate_value": 0.25,
            "min_age": 13,
        },  # noqa: E501
        {"to_code": "2dan", "from_code": "chodan", "gate_type": "time", "gate_value": 1.0},
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
        # yeonsa: prereq 5단, 5단 held ≥ 3y
        {"to_code": "yeonsa", "prereq_code": "5dan", "gate_type": "time", "gate_value": 3.0},
        # gyosa path A (OR with path B): prereq 연사, 연사 held ≥ 7y
        {"to_code": "gyosa", "prereq_code": "yeonsa", "gate_type": "time", "gate_value": 7.0},
        # gyosa path B (OR with path A): prereq 6단, 6단 held ≥ 4y
        {"to_code": "gyosa", "prereq_code": "6dan", "gate_type": "time", "gate_value": 4.0},
        # beomsa: prereq 8단 (held check), clock from 교사 attainment ≥ 10y, age ≥ 60
        {
            "to_code": "beomsa",
            "from_code": "gyosa",
            "prereq_code": "8dan",
            "gate_type": "time",
            "gate_value": 10.0,
            "min_age": 60,
        },  # noqa: E501
    ],
    # -------------------------------------------------------------------------
    # 독서 — count-gated tier progression
    # gate_value = cumulative lifetime book count to reach that tier
    # -------------------------------------------------------------------------
    ("독서", "독서"): [
        {"to_code": "chogup", "from_code": "ibmun", "gate_type": "count", "gate_value": 10.0},
        {"to_code": "junggup", "from_code": "chogup", "gate_type": "count", "gate_value": 25.0},
        {"to_code": "gogup", "from_code": "junggup", "gate_type": "count", "gate_value": 50.0},
        {"to_code": "dain", "from_code": "gogup", "gate_type": "count", "gate_value": 100.0},
    ],
}
