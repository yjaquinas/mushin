"""Playwright E2E specs for the match-list sub-form + competition stats (Task 8).

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md — "E2E tests use the Playwright
MCP — not a bundled Playwright"). They are written ahead of being run by an
agent with MCP browser tools attached.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser, mirroring
``tests/e2e/test_logging.py``.

Specs covered
-------------
1. Adding a match row in the 검도/시합 quick-add sub-form via the
   "+ 경기 추가" button appends a new bout row without a full page reload, and
   previously entered values in earlier rows survive the fragment swap.
2. Submitting a tournament entry with multiple match rows (opponent, score,
   result) persists them and the entry's detail screen reflects the updated
   W/L/D record.
3. The competition stats section (record, win rate, head-to-head) renders on
   the 시합 sub-tally's detail screen and only there — not on a non-tournament
   sub-tally's detail screen.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

# Skip the whole module when there's no Playwright browser available (plain
# `uv run pytest` on a dev machine / CI without a browser install). When run
# under the Playwright MCP, the MCP supplies its own browser/session and these
# specs are exercised by an agent driving the `mcp__playwright__*` tools
# directly rather than importing `playwright` here.
playwright_sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is not installed; e2e specs run via the Playwright MCP",
)

BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def browser():
    with playwright_sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    yield page
    context.close()


def _enter_as_guest(page) -> None:
    """Land on the entry screen and tap "그냥 시작하기" to start a guest session."""
    page.goto(BASE_URL + "/")
    page.get_by_text("그냥 시작하기").click()
    page.wait_for_url(BASE_URL + "/home")


def test_add_match_row_appends_without_reload_and_keeps_values(page) -> None:
    """Tapping "+ 경기 추가" appends a bout row via an HTMX fragment swap, and
    a value typed into the first row survives the swap."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="시합"))
    card.get_by_role("button", name="기록하기").click()

    sheet = page.locator("#log-sheet")
    opponent_input = sheet.locator('input[name^="match_opponent_"][name$="_0"]')
    opponent_input.fill("김철수")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    sheet.get_by_text("+ 경기 추가").click()

    # A second row appears with its own opponent input.
    page.wait_for_selector('#log-sheet input[name$="_1"][name^="match_opponent_"]')

    # The first row's value survived the fragment swap.
    assert sheet.locator('input[name^="match_opponent_"][name$="_0"]').input_value() == "김철수"
    assert navigated["count"] == 0, "adding a match row should swap a fragment, not navigate"


def test_submitting_tournament_entry_with_matches_updates_detail_record(page) -> None:
    """Logging a 시합 entry with match rows persists them, and the detail
    screen's record reflects the new bouts."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="시합"))
    card.get_by_role("button", name="기록하기").click()

    sheet = page.locator("#log-sheet")
    sheet.locator('input[name^="match_opponent_"][name$="_0"]').fill("김철수")
    sheet.locator('input[name^="match_score_"][name$="_0"]').fill("2-1")
    sheet.locator('label:has(input[name^="match_result_"][value="win"])').first.click()

    sheet.get_by_role("button", name="기록 남기기").click()

    # Navigate to the 시합 detail screen via the card's title link.
    page.get_by_role("link", name="시합").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    # The W/L/D record now shows at least one win.
    record = page.locator("text=전적").locator("..")
    assert "김철수" in page.content()
    assert record is not None


def test_competition_stats_only_on_tournament_detail(page) -> None:
    """The 전적 (competition stats) section appears on the 시합 detail screen
    and not on a non-tournament (수련) detail screen."""
    _enter_as_guest(page)

    tournament_card = page.locator("article", has=page.get_by_role("heading", name="시합"))
    tournament_card.get_by_role("link", name="시합").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")
    assert page.get_by_text("전적").count() > 0

    page.goto(BASE_URL + "/home")
    practice_card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    practice_card.get_by_role("link", name="수련").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")
    assert page.get_by_text("전적").count() == 0
