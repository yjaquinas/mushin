"""Tests for the renderer-agnostic stats service (Task 3).

Acceptance criteria covered
---------------------------
1. Each stat returns correct values against a fixture of known entries —
   including a streak across a gap, and week / month boundary cases evaluated in
   the caller-supplied timezone (these fixtures pass ``tz=KST`` = Asia/Seoul).
2. The heatmap returns a dense trailing-365-day series (every day present,
   zero-filled), keyed by the local day in the supplied timezone.

Determinism
-----------
Several stats anchor on "today" (current-period counts, trend, the heatmap
window). To make those assertions deterministic without a clock-freezing
dependency, we monkeypatch ``stats._today_local`` to a fixed day per test
(the patch ignores the passed tz and returns the frozen day). Period-
*independent* stats (lifetime, longest streak, scale distribution) use fixed
historical dates and don't need the anchor.

Each test runs against its own freshly-migrated temp SQLite file; ``DATABASE_PATH``
is pointed at it so the service's ``db.connect()`` uses the test DB (never the dev
DB). Entries are created through ``app.services.entries`` so the stats read the
same rows the rest of the app writes.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import db
from app.models.migrate import run_migrations
from app.services import entries, stats

# Existing fixtures use +09:00 offsets and assert on Asia/Seoul calendar buckets,
# so pass that zone explicitly to preserve their expected values. The
# America/Los_Angeles case below proves the tz parameter changes which calendar
# day/period an instant lands in.
KST = ZoneInfo("Asia/Seoul")
LA = ZoneInfo("America/Los_Angeles")

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point the service layer's connect() at it."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    return db_path


def _freeze_today(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    """Pin stats' notion of the current local day (ignores the passed tz)."""
    monkeypatch.setattr(stats, "_today_local", lambda _tz: day)


def _seed_user(db_path: Path, name: str = "U") -> int:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO user (auth_provider, display_name) VALUES ('email', ?)",
            (name,),
        )
        return cur.lastrowid
    finally:
        conn.close()


