"""Integration tests for the web (HTMX) routes (Task 6).

Covers:

1. The logged-out entry screen (``GET /``) renders the 無心 gloss, the
   "그냥 시작하기" guest CTA, and the "계정 없이, 나만 보는 기록" framing — and
   never claims data stays only on-device (guest data lives on the server).
2. The guest flow: ``POST /auth/guest`` mints a session, and ``GET /home``
   then renders activity cards for the seeded 검도 + 독서 starter templates.
3. ``POST /sub-tallies/{id}/log`` under ``HX-Request: true`` returns an HTMX
   fragment (not a full document) and increments the sub-tally's count.
4. A strings-centralization guard scanning ``app/templates/**`` for hardcoded
   user-facing Korean text.

Setup mirrors ``tests/integration/test_auth.py``: a fresh migrated temp SQLite
DB per test, ``SESSION_SECRET`` set, and an HTTPS base URL so the ``Secure``
session cookie round-trips through httpx's cookie jar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import ui_strings as strings_module
from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import competition, seeding, stats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def web_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(web_db: Path) -> AsyncClient:
    """Async client with an HTTPS base URL so the Secure session cookie persists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


async def _guest_login(client: AsyncClient) -> int:
    """Mint a guest session and return its owner_id (user id)."""
    resp = await client.post("/auth/guest")
    assert resp.status_code == 200
    return int(resp.json()["user_id"])


# ---------------------------------------------------------------------------
# Entry screen (logged out)
# ---------------------------------------------------------------------------


