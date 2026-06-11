"""Tests for the progression engine (Task 7, engine half).

Covers
------
* All four gate types (time / count / event / manual) with passing cases.
* KKA dan ladder: current dan, time-in-grade, next-dan eligibility date — both a
  not-yet-eligible user (4단 attained 2y ago, 5단 needs 4y) and an eligible one.
* min_age surfaced transparently when no age is supplied; enforced when supplied
  (8단's 만46세, 9단's 만65세).
* Shōgō prestige track: cross-track ``prereq_level_id`` (gates on dan levels),
  the 교사 OR-paths, and 범사's dual clock (8단 ≥8y AND 교사 ≥10y) + age ≥60.
* Reading tiers: current tier and count-to-next (count gate).
* Eligibility recomputes as the injected ``now`` advances — no stored bool.

Each test runs against its own freshly-migrated temp SQLite file with hand-built
``level`` / ``level_rule`` fixtures; ``DATABASE_PATH`` is pointed at it so the
service's ``db.connect()`` uses the test DB, never the dev DB. ``now`` is passed
explicitly so all time math is deterministic.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.services import progression

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point the service layer's connect() at it."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    return db_path


class Builder:
    """Tiny owner-scoped fixture builder writing straight to the temp DB."""

    def __init__(self, db_path: Path, owner_id: int) -> None:
        self.path = db_path
        self.owner_id = owner_id
        self.level_field_id: int | None = None
        self.result_field_id: int | None = None

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def sub_tally(self, *, mode: str = "progression", name: str = "Grading") -> int:
        c = self._conn()
        try:
            cat = c.execute(
                "INSERT INTO category (owner_id, name) VALUES (?, 'Kendo')",
                (self.owner_id,),
            ).lastrowid
            sid = c.execute(
                "INSERT INTO sub_tally (owner_id, category_id, name, count_mode)"
                " VALUES (?, ?, ?, ?)",
                (self.owner_id, cat, name, mode),
            ).lastrowid
            self.level_field_id = c.execute(
                "INSERT INTO field_def (sub_tally_id, kind, label) VALUES (?, 'level', '급/단')",
                (sid,),
            ).lastrowid
            self.result_field_id = c.execute(
                "INSERT INTO field_def (sub_tally_id, kind, label) VALUES (?, 'result', '합격')",
                (sid,),
            ).lastrowid
            return sid
        finally:
            c.close()

    def level(self, sid: int, *, track: str, ordinal: int, code: str, label: str) -> int:
        c = self._conn()
        try:
            return c.execute(
                "INSERT INTO level (sub_tally_id, owner_id, track, ordinal, code, label)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sid, self.owner_id, track, ordinal, code, label),
            ).lastrowid
        finally:
            c.close()

    def rule(
        self,
        sid: int,
        *,
        to_level_id: int,
        gate_type: str,
        from_level_id: int | None = None,
        gate_value: float | None = None,
        min_age: int | None = None,
        prereq_level_id: int | None = None,
    ) -> int:
        c = self._conn()
        try:
            return c.execute(
                "INSERT INTO level_rule (owner_id, sub_tally_id, from_level_id, to_level_id,"
                " gate_type, gate_value, min_age, prereq_level_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.owner_id,
                    sid,
                    from_level_id,
                    to_level_id,
                    gate_type,
                    gate_value,
                    min_age,
                    prereq_level_id,
                ),
            ).lastrowid
        finally:
            c.close()

    def level_entry(self, sid: int, *, code: str, occurred_at: datetime) -> int:
        return self._entry_value(sid, self.level_field_id, code, occurred_at)

    def result_entry(self, sid: int, *, value: str, occurred_at: datetime) -> int:
        return self._entry_value(sid, self.result_field_id, value, occurred_at)

    def plain_entry(self, sid: int, *, occurred_at: datetime) -> int:
        """An entry with no recorded level/result (e.g. a book read)."""
        c = self._conn()
        try:
            return c.execute(
                "INSERT INTO entry (owner_id, sub_tally_id, occurred_at) VALUES (?, ?, ?)",
                (self.owner_id, sid, occurred_at.isoformat()),
            ).lastrowid
        finally:
            c.close()

    def _entry_value(
        self, sid: int, field_def_id: int | None, text: str, occurred_at: datetime
    ) -> int:
        c = self._conn()
        try:
            eid = c.execute(
                "INSERT INTO entry (owner_id, sub_tally_id, occurred_at) VALUES (?, ?, ?)",
                (self.owner_id, sid, occurred_at.isoformat()),
            ).lastrowid
            c.execute(
                "INSERT INTO entry_value (entry_id, field_def_id, text_value) VALUES (?, ?, ?)",
                (eid, field_def_id, text),
            )
            return eid
        finally:
            c.close()


def _user(db_path: Path, provider: str = "email") -> int:
    c = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        return c.execute(
            "INSERT INTO user (auth_provider, display_name) VALUES (?, 'U')", (provider,)
        ).lastrowid
    finally:
        c.close()


def NOW(years: float = 0.0) -> datetime:  # noqa: N802 - reads as a clock constructor
    return datetime(2024, 1, 1, tzinfo=KST) + timedelta(days=years * 365.25)


# ---------------------------------------------------------------------------
# Gate types in isolation
# ---------------------------------------------------------------------------


def _track(status: dict, track: str) -> dict:
    return next(t for t in status["tracks"] if t["track"] == track)


def test_time_gate_not_eligible_then_eligible_as_now_advances(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    a = b.level(sid, track="dan", ordinal=1, code="a", label="A")
    bb = b.level(sid, track="dan", ordinal=2, code="b", label="B")
    b.rule(sid, from_level_id=a, to_level_id=bb, gate_type="time", gate_value=2.0)
    b.level_entry(sid, code="a", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    # 1 year after attaining A: not yet eligible for B (needs 2y).
    st = progression.status(sid, owner, now=NOW(1.0))
    dan = _track(st, "dan")
    assert dan["current_level"]["code"] == "a"
    assert dan["eligible"] is False
    assert dan["paths"][0]["gate"]["years_remaining"] == pytest.approx(1.0, abs=0.01)

    # 2 years after: eligible — recomputed purely from the advanced `now`, no
    # new entry and nothing stored.
    st2 = progression.status(sid, owner, now=NOW(2.0))
    assert _track(st2, "dan")["eligible"] is True


def test_count_gate_reports_remaining_and_flips(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally(name="Reading")
    t0 = b.level(sid, track="tier", ordinal=1, code="ibmun", label="입문")
    t1 = b.level(sid, track="tier", ordinal=2, code="chogup", label="초급")
    b.rule(sid, from_level_id=t0, to_level_id=t1, gate_type="count", gate_value=10)
    b.level_entry(sid, code="ibmun", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    # 4 more book entries (5 total): 5/10 → not eligible, 5 remaining.
    for _ in range(4):
        b.plain_entry(sid, occurred_at=datetime(2024, 2, 1, tzinfo=KST))
    st = progression.status(sid, owner, now=NOW(1.0))
    tier = _track(st, "tier")
    assert tier["current_level"]["code"] == "ibmun"
    gate = tier["paths"][0]["gate"]
    assert gate["current_count"] == 5
    assert gate["count_remaining"] == 5
    assert tier["eligible"] is False

    # Reach 10 → eligible.
    for _ in range(5):
        b.plain_entry(sid, occurred_at=datetime(2024, 3, 1, tzinfo=KST))
    st2 = progression.status(sid, owner, now=NOW(1.0))
    assert _track(st2, "tier")["eligible"] is True
    assert _track(st2, "tier")["paths"][0]["gate"]["count_remaining"] == 0


def test_event_gate_eligible_only_with_pass_after_current_level(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    a = b.level(sid, track="dan", ordinal=1, code="a", label="A")
    bb = b.level(sid, track="dan", ordinal=2, code="b", label="B")
    b.rule(sid, from_level_id=a, to_level_id=bb, gate_type="event")
    b.level_entry(sid, code="a", occurred_at=datetime(2024, 6, 1, tzinfo=KST))

    # A pass logged BEFORE holding A doesn't count.
    b.result_entry(sid, value="합격", occurred_at=datetime(2024, 1, 1, tzinfo=KST))
    st = progression.status(sid, owner, now=NOW(1.0))
    assert _track(st, "dan")["eligible"] is False

    # A pass at/after holding A counts.
    b.result_entry(sid, value="pass", occurred_at=datetime(2024, 7, 1, tzinfo=KST))
    st2 = progression.status(sid, owner, now=NOW(1.0))
    dan = _track(st2, "dan")
    assert dan["eligible"] is True
    assert dan["paths"][0]["gate"]["passing_attempts"] == 1


def test_manual_gate_always_declarable(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    a = b.level(sid, track="dan", ordinal=1, code="a", label="A")
    bb = b.level(sid, track="dan", ordinal=2, code="b", label="B")
    b.rule(sid, from_level_id=a, to_level_id=bb, gate_type="manual")
    b.level_entry(sid, code="a", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    st = progression.status(sid, owner, now=NOW(1.0))
    dan = _track(st, "dan")
    assert dan["eligible"] is True
    assert dan["paths"][0]["gate"]["declarable"] is True


# ---------------------------------------------------------------------------
# KKA dan ladder (realistic fixture)
# ---------------------------------------------------------------------------

# (from->to years, target min_age)
_DAN = [
    ("1gup", "chodan", 0.25, 13),
    ("chodan", "2dan", 1.0, None),
    ("2dan", "3dan", 2.0, 16),
    ("3dan", "4dan", 3.0, None),
    ("4dan", "5dan", 4.0, None),
    ("5dan", "6dan", 5.0, None),
    ("6dan", "7dan", 6.0, None),
    ("7dan", "8dan", 10.0, 46),
    ("8dan", "9dan", 10.0, 65),
]
_DAN_CODES = ["1gup", "chodan", "2dan", "3dan", "4dan", "5dan", "6dan", "7dan", "8dan", "9dan"]


def _seed_dan_ladder(b: Builder, sid: int) -> dict[str, int]:
    ids: dict[str, int] = {}
    for i, code in enumerate(_DAN_CODES, start=1):
        ids[code] = b.level(sid, track="dan", ordinal=i, code=code, label=code)
    for frm, to, years, min_age in _DAN:
        b.rule(
            sid,
            from_level_id=ids[frm],
            to_level_id=ids[to],
            gate_type="time",
            gate_value=years,
            min_age=min_age,
        )
    return ids


def test_dan_current_grade_and_time_in_grade(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_dan_ladder(b, sid)
    # Attained 4단 exactly 2 years before `now`.
    b.level_entry(sid, code="4dan", occurred_at=datetime(2022, 1, 1, tzinfo=KST))
    now = datetime(2024, 1, 1, tzinfo=KST)

    st = progression.status(sid, owner, now=now)
    dan = _track(st, "dan")
    assert dan["current_level"]["code"] == "4dan"
    assert dan["next_level"]["code"] == "5dan"
    gate = dan["paths"][0]["gate"]
    # ~2 years in grade.
    assert gate["years_held"] == pytest.approx(2.0, abs=0.02)
    # 5단 needs 4 years at 4단 → not eligible, ~2 years remaining.
    assert dan["eligible"] is False
    assert gate["years_remaining"] == pytest.approx(2.0, abs=0.02)


def test_dan_eligible_when_time_met(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_dan_ladder(b, sid)
    # Attained 4단 4+ years ago → eligible for 5단 (no age gate on 5단).
    b.level_entry(sid, code="4dan", occurred_at=datetime(2019, 1, 1, tzinfo=KST))
    now = datetime(2024, 1, 1, tzinfo=KST)

    dan = _track(progression.status(sid, owner, now=now), "dan")
    assert dan["eligible"] is True
    # Eligibility date is ~4 years after attainment.
    assert dan["paths"][0]["gate"]["eligible_at"].startswith("2023-01")


def test_dan_eligibility_date_countdown(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_dan_ladder(b, sid)
    # 초단 needs 0.25y (3 months) at 1급, plus 만13세.
    b.level_entry(sid, code="1gup", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    # 1 month in: not eligible.
    one_month = datetime(2024, 2, 1, tzinfo=KST)
    dan = _track(progression.status(sid, owner, age=20, now=one_month), "dan")
    assert dan["eligible"] is False

    # 4 months in + age known ≥13: eligible.
    four_months = datetime(2024, 5, 1, tzinfo=KST)
    dan2 = _track(progression.status(sid, owner, age=20, now=four_months), "dan")
    assert dan2["eligible"] is True


def test_dan_min_age_surfaced_when_age_unknown(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_dan_ladder(b, sid)
    # Attained 7단 long ago → time gate to 8단 (10y) is met, but 8단 needs 만46세.
    b.level_entry(sid, code="7dan", occurred_at=datetime(2000, 1, 1, tzinfo=KST))
    now = datetime(2024, 1, 1, tzinfo=KST)

    # Age unknown: requirement surfaced, NOT fabricated eligible.
    dan = _track(progression.status(sid, owner, age=None, now=now), "dan")
    assert dan["next_level"]["code"] == "8dan"
    assert dan["paths"][0]["gate"]["satisfied"] is True  # time clock met
    assert dan["paths"][0]["age"]["age_requirement"] == 46
    assert dan["paths"][0]["age"]["age_known"] is False
    assert dan["eligible"] is False  # never fabricate eligibility on unknown age

    # Age provided and below threshold: still not eligible.
    dan_young = _track(progression.status(sid, owner, age=40, now=now), "dan")
    assert dan_young["eligible"] is False

    # Age provided and at/above threshold: eligible.
    dan_ok = _track(progression.status(sid, owner, age=46, now=now), "dan")
    assert dan_ok["eligible"] is True
    assert dan_ok["paths"][0]["age"]["age_known"] is True


# ---------------------------------------------------------------------------
# Shōgō prestige track (cross-track prereq, OR-paths, dual clock + age)
# ---------------------------------------------------------------------------


def _seed_kendo_full(b: Builder, sid: int) -> dict[str, int]:
    """Dan ladder + shōgō track (연사/교사/범사) with KKA-shaped rules."""
    ids = _seed_dan_ladder(b, sid)
    ids["yeonsa"] = b.level(sid, track="shogo", ordinal=1, code="yeonsa", label="연사")
    ids["gyosa"] = b.level(sid, track="shogo", ordinal=2, code="gyosa", label="교사")
    ids["beomsa"] = b.level(sid, track="shogo", ordinal=3, code="beomsa", label="범사")

    # 연사: prereq 5단, 5단 held ≥3y.
    b.rule(
        sid,
        to_level_id=ids["yeonsa"],
        gate_type="time",
        gate_value=3.0,
        prereq_level_id=ids["5dan"],
    )
    # 교사 path 1: prereq 연사 (and implicitly 5단), 연사 held ≥7y.
    b.rule(
        sid,
        to_level_id=ids["gyosa"],
        gate_type="time",
        gate_value=7.0,
        prereq_level_id=ids["yeonsa"],
    )
    # 교사 path 2: prereq 6단 (must also hold 연사), 6단 held ≥4y.
    b.rule(
        sid,
        to_level_id=ids["gyosa"],
        gate_type="time",
        gate_value=4.0,
        prereq_level_id=ids["6dan"],
    )
    # 범사: prereq 8단 (+ 교사 by ordinal), 8단 ≥8y, 교사 ≥10y, age ≥60.
    # The from-level supplies the 교사≥10y clock; prereq supplies the 8단≥8y clock.
    b.rule(
        sid,
        from_level_id=ids["gyosa"],
        to_level_id=ids["beomsa"],
        gate_type="time",
        gate_value=10.0,
        min_age=60,
        prereq_level_id=ids["8dan"],
    )
    return ids


def test_shogo_yeonsa_requires_dan_prereq_cross_track(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_kendo_full(b, sid)

    # Hold only 4단 (not 5단): 연사 prereq unmet regardless of time.
    b.level_entry(sid, code="4dan", occurred_at=datetime(2000, 1, 1, tzinfo=KST))
    now = datetime(2024, 1, 1, tzinfo=KST)
    shogo = _track(progression.status(sid, owner, now=now), "shogo")
    assert shogo["next_level"]["code"] == "yeonsa"
    path = shogo["paths"][0]
    assert path["prerequisite"]["code"] == "5dan"
    assert path["prerequisite"]["held"] is False
    assert path["eligible"] is False

    # Hold 5단 for 3+ years → 연사 eligible (time clock runs from 5단 attainment).
    b.level_entry(sid, code="5dan", occurred_at=datetime(2020, 1, 1, tzinfo=KST))
    shogo2 = _track(progression.status(sid, owner, now=now), "shogo")
    assert shogo2["eligible"] is True


def test_shogo_gyosa_or_path_via_6dan(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_kendo_full(b, sid)
    now = datetime(2024, 1, 1, tzinfo=KST)

    # Hold 연사 only 2 years (path 1 fails: needs 7y) but hold 6단 5 years
    # (path 2 succeeds: needs 4y). Must also currently hold 연사.
    b.level_entry(sid, code="5dan", occurred_at=datetime(2010, 1, 1, tzinfo=KST))
    b.level_entry(sid, code="6dan", occurred_at=datetime(2019, 1, 1, tzinfo=KST))
    b.level_entry(sid, code="yeonsa", occurred_at=datetime(2022, 1, 1, tzinfo=KST))

    shogo = _track(progression.status(sid, owner, now=now), "shogo")
    assert shogo["current_level"]["code"] == "yeonsa"
    assert shogo["next_level"]["code"] == "gyosa"
    assert len(shogo["paths"]) == 2
    # The 연사-clock path is not satisfied; the 6단-clock path is.
    eligibles = [p["eligible"] for p in shogo["paths"]]
    assert eligibles.count(True) == 1
    assert shogo["eligible"] is True


def test_shogo_beomsa_dual_clock_and_age(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally()
    _seed_kendo_full(b, sid)
    now = datetime(2024, 1, 1, tzinfo=KST)

    # Hold 8단 for 9 years (≥8y ✓) and 교사 for 11 years (≥10y ✓), age 62 (≥60 ✓).
    b.level_entry(sid, code="8dan", occurred_at=datetime(2015, 1, 1, tzinfo=KST))
    b.level_entry(sid, code="gyosa", occurred_at=datetime(2013, 1, 1, tzinfo=KST))

    # Age unknown: the 60+ requirement is surfaced, eligibility NOT fabricated.
    shogo = _track(progression.status(sid, owner, age=None, now=now), "shogo")
    path = shogo["paths"][0]
    assert path["prerequisite"]["code"] == "8dan"
    assert path["prerequisite"]["held"] is True
    assert path["age"]["age_requirement"] == 60
    assert path["age"]["age_known"] is False
    assert shogo["eligible"] is False

    # Age 62: both clocks met + age ⇒ eligible.
    shogo_ok = _track(progression.status(sid, owner, age=62, now=now), "shogo")
    assert shogo_ok["eligible"] is True

    # Break the 교사 clock (only 5 years held): dual-clock fails even at age 62.
    b2 = Builder(test_db, _user(test_db))
    sid2 = b2.sub_tally()
    _seed_kendo_full(b2, sid2)
    b2.level_entry(sid2, code="8dan", occurred_at=datetime(2015, 1, 1, tzinfo=KST))
    b2.level_entry(sid2, code="gyosa", occurred_at=datetime(2020, 1, 1, tzinfo=KST))  # only 4y
    shogo_short = _track(progression.status(sid2, b2.owner_id, age=62, now=now), "shogo")
    assert shogo_short["eligible"] is False
    assert shogo_short["paths"][0]["gate"]["satisfied"] is False  # 교사 clock not met


# ---------------------------------------------------------------------------
# Reading tiers (count gate, full ladder)
# ---------------------------------------------------------------------------

_READING = [("ibmun", 1), ("chogup", 2), ("junggup", 3), ("gogup", 4), ("dain", 5)]
_READING_GATES = {"chogup": 10, "junggup": 25, "gogup": 50, "dain": 100}


def _seed_reading(b: Builder, sid: int) -> dict[str, int]:
    ids = {
        code: b.level(sid, track="tier", ordinal=o, code=code, label=code) for code, o in _READING
    }
    prev = "ibmun"
    for code in ["chogup", "junggup", "gogup", "dain"]:
        b.rule(
            sid,
            from_level_id=ids[prev],
            to_level_id=ids[code],
            gate_type="count",
            gate_value=_READING_GATES[code],
        )
        prev = code
    return ids


def test_reading_current_tier_and_count_to_next(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally(name="Reading")
    _seed_reading(b, sid)
    # Declared 초급 already; 30 books read total → between 중급(25) and 고급(50).
    b.level_entry(sid, code="ibmun", occurred_at=datetime(2024, 1, 1, tzinfo=KST))
    b.level_entry(sid, code="chogup", occurred_at=datetime(2024, 2, 1, tzinfo=KST))
    b.level_entry(sid, code="junggup", occurred_at=datetime(2024, 3, 1, tzinfo=KST))
    # 3 level entries already count as 3 books; add 27 plain entries → 30 total.
    for _ in range(27):
        b.plain_entry(sid, occurred_at=datetime(2024, 4, 1, tzinfo=KST))

    tier = _track(progression.status(sid, owner, now=NOW(1.0)), "tier")
    assert tier["current_level"]["code"] == "junggup"
    assert tier["next_level"]["code"] == "gogup"
    gate = tier["paths"][0]["gate"]
    assert gate["current_count"] == 30
    assert gate["required_count"] == 50
    assert gate["count_remaining"] == 20
    assert tier["eligible"] is False


# ---------------------------------------------------------------------------
# Batching + hero field + isolation
# ---------------------------------------------------------------------------


def test_batched_status_no_n_plus_1(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid1 = b.sub_tally()
    _seed_dan_ladder(b, sid1)
    b.level_entry(sid1, code="2dan", occurred_at=datetime(2024, 1, 1, tzinfo=KST))
    sid2 = b.sub_tally(name="Reading")
    _seed_reading(b, sid2)
    b.level_entry(sid2, code="chogup", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    out = progression.status_for_sub_tallies([sid1, sid2], owner, now=NOW(1.0))
    assert set(out) == {sid1, sid2}
    assert _track(out[sid1], "dan")["current_level"]["code"] == "2dan"
    assert _track(out[sid2], "tier")["current_level"]["code"] == "chogup"


def test_hero_field_progression_vs_running(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    prog = b.sub_tally()
    _seed_dan_ladder(b, prog)
    b.level_entry(prog, code="3dan", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    hero_prog = progression.hero_field(prog, owner)
    assert hero_prog["hero"] == "level"
    assert any(c["code"] == "3dan" for c in hero_prog["current_levels"])

    run = b.sub_tally(mode="running", name="Practice")
    b.plain_entry(run, occurred_at=datetime(2024, 1, 1, tzinfo=KST))
    # cached_count is maintained by entries.py; here it's 0 (we wrote raw), which
    # is fine — the hero CHOICE is what we assert, not the value.
    hero_run = progression.hero_field(run, owner)
    assert hero_run["hero"] == "count"


def test_status_is_owner_scoped(test_db: Path) -> None:
    owner_a = _user(test_db)
    owner_b = _user(test_db)
    ba = Builder(test_db, owner_a)
    sid = ba.sub_tally()
    _seed_dan_ladder(ba, sid)
    ba.level_entry(sid, code="3dan", occurred_at=datetime(2024, 1, 1, tzinfo=KST))

    # Owner B asking about owner A's sub_tally id sees nothing of A's.
    out = progression.status(sid, owner_b, now=NOW(1.0))
    assert out["tracks"] == []
    assert out["is_progression"] is False


def test_no_levels_is_not_progression(test_db: Path) -> None:
    owner = _user(test_db)
    b = Builder(test_db, owner)
    sid = b.sub_tally(mode="running", name="Practice")
    out = progression.status(sid, owner, now=NOW(1.0))
    assert out["is_progression"] is False
    assert out["tracks"] == []