def _seed_activity(db_path: Path, owner_id: int, *, name: str = "Practice") -> dict[str, int]:
    """Category + activity + count / scale / tag_group field_defs + two tags."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, sort_order) VALUES (?, 'Kendo', 0)",
            (owner_id,),
        )
        category_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, 'running', 0)",
            (owner_id, category_id, name),
        )
        activity_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'count', 'Reps', 0)",
            (activity_id,),
        )
        count_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'scale', 'Mood', 1)",
            (activity_id,),
        )
        scale_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO field_def (activity_id, kind, label, sort_order)"
            " VALUES (?, 'tag_group', 'Tags', 2)",
            (activity_id,),
        )
        tag_group_fid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order) VALUES (?, ?, 'kata', 0)",
            (owner_id, tag_group_fid),
        )
        tag_kata = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO tag (owner_id, field_def_id, name, sort_order) VALUES (?, ?, 'shiai', 1)",
            (owner_id, tag_group_fid),
        )
        tag_shiai = cur.lastrowid
        return {
            "category_id": category_id,
            "activity_id": activity_id,
            "count_fid": count_fid,
            "scale_fid": scale_fid,
            "tag_group_fid": tag_group_fid,
            "tag_kata": tag_kata,
            "tag_shiai": tag_shiai,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Counts: week / month / year / lifetime / avg-per-week (KST)
# ---------------------------------------------------------------------------


def test_counts_kst_periods(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    # Anchor "today" at Wed 2026-06-10 (KST). ISO week starts Mon 2026-06-08.
    _freeze_today(monkeypatch, date(2026, 6, 10))

    # This week (Mon 06-08 .. today 06-10): two entries.
    entries.create(owner, st, {}, occurred_at="2026-06-08T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-10T09:00:00+09:00", tz=KST)
    # Earlier this month but last week (Sun 06-07).
    entries.create(owner, st, {}, occurred_at="2026-06-07T10:00:00+09:00", tz=KST)
    # Earlier this year, last month (May).
    entries.create(owner, st, {}, occurred_at="2026-05-20T10:00:00+09:00", tz=KST)
    # Last year — only counts toward lifetime.
    entries.create(owner, st, {}, occurred_at="2025-12-31T10:00:00+09:00", tz=KST)

    summary = stats.counts(st, owner, tz=KST)
    assert summary["this_week"] == 2
    assert summary["this_month"] == 3  # 06-07, 06-08, 06-10
    assert summary["this_year"] == 4  # all of 2026
    assert summary["lifetime"] == 5


def test_counts_week_boundary_kst_midnight(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An instant at 14:30Z on Sun is 23:30 KST Sun (last week); 15:30Z is 00:30
    KST Mon (this week). The UTC instants are 1h apart but land in different KST
    weeks."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    # 2026-06-07 is a Sunday (KST); 2026-06-08 a Monday → start of this week.
    _freeze_today(monkeypatch, date(2026, 6, 10))

    entries.create(owner, st, {}, occurred_at="2026-06-07T14:30:00+00:00", tz=KST)  # Sun 23:30 KST
    entries.create(owner, st, {}, occurred_at="2026-06-07T15:30:00+00:00", tz=KST)  # Mon 00:30 KST

    summary = stats.counts(st, owner, tz=KST)
    assert summary["this_week"] == 1  # only the Monday one


def test_counts_month_boundary_kst(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry at 2026-05-31T15:30:00Z is 2026-06-01 00:30 KST → June, not May."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    _freeze_today(monkeypatch, date(2026, 6, 15))

    entries.create(owner, st, {}, occurred_at="2026-05-31T15:30:00+00:00", tz=KST)  # 06-01 KST
    entries.create(owner, st, {}, occurred_at="2026-05-31T13:00:00+00:00", tz=KST)  # 05-31 22:00 KST

    summary = stats.counts(st, owner, tz=KST)
    assert summary["this_month"] == 1  # only the one that rolled into June KST


def test_period_bucketing_depends_on_caller_timezone(test_db: Path) -> None:
    """The same stored instant lands in a different calendar day depending on the
    supplied tz — proof the parameter selects the bucket, not a hardcoded zone.

    2026-06-01T05:30:00Z -> 2026-05-31 22:30 LA (PDT) but 2026-06-01 14:30 KST.

    Using ``heatmap_range`` (which buckets purely by local day, no "today"
    needed) over a window spanning both candidate days: in LA the entry sits in
    the 05-31 bucket; in KST it sits in the 06-01 bucket.
    """
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T05:30:00+00:00", tz=LA)

    la = {d["date"]: d["count"] for d in stats.heatmap_range(
        st, owner, date(2026, 5, 31), date(2026, 6, 1), tz=LA
    )}
    assert la["2026-05-31"] == 1
    assert la["2026-06-01"] == 0

    kst = {d["date"]: d["count"] for d in stats.heatmap_range(
        st, owner, date(2026, 5, 31), date(2026, 6, 1), tz=KST
    )}
    assert kst["2026-05-31"] == 0
    assert kst["2026-06-01"] == 1


def test_avg_per_week(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    # Today 2026-06-15; first entry 2026-06-01 → span 15 days inclusive → 15/7
    # weeks. 6 entries / (15/7) = 2.8.
    _freeze_today(monkeypatch, date(2026, 6, 15))
    for day in ("01", "02", "03", "08", "10", "15"):
        entries.create(owner, st, {}, occurred_at=f"2026-06-{day}T10:00:00+09:00", tz=KST)

    summary = stats.counts(st, owner, tz=KST)
    assert summary["lifetime"] == 6
    assert summary["avg_per_week"] == round(6 / (15 / 7.0), 2)  # 2.8


# ---------------------------------------------------------------------------
# Batched counts (no N+1)
# ---------------------------------------------------------------------------


def test_counts_for_sub_tallies_batched(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    a = _seed_activity(test_db, owner, name="A")
    b = _seed_activity(test_db, owner, name="B")
    c = _seed_activity(test_db, owner, name="C")  # no entries
    _freeze_today(monkeypatch, date(2026, 6, 10))

    entries.create(owner, a["activity_id"], {}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)
    entries.create(owner, a["activity_id"], {}, occurred_at="2026-06-09T10:00:00+09:00", tz=KST)
    entries.create(owner, b["activity_id"], {}, occurred_at="2026-06-08T10:00:00+09:00", tz=KST)

    ids = [a["activity_id"], b["activity_id"], c["activity_id"]]
    result = stats.counts_for_sub_tallies(ids, owner, tz=KST)

    assert set(result) == set(ids)  # every requested id present
    assert result[a["activity_id"]]["lifetime"] == 2
    assert result[b["activity_id"]]["lifetime"] == 1
    assert result[c["activity_id"]]["lifetime"] == 0  # zeroed, not missing
    assert result[c["activity_id"]]["avg_per_week"] == 0.0


def test_counts_for_sub_tallies_isolated(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")
    entries.create(a, ids_a["activity_id"], {}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)

    # B requests A's activity id → batched query is owner-scoped, returns zero.
    result = stats.counts_for_sub_tallies([ids_a["activity_id"]], b, tz=KST)
    assert result[ids_a["activity_id"]]["lifetime"] == 0


# ---------------------------------------------------------------------------
# Streaks: current + longest, with a gap
# ---------------------------------------------------------------------------


def test_streaks_current_and_longest_with_gap(test_db: Path) -> None:
    """Two runs separated by a gap: a longer earlier run sets ``longest`` while a
    shorter recent run sets ``current``.

    Earlier run: 2026-03-01..03-05 (5 days). Gap. Recent run: 2026-06-08..06-10
    (3 days). current = 3, longest = 5.
    """
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    for day in ("01", "02", "03", "04", "05"):
        entries.create(owner, st, {}, occurred_at=f"2026-03-{day}T10:00:00+09:00", tz=KST)
    for day in ("08", "09", "10"):
        entries.create(owner, st, {}, occurred_at=f"2026-06-{day}T10:00:00+09:00", tz=KST)

    s = stats.streaks(st, owner, tz=KST)
    assert s["current"] == 3
    assert s["longest"] == 5


def test_streaks_current_matches_cached_streak(test_db: Path) -> None:
    """stats.streaks()['current'] must equal entries.py's cached_streak (same KST
    rule, derived from stored timestamps)."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-01T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-02T22:00:00+09:00", tz=KST)  # same day
    entries.create(owner, st, {}, occurred_at="2020-01-01T10:00:00+09:00", tz=KST)  # old gap

    cached = entries.recompute(st, owner, tz=KST)["cached_streak"]
    assert stats.streaks(st, owner, tz=KST)["current"] == cached == 2