async def test_entry_screen_renders_for_logged_out_client(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "無心" in resp.text
    assert "그냥 시작하기" in resp.text
    assert "계정 없이, 나만 보는 기록" in resp.text


async def test_entry_screen_does_not_claim_device_only_storage(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    # Guest data lives on the server, not on-device — never imply otherwise.
    assert "기기에만" not in resp.text
    assert "기기에서만" not in resp.text


async def test_entry_screen_consent_line_links_to_privacy_policy(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text
    assert "개인정보처리방침" in resp.text


# ---------------------------------------------------------------------------
# Privacy policy page (logged out)
# ---------------------------------------------------------------------------


async def test_privacy_policy_renders_for_logged_out_client(client: AsyncClient) -> None:
    resp = await client.get("/privacy")
    assert resp.status_code == 200
    assert "개인정보처리방침" in resp.text
    assert "제11조" in resp.text
    assert "2026.06.11" in resp.text
    assert "mushin@aqnas.xyz" in resp.text


async def test_privacy_policy_excludes_internal_meta_content(client: AsyncClient) -> None:
    resp = await client.get("/privacy")
    assert resp.status_code == 200
    assert "초안(DRAFT)" not in resp.text
    assert "검토를 받으시기를 권장" not in resp.text


async def test_footer_privacy_link_present_on_entry_and_home(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text

    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text


# ---------------------------------------------------------------------------
# Guest flow -> home renders seeded templates
# ---------------------------------------------------------------------------


async def test_guest_home_renders_seeded_starter_templates(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)

    # The guest path lazy-seeds on first *entry*, not on guest creation — seed
    # explicitly here so /home has cards to render.
    seeding.seed_account(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert "검도" in resp.text
    assert "독서" in resp.text


async def test_home_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Log -> fragment swap, count increments
# ---------------------------------------------------------------------------


async def test_log_returns_fragment_and_increments_count(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_tally_id = conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '수련'""",
            (owner_id,),
        ).fetchone()["id"]

    before = stats.counts(sub_tally_id, owner_id)

    resp = await client.post(
        f"/sub-tallies/{sub_tally_id}/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    # A fragment, not a full document.
    assert "<!DOCTYPE html>" not in resp.text
    assert "<html" not in resp.text

    after = stats.counts(sub_tally_id, owner_id)
    assert after["lifetime"] == before["lifetime"] + 1


async def test_log_unknown_sub_tally_returns_404(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.post(
        "/sub-tallies/999999/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Match-list sub-form (tournament entries) + competition stats (Task 8)
# ---------------------------------------------------------------------------


def _tournament_ids(owner_id: int) -> tuple[int, int]:
    """(sub_tally_id, match_list field_def_id) for the seeded 검도/시합 tournament."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_tally_id = conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '시합'""",
            (owner_id,),
        ).fetchone()["id"]
        field_def_id = conn.execute(
            "SELECT id FROM field_def WHERE sub_tally_id = ? AND kind = 'match_list'",
            (sub_tally_id,),
        ).fetchone()["id"]
    return sub_tally_id, field_def_id


async def test_log_sheet_renders_match_sub_form_for_tournament(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.get(
        f"/sub-tallies/{sub_tally_id}/log",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert f"match_opponent_{field_def_id}_0" in resp.text
    assert f"match_score_{field_def_id}_0" in resp.text
    assert f"match_result_{field_def_id}_0" in resp.text


async def test_log_sheet_does_not_render_match_sub_form_for_non_tournament(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_tally_id = conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '수련'""",
            (owner_id,),
        ).fetchone()["id"]

    resp = await client.get(
        f"/sub-tallies/{sub_tally_id}/log",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "match_opponent_" not in resp.text


async def test_add_match_row_appends_row_preserving_existing_values(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/sub-tallies/{sub_tally_id}/match-rows/{field_def_id}/add",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Existing row's value survives the swap.
    assert 'value="김철수"' in resp.text
    # A second, empty row was appended.
    assert f"match_opponent_{field_def_id}_1" in resp.text


async def test_remove_match_row_drops_the_requested_row(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/sub-tallies/{sub_tally_id}/match-rows/{field_def_id}/remove/0",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
            f"match_opponent_{field_def_id}_1": "박영희",
            f"match_score_{field_def_id}_1": "1-0",
            f"match_result_{field_def_id}_1": "loss",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Row 0 (김철수) was removed; the remaining row is renumbered to index 0.
    assert "김철수" not in resp.text
    assert 'value="박영희"' in resp.text
    assert f"match_opponent_{field_def_id}_0" in resp.text
    assert f"match_opponent_{field_def_id}_1" not in resp.text


async def test_submitting_tournament_entry_persists_match_rows(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/sub-tallies/{sub_tally_id}/log",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
            f"match_opponent_{field_def_id}_1": "박영희",
            f"match_score_{field_def_id}_1": "0-2",
            f"match_result_{field_def_id}_1": "loss",
            f"match_opponent_{field_def_id}_2": "이민수",
            f"match_score_{field_def_id}_2": "1-1",
            f"match_result_{field_def_id}_2": "draw",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND sub_tally_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, sub_tally_id),
        ).fetchone()["id"]

    matches = competition.list_matches(owner_id, entry_id)
    assert len(matches) == 3
    assert {m["opponent"] for m in matches} == {"김철수", "박영희", "이민수"}
    assert {m["result"] for m in matches} == {"win", "loss", "draw"}

    record = competition.record(owner_id, sub_tally_id)
    assert record["wins"] == 1
    assert record["losses"] == 1
    assert record["draws"] == 1
    assert record["decided"] == 3
    assert record["win_rate"] == pytest.approx(1 / 3)


async def test_submitting_tournament_entry_drops_incomplete_rows(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/sub-tallies/{sub_tally_id}/log",
        data={
            f"match_opponent_{field_def_id}_0": "",
            f"match_score_{field_def_id}_0": "",
            f"match_result_{field_def_id}_0": "",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND sub_tally_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, sub_tally_id),
        ).fetchone()["id"]

    assert competition.list_matches(owner_id, entry_id) == []


# ---------------------------------------------------------------------------
# Sub-tally detail screen + competition stats
# ---------------------------------------------------------------------------


async def test_detail_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/sub-tallies/1", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_detail_unknown_sub_tally_returns_404(client: AsyncClient) -> None:
    await _guest_login(client)
    resp = await client.get("/sub-tallies/999999")
    assert resp.status_code == 404


async def test_non_tournament_detail_has_no_competition_stats(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_tally_id = conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '수련'""",
            (owner_id,),
        ).fetchone()["id"]

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_TITLE not in resp.text


async def test_tournament_detail_shows_record_and_head_to_head(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, _field_def_id = _tournament_ids(owner_id)

    # Build a fixture: two outings, three bouts total against two opponents.
    from app.services import entries as entries_service

    entry_a = entries_service.create(owner_id, sub_tally_id, {})
    competition.add_matches(
        owner_id,
        entry_a["id"],
        [
            {"opponent": "김철수", "score": "2-1", "result": "win"},
            {"opponent": "박영희", "score": "0-2", "result": "loss"},
        ],
    )
    entry_b = entries_service.create(owner_id, sub_tally_id, {})
    competition.add_matches(
        owner_id,
        entry_b["id"],
        [{"opponent": "김철수", "score": "1-1", "result": "draw"}],
    )

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_TITLE in resp.text
    # Record: 1 win, 1 loss, 1 draw.
    assert "1" in resp.text and strings_module.MATCH_RESULT_WIN in resp.text
    # Head-to-head opponents both appear.
    assert "김철수" in resp.text
    assert "박영희" in resp.text


async def test_tournament_detail_win_rate_none_with_no_bouts(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id, _field_def_id = _tournament_ids(owner_id)

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_WIN_RATE_NONE in resp.text


# ---------------------------------------------------------------------------
# Stats screens: calendar, heatmap, streak, distributions, progression
# ---------------------------------------------------------------------------


def _practice_sub_tally_id(owner_id: int) -> int:
    """The seeded 검도/수련 (running, non-progression) sub-tally id."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '수련'""",
            (owner_id,),
        ).fetchone()["id"]


def _grading_sub_tally_id(owner_id: int) -> int:
    """The seeded 검도/심사 (progression: dan + shogo tracks) sub-tally id."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '검도' AND st.name = '심사'""",
            (owner_id,),
        ).fetchone()["id"]


def _reading_sub_tally_id(owner_id: int) -> int:
    """The seeded 독서 (progression: count-gated tier track) sub-tally id."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM sub_tally st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = '독서'""",
            (owner_id,),
        ).fetchone()["id"]


def _level_field_id(sub_tally_id: int) -> int:
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            "SELECT id FROM field_def WHERE sub_tally_id = ? AND kind = 'level'",
            (sub_tally_id,),
        ).fetchone()["id"]


async def test_detail_shows_calendar_with_marked_today(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id = _practice_sub_tally_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, sub_tally_id, {})

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    assert "cal-day--marked" in resp.text
    assert "cal-day--today" in resp.text


async def test_detail_shows_heatmap_grid_with_bucketed_cells(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id = _practice_sub_tally_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, sub_tally_id, {})

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    # 365 trailing days -> 365 .heat-cell elements.
    assert resp.text.count('class="heat-cell heat-cell--') == 365
    assert 'role="img"' in resp.text
    assert strings_module.HEATMAP_ARIA_LABEL in resp.text
    # At least one bucketed cell reflects today's entry.
    assert "heat-cell--0" in resp.text
    assert any(f"heat-cell--{n}" in resp.text for n in (1, 2, 3, 4))


async def test_detail_streak_matches_stats_service(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id = _practice_sub_tally_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, sub_tally_id, {})

    expected = stats.streaks(sub_tally_id, owner_id)

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    assert f"{expected['current']}{strings_module.STREAK_DAYS_UNIT}" in resp.text
    assert f"{expected['longest']}{strings_module.STREAK_DAYS_UNIT}" in resp.text


async def test_kendo_grading_detail_shows_dan_and_next_stage_and_shogo(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id = _grading_sub_tally_id(owner_id)
    level_field_id = _level_field_id(sub_tally_id)

    from app.services import entries as entries_service

    # Attain 1급 -> current dan is 1급, next is 초단 with a time gate countdown.
    entries_service.create(owner_id, sub_tally_id, {"values": {level_field_id: "1gup"}})

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    text = resp.text

    # Current dan stage shown.
    assert "1급" in text
    # Next-stage requirement (초단) and a remaining-time string.
    assert "초단" in text
    assert strings_module.PROGRESSION_NEXT_LABEL in text
    assert strings_module.PROGRESSION_TIME_REMAINING_PREFIX in text
    # The shōgō (칭호) parallel track is surfaced.
    assert strings_module.PROGRESSION_TRACK_SHOGO in text


async def test_reading_detail_shows_tier_and_count_to_next(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)
    sub_tally_id = _reading_sub_tally_id(owner_id)
    level_field_id = _level_field_id(sub_tally_id)

    from app.services import entries as entries_service

    # 3 books read -> still 입문 tier, 7 more needed for 초급 (gate_value=10).
    for _ in range(3):
        entries_service.create(owner_id, sub_tally_id, {"values": {level_field_id: "ibmun"}})

    resp = await client.get(f"/sub-tallies/{sub_tally_id}")
    assert resp.status_code == 200
    text = resp.text

    assert "입문" in text
    assert "초급" in text
    assert strings_module.PROGRESSION_COUNT_REMAINING_PREFIX in text
    assert "7" in text


async def test_home_does_not_render_heavy_stats(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seeding.seed_account(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text
    assert "heat-cell" not in text
    assert "cal-day" not in text
    assert strings_module.STATS_SUMMARY_TITLE not in text
    assert strings_module.PROGRESSION_TITLE not in text


# ---------------------------------------------------------------------------
# Strings centralization guard
# ---------------------------------------------------------------------------

# Matches Hangul syllable codepoints (가-힣).
_HANGUL_RE = re.compile(r"[가-힣]")

# Jinja comments, possibly spanning multiple lines: {# ... #}
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)


def _strip_jinja_comments(text: str) -> str:
    """Remove ``{# ... #}`` Jinja comments (incl. multi-line) from *text*.

    Replaces each comment with the same number of newlines it spanned, so
    line numbers in the remaining text are unaffected.
    """

    def _blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return _JINJA_COMMENT_RE.sub(_blank, text)


# Templates exempt from the Korean-literal guard, by path relative to
# app/templates/. These are long-form legal/content pages, not UI chrome —
# they are Korean-only by nature and not subject to i18n centralization.
# Page-chrome strings (titles, footer labels) on these pages still come from
# ui_strings. Do NOT add other templates here — genuinely hardcoded UI copy
# belongs in ui_strings.py.
_KOREAN_GUARD_EXEMPT_PATHS = {
    # 개인정보처리방침 (privacy policy) body — hand-converted from the
    # finalized legal draft in meetings/MEETING-2026-06-10-privacy-policy/.
    "web/_privacy_content.html",
}


async def test_templates_do_not_hardcode_korean_text() -> None:
    """``app/templates/**`` must not contain hardcoded user-facing Korean.

    User-facing strings live in ``app/ui_strings.py`` and are exposed to
    templates as ``strings`` (see app.routes.web). Hangul appearing only
    inside a Jinja comment (``{# ... #}``, including multi-line ones) is not
    user-facing and is excluded; so is the ``lang="ko"`` locale attribute
    (it contains no Hangul characters, but is naturally excluded anyway).
    The privacy-policy content partial (see ``_KOREAN_GUARD_EXEMPT_PATHS``) is
    also excluded — it's long-form legal prose, not UI chrome.

    This test enumerates every line containing Hangul outside a Jinja comment
    and fails loudly, naming the file + line, so a genuine hardcoded
    user-facing string gets centralized into ``ui_strings.py`` rather than
    silently tolerated.
    """
    templates_dir = Path(__file__).resolve().parents[2] / "app" / "templates"
    offenders: list[str] = []

    for path in sorted(templates_dir.rglob("*.jinja2")) + sorted(templates_dir.rglob("*.html")):
        rel_to_templates = path.relative_to(templates_dir).as_posix()
        if rel_to_templates in _KOREAN_GUARD_EXEMPT_PATHS:
            continue
        raw_text = path.read_text(encoding="utf-8")
        stripped_text = _strip_jinja_comments(raw_text)
        raw_lines = raw_text.splitlines()
        stripped_lines = stripped_text.splitlines()
        for lineno, (raw_line, stripped_line) in enumerate(
            zip(raw_lines, stripped_lines, strict=True), start=1
        ):
            if _HANGUL_RE.search(stripped_line):
                rel = path.relative_to(templates_dir.parents[1])
                offenders.append(f"{rel}:{lineno}: {raw_line.strip()}")

    assert not offenders, (
        "Hardcoded user-facing Korean text found outside ui_strings.py "
        "(centralize in app/ui_strings.py and reference via `strings`):\n" + "\n".join(offenders)
    )