def test_streaks_empty(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    s = stats.streaks(ids["activity_id"], owner, tz=KST)
    assert s == {"current": 0, "longest": 0}


# ---------------------------------------------------------------------------
# Heatmap: dense trailing-365-day series, zero-filled, keyed by KST day
# ---------------------------------------------------------------------------


def test_heatmap_dense_and_zero_filled(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    today = date(2026, 6, 10)
    _freeze_today(monkeypatch, today)

    # Two entries today (same KST day → bucket count 2), one yesterday, one a year
    # ago (just inside the window: start = today - 364 days = 2025-06-11).
    entries.create(owner, st, {}, occurred_at="2026-06-10T09:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-10T21:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-09T12:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2025-06-11T12:00:00+09:00", tz=KST)  # window start
    # Outside the window (one day before start) → excluded.
    entries.create(owner, st, {}, occurred_at="2025-06-10T12:00:00+09:00", tz=KST)

    series = stats.heatmap(st, owner, tz=KST)

    # Dense: exactly 365 buckets, one per day, oldest first, contiguous.
    assert len(series) == 365
    assert series[0]["date"] == "2025-06-11"
    assert series[-1]["date"] == "2026-06-10"
    days = [d["date"] for d in series]
    assert days == sorted(days)
    assert len(set(days)) == 365  # no duplicate/missing days

    by_date = {d["date"]: d["count"] for d in series}
    assert by_date["2026-06-10"] == 2  # two same-day entries collapse into one bucket count
    assert by_date["2026-06-09"] == 1
    assert by_date["2025-06-11"] == 1  # exactly on the window start
    assert "2025-06-10" not in by_date  # outside window
    # A day with no entries is present and zero-filled.
    assert by_date["2026-01-01"] == 0


def test_heatmap_keyed_by_kst_day(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry at 2026-06-09T15:30:00Z is 2026-06-10 00:30 KST → it lands in the
    06-10 bucket, not 06-09."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    _freeze_today(monkeypatch, date(2026, 6, 10))
    entries.create(owner, st, {}, occurred_at="2026-06-09T15:30:00+00:00", tz=KST)

    by_date = {d["date"]: d["count"] for d in stats.heatmap(st, owner, tz=KST)}
    assert by_date["2026-06-10"] == 1
    assert by_date["2026-06-09"] == 0


# ---------------------------------------------------------------------------
# Tag-group frequency + trend
# ---------------------------------------------------------------------------


def test_tag_frequency_and_trend(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]
    fid = ids["tag_group_fid"]
    kata, shiai = ids["tag_kata"], ids["tag_shiai"]

    # Anchor in June 2026. This month = June, last month = May.
    _freeze_today(monkeypatch, date(2026, 6, 15))

    # June (this period): kata x2, shiai x1.
    entries.create(owner, st, {"tags": [kata]}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [kata]}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [shiai]}, occurred_at="2026-06-12T10:00:00+09:00", tz=KST)
    # May (last period): kata x1, shiai x2.
    entries.create(owner, st, {"tags": [kata]}, occurred_at="2026-05-05T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [shiai]}, occurred_at="2026-05-06T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [shiai]}, occurred_at="2026-05-07T10:00:00+09:00", tz=KST)
    # April (neither period): kata x1 → counts only toward lifetime total.
    entries.create(owner, st, {"tags": [kata]}, occurred_at="2026-04-01T10:00:00+09:00", tz=KST)

    result = stats.tag_frequency(st, owner, fid, period="month", tz=KST)
    by_tag = {t["tag_id"]: t for t in result["tags"]}

    assert by_tag[kata]["total"] == 4  # 2 June + 1 May + 1 April
    assert by_tag[kata]["this_period"] == 2
    assert by_tag[kata]["last_period"] == 1
    assert by_tag[kata]["delta"] == 1

    assert by_tag[shiai]["total"] == 3
    assert by_tag[shiai]["this_period"] == 1
    assert by_tag[shiai]["last_period"] == 2
    assert by_tag[shiai]["delta"] == -1

    # Sorted by lifetime total desc → kata (4) before shiai (3).
    assert [t["tag_id"] for t in result["tags"]] == [kata, shiai]


def test_tag_frequency_top_n(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st, fid = ids["activity_id"], ids["tag_group_fid"]
    entries.create(owner, st, {"tags": [ids["tag_kata"]]}, occurred_at="2026-01-01T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [ids["tag_kata"]]}, occurred_at="2026-01-02T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"tags": [ids["tag_shiai"]]}, occurred_at="2026-01-03T10:00:00+09:00", tz=KST)

    result = stats.tag_frequency(st, owner, fid, top=1, tz=KST)
    assert len(result["tags"]) == 1
    assert result["tags"][0]["tag_id"] == ids["tag_kata"]


def test_tag_frequency_rejects_wrong_kind(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    with pytest.raises(stats.FieldKindError):
        stats.tag_frequency(ids["activity_id"], owner, ids["count_fid"], tz=KST)


# ---------------------------------------------------------------------------
# Scale distribution
# ---------------------------------------------------------------------------


def test_scale_distribution(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st, fid = ids["activity_id"], ids["scale_fid"]

    # Values: 5, 5, 3, 4 → distribution {3:1, 4:1, 5:2}, avg 4.25, count 4.
    for day, val in (("01", 5), ("02", 5), ("03", 3), ("04", 4)):
        entries.create(
            owner, st, {"values": {fid: val}}, occurred_at=f"2026-01-{day}T10:00:00+09:00", tz=KST
        )

    result = stats.scale_distribution(st, owner, fid)
    assert result["count"] == 4
    assert result["average"] == 4.25
    assert result["distribution"] == [
        {"value": 3.0, "count": 1},
        {"value": 4.0, "count": 1},
        {"value": 5.0, "count": 2},
    ]


def test_scale_distribution_empty(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    result = stats.scale_distribution(ids["activity_id"], owner, ids["scale_fid"])
    assert result == {"distribution": [], "count": 0, "average": None}


def test_scale_distribution_rejects_wrong_kind(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    with pytest.raises(stats.FieldKindError):
        stats.scale_distribution(ids["activity_id"], owner, ids["count_fid"])


# ---------------------------------------------------------------------------
# Count totals + trend
# ---------------------------------------------------------------------------


def test_count_totals_and_trend(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st, fid = ids["activity_id"], ids["count_fid"]

    _freeze_today(monkeypatch, date(2026, 6, 15))

    # June (this period): 30 + 20 = 50.
    entries.create(owner, st, {"values": {fid: 30}}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {"values": {fid: 20}}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)
    # May (last period): 40.
    entries.create(owner, st, {"values": {fid: 40}}, occurred_at="2026-05-05T10:00:00+09:00", tz=KST)
    # April: 10 → lifetime only.
    entries.create(owner, st, {"values": {fid: 10}}, occurred_at="2026-04-01T10:00:00+09:00", tz=KST)

    result = stats.count_totals(st, owner, fid, period="month", tz=KST)
    assert result["lifetime"] == 100.0
    assert result["this_period"] == 50.0
    assert result["last_period"] == 40.0
    assert result["delta"] == 10.0
    assert result["entries"] == 4


def test_count_totals_rejects_wrong_kind(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    with pytest.raises(stats.FieldKindError):
        stats.count_totals(ids["activity_id"], owner, ids["scale_fid"], tz=KST)


def test_count_totals_isolated_between_users(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")
    entries.create(
        a,
        ids_a["activity_id"],
        {"values": {ids_a["count_fid"]: 30}},
        occurred_at="2026-06-01T10:00:00+09:00",
        tz=KST,
    )

    # B asking about A's field raises (not owned by B) — no cross-tenant read.
    with pytest.raises(stats.FieldNotFoundError):
        stats.count_totals(ids_a["activity_id"], b, ids_a["count_fid"], tz=KST)


# ---------------------------------------------------------------------------
# _shift_period: period start n steps from the period containing an anchor
# ---------------------------------------------------------------------------


def test_shift_period_week_normalizes_and_steps() -> None:
    # Wed 2026-06-10 → ISO week starts Mon 2026-06-08.
    anchor = date(2026, 6, 10)
    assert stats._shift_period(anchor, "week", 0) == date(2026, 6, 8)
    assert stats._shift_period(anchor, "week", 1) == date(2026, 6, 15)
    assert stats._shift_period(anchor, "week", -1) == date(2026, 6, 1)


def test_shift_period_month_crosses_year_boundary() -> None:
    # Forward across Dec → Jan.
    assert stats._shift_period(date(2026, 12, 15), "month", 1) == date(2027, 1, 1)
    # Backward across Jan → Dec.
    assert stats._shift_period(date(2026, 1, 15), "month", -1) == date(2025, 12, 1)
    # Multi-step backward.
    assert stats._shift_period(date(2026, 3, 31), "month", -5) == date(2025, 10, 1)
    # Zero step normalizes to the 1st.
    assert stats._shift_period(date(2026, 6, 30), "month", 0) == date(2026, 6, 1)


def test_shift_period_year_steps_and_normalizes() -> None:
    assert stats._shift_period(date(2026, 6, 10), "year", 0) == date(2026, 1, 1)
    assert stats._shift_period(date(2026, 6, 10), "year", 1) == date(2027, 1, 1)
    assert stats._shift_period(date(2026, 6, 10), "year", -3) == date(2023, 1, 1)


def test_shift_period_leap_year() -> None:
    # _year_start always lands on Jan 1, so year stepping is leap-safe.
    assert stats._shift_period(date(2024, 2, 29), "year", 1) == date(2025, 1, 1)
    # _add_year clamps Feb 29 → Feb 28 directly (exercise the helper).
    assert stats._add_year(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert stats._add_year(date(2024, 2, 29), 4) == date(2028, 2, 29)  # target is leap


def test_shift_period_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        stats._shift_period(date(2026, 6, 10), "decade", 1)


# ---------------------------------------------------------------------------
# heatmap_range: dense, zero-filled over an arbitrary [start, end]
# ---------------------------------------------------------------------------


def test_heatmap_range_arbitrary_window(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    entries.create(owner, st, {}, occurred_at="2026-06-08T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-08T21:00:00+09:00", tz=KST)  # same day → 2
    entries.create(owner, st, {}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)
    # Outside the [06-08, 06-10] window → excluded.
    entries.create(owner, st, {}, occurred_at="2026-06-11T10:00:00+09:00", tz=KST)

    series = stats.heatmap_range(st, owner, date(2026, 6, 8), date(2026, 6, 10), tz=KST)
    assert [d["date"] for d in series] == ["2026-06-08", "2026-06-09", "2026-06-10"]
    by_date = {d["date"]: d["count"] for d in series}
    assert by_date["2026-06-08"] == 2
    assert by_date["2026-06-09"] == 0  # zero-filled
    assert by_date["2026-06-10"] == 1
    assert "2026-06-11" not in by_date


def test_heatmap_range_single_day(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]
    entries.create(owner, st, {}, occurred_at="2026-06-10T10:00:00+09:00", tz=KST)

    series = stats.heatmap_range(st, owner, date(2026, 6, 10), date(2026, 6, 10), tz=KST)
    assert series == [{"date": "2026-06-10", "count": 1}]


def test_heatmap_range_multi_year(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    start, end = date(2024, 1, 1), date(2026, 6, 11)
    expected_len = (end - start).days + 1
    series = stats.heatmap_range(st, owner, start, end, tz=KST)
    assert len(series) == expected_len
    assert series[0]["date"] == "2024-01-01"
    assert series[-1]["date"] == "2026-06-11"
    days = [d["date"] for d in series]
    assert days == sorted(days)
    assert len(set(days)) == expected_len  # contiguous, no gaps/dupes
    # Feb 29 2024 is present (leap day inside the range).
    assert {d["date"]: d["count"] for d in series}["2024-02-29"] == 0


def test_heatmap_range_empty_when_end_before_start(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    series = stats.heatmap_range(ids["activity_id"], owner, date(2026, 6, 10), date(2026, 6, 9), tz=KST)
    assert series == []


# ---------------------------------------------------------------------------
# card_stats: counts + streaks + heatmap from one consolidated read
# ---------------------------------------------------------------------------


def test_card_stats_counts_and_streaks_match_separate_calls(
    test_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """card_stats()'s counts/streaks must be byte-for-byte equivalent to calling
    counts() and streaks() separately on the same data."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    _freeze_today(monkeypatch, date(2026, 6, 10))

    # Entries spread across several days, including a current run, an earlier
    # longer run (gap), a same-day collapse, and one in a prior year.
    for day in ("08", "09", "10"):  # current run of 3
        entries.create(owner, st, {}, occurred_at=f"2026-06-{day}T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-10T21:00:00+09:00", tz=KST)  # same-day
    for day in ("01", "02", "03", "04"):  # earlier run of 4 (this month)
        entries.create(owner, st, {}, occurred_at=f"2026-05-{day}T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2025-06-10T10:00:00+09:00", tz=KST)  # last year

    card = stats.card_stats(st, owner, tz=KST)

    assert card["counts"] == stats.counts(st, owner, tz=KST)
    assert card["streaks"] == stats.streaks(st, owner, tz=KST)


def test_card_stats_weekly_intensity_is_distinct_active_days(
    test_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each weekly bucket's intensity is the count of distinct days in that ISO
    week with at least one entry — same-day entries collapse to one, multiple
    distinct days in a week add up, and intensity never exceeds 7.

    Fixture (KST), expected per-week intensity computed by hand below:
      - ISO week of Mon 2026-06-08: entries on Mon 06-08 (x2, same day) and
        Wed 06-10 → 2 distinct active days.
      - ISO week of Mon 2026-06-01: entries on Tue 06-02 and Fri 06-05 → 2
        distinct active days.
      - ISO week of Mon 2026-05-25: a single entry on Wed 05-27 → 1 active day.
      - ISO week of Mon 2026-05-18: no entries → 0.
    """
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    # Anchor today inside the week of Mon 2026-06-08 (Wed 06-10).
    _freeze_today(monkeypatch, date(2026, 6, 10))

    # Week of 06-08: two entries same day (06-08), plus 06-10 → 2 distinct days.
    entries.create(owner, st, {}, occurred_at="2026-06-08T08:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-08T21:00:00+09:00", tz=KST)  # same day
    entries.create(owner, st, {}, occurred_at="2026-06-10T09:00:00+09:00", tz=KST)
    # Week of 06-01: 06-02 and 06-05 → 2 distinct days.
    entries.create(owner, st, {}, occurred_at="2026-06-02T10:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-05T10:00:00+09:00", tz=KST)
    # Week of 05-25: only 05-27 → 1 distinct day.
    entries.create(owner, st, {}, occurred_at="2026-05-27T10:00:00+09:00", tz=KST)

    series = stats.card_stats(st, owner, tz=KST)["heatmap"]
    by_week = {b["week_start"]: b["intensity"] for b in series}

    assert by_week["2026-06-08"] == 2
    assert by_week["2026-06-01"] == 2
    assert by_week["2026-05-25"] == 1
    assert by_week["2026-05-18"] == 0
    # Intensity is bounded 0..7 regardless of entry count (same-day collapse).
    assert all(0 <= b["intensity"] <= 7 for b in series)


def test_card_stats_default_heatmap_window(test_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The heatmap covers the current calendar year as contiguous
    Monday-anchored weekly buckets, oldest-first — from the week containing
    Jan 1 through the week containing Dec 31, a fixed-length series regardless
    of the current date (future weeks are zero-filled, not omitted, so the
    card's height never changes as the year progresses). Quarter labels land
    on exactly the one week containing each of Jan/Apr/Jul/Oct's 1st."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    today = date(2026, 6, 10)  # well inside the year, not at either boundary
    _freeze_today(monkeypatch, today)
    entries.create(owner, st, {}, occurred_at="2026-06-10T09:00:00+09:00", tz=KST)

    series = stats.card_stats(st, owner, tz=KST)["heatmap"]

    jan1, dec31 = date(2026, 1, 1), date(2026, 12, 31)
    expected_start = jan1 - timedelta(days=jan1.weekday())
    expected_end = dec31 - timedelta(days=dec31.weekday())
    expected_weeks = (expected_end - expected_start).days // 7 + 1

    assert len(series) == expected_weeks
    assert series[0]["week_start"] == expected_start.isoformat()
    assert series[-1]["week_start"] == expected_end.isoformat()

    weeks = [date.fromisoformat(b["week_start"]) for b in series]
    assert all(w.weekday() == 0 for w in weeks)  # every week_start is a Monday
    assert weeks == sorted(weeks)
    assert len(set(weeks)) == expected_weeks  # contiguous, no gaps/dupes
    assert all(
        (later - earlier).days == 7 for earlier, later in zip(weeks, weeks[1:], strict=False)
    )

    by_week = {b["week_start"]: b["intensity"] for b in series}
    assert by_week["2026-06-08"] == 1  # the lone 06-10 entry's week (Monday-anchored)

    # The series extends past "today" into the future, zero-filled, not omitted.
    future_weeks = [b for b in series if date.fromisoformat(b["week_start"]) > today]
    assert future_weeks
    assert all(b["intensity"] == 0 for b in future_weeks)

    # Quarter labels: exactly one labeled week per quarter-start month.
    labeled = {b["week_start"]: b["quarter_month"] for b in series if b["quarter_month"]}
    assert len(labeled) == 4
    for month in (1, 4, 7, 10):
        qd = date(2026, month, 1)
        matches = [
            ws
            for ws in labeled
            if date.fromisoformat(ws) <= qd <= date.fromisoformat(ws) + timedelta(days=6)
        ]
        assert matches == [k for k in labeled if labeled[k] == month]
        assert len(matches) == 1


def test_card_stats_heatmap_anchors_on_current_year(
    test_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The heatmap's year follows the caller's *current* local year, not a
    trailing window — an entry from the prior year falls outside the series."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    _freeze_today(monkeypatch, date(2027, 1, 2))  # early in the new year
    entries.create(owner, st, {}, occurred_at="2027-01-02T09:00:00+09:00", tz=KST)
    entries.create(owner, st, {}, occurred_at="2026-06-10T09:00:00+09:00", tz=KST)  # prior year

    series = stats.card_stats(st, owner, tz=KST)["heatmap"]

    jan1_2027 = date(2027, 1, 1)
    expected_start = jan1_2027 - timedelta(days=jan1_2027.weekday())
    assert series[0]["week_start"] == expected_start.isoformat()
    assert all(date.fromisoformat(b["week_start"]) >= expected_start for b in series)

    total_intensity = sum(b["intensity"] for b in series)
    assert total_intensity == 1  # only the 2027-01-02 entry's week counts


# ---------------------------------------------------------------------------
# period_entries: hydrated entries in [start, end], newest-first, owner-scoped
# ---------------------------------------------------------------------------


def test_period_entries_filters_and_orders(test_db: Path) -> None:
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    e_before = entries.create(owner, st, {}, occurred_at="2026-06-07T10:00:00+09:00", tz=KST)
    e_mid = entries.create(owner, st, {}, occurred_at="2026-06-08T10:00:00+09:00", tz=KST)
    e_late = entries.create(owner, st, {}, occurred_at="2026-06-10T21:00:00+09:00", tz=KST)
    e_after = entries.create(owner, st, {}, occurred_at="2026-06-11T10:00:00+09:00", tz=KST)

    result = stats.period_entries(st, owner, date(2026, 6, 8), date(2026, 6, 10), tz=KST)
    got_ids = [r["id"] for r in result]

    # Only the in-window entries, newest-first.
    assert got_ids == [e_late["id"], e_mid["id"]]
    assert e_before["id"] not in got_ids
    assert e_after["id"] not in got_ids
    # Hydrated dicts (carry the entry shape, not bare rows).
    assert "values" in result[0] and "tags" in result[0]


def test_period_entries_kst_boundary(test_db: Path) -> None:
    """An entry at 2026-06-07T15:30:00Z is 2026-06-08 00:30 KST → inside a window
    that starts 06-08, even though the UTC instant is on 06-07."""
    owner = _seed_user(test_db)
    ids = _seed_activity(test_db, owner)
    st = ids["activity_id"]

    e = entries.create(owner, st, {}, occurred_at="2026-06-07T15:30:00+00:00", tz=KST)
    result = stats.period_entries(st, owner, date(2026, 6, 8), date(2026, 6, 8), tz=KST)
    assert [r["id"] for r in result] == [e["id"]]


def test_period_entries_owner_scoped(test_db: Path) -> None:
    a = _seed_user(test_db, name="A")
    b = _seed_user(test_db, name="B")
    ids_a = _seed_activity(test_db, a, name="A-st")
    entries.create(a, ids_a["activity_id"], {}, occurred_at="2026-06-08T10:00:00+09:00", tz=KST)

    # B querying A's activity id gets nothing (list_for_activity is owner-scoped).
    result = stats.period_entries(ids_a["activity_id"], b, date(2026, 6, 1), date(2026, 6, 30), tz=KST)
    assert result == []
