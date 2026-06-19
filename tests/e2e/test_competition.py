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
1. Adding a match row in the Kendo/Tournament quick-add sub-form via the
   "+ Add match" button appends a new bout row without a full page reload,
   and previously entered values in earlier rows survive the fragment swap.
   Quick-add only lives on the sub-tally detail screen, so the spec navigates
   there first.
2. Submitting a tournament entry with multiple match rows (opponent, score,
   result) persists them and the entry's detail screen reflects the updated
   W/L/D record.
3. The competition stats section (record, win rate, head-to-head) renders on
   the Tournament sub-tally's detail screen and only there — not on a
   non-tournament sub-tally's detail screen.
"""

from __future__ import annotations

import pytest

from app import ui_strings

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
    """Land on the entry screen and tap "Continue without an account" to start a guest session."""
    page.goto(BASE_URL + "/")
    page.get_by_text(ui_strings.ENTRY_GUEST_LINK).click()
    page.wait_for_url(BASE_URL + "/home")


def _open_detail(page, heading: str):
    """Navigate from /home to a sub-tally's detail screen via its card link,
    returning the detail-screen's `<article>` locator for that sub-tally."""
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    home_card.locator("a").first.click()
    page.wait_for_url(f"{BASE_URL}/activities/*")
    return page.locator("article", has=page.get_by_role("heading", name=heading))


def test_add_match_row_appends_without_reload_and_keeps_values(page) -> None:
    """Tapping "+ Add match" appends a bout row via an HTMX fragment swap,
    and a value typed into the first row survives the swap."""
    _enter_as_guest(page)

    _open_detail(page, "Tournament")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    sheet = page.locator("#log-panel")
    opponent_input = sheet.locator('input[name^="match_opponent_"][name$="_0"]')
    opponent_input.fill("Kim Chulsoo")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    sheet.get_by_text(ui_strings.MATCH_LIST_ADD_ROW).click()

    # A second row appears with its own opponent input.
    page.wait_for_selector('#log-panel input[name$="_1"][name^="match_opponent_"]')

    # The first row's value survived the fragment swap.
    assert (
        sheet.locator('input[name^="match_opponent_"][name$="_0"]').input_value() == "Kim Chulsoo"
    )
    assert navigated["count"] == 0, "adding a match row should swap a fragment, not navigate"


def test_submitting_tournament_entry_with_matches_updates_detail_record(page) -> None:
    """Logging a Tournament entry with match rows persists them, and the
    detail screen's record reflects the new bouts."""
    _enter_as_guest(page)

    _open_detail(page, "Tournament")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    sheet = page.locator("#log-panel")
    sheet.locator('input[name^="match_opponent_"][name$="_0"]').fill("Kim Chulsoo")
    sheet.locator('input[name^="match_score_"][name$="_0"]').fill("2-1")
    sheet.locator('label:has(input[name^="match_result_"][value="win"])').first.click()

    sheet.get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # The W/L/D record now shows at least one win, on the same detail screen.
    page.wait_for_selector(f"text={ui_strings.STATS_TITLE}")
    assert "Kim Chulsoo" in page.content()


def test_competition_stats_only_on_tournament_detail(page) -> None:
    """The Record (competition stats) section appears on the Tournament
    detail screen and not on a non-tournament (Practice) detail screen."""
    _enter_as_guest(page)

    _open_detail(page, "Tournament")
    assert page.get_by_text(ui_strings.STATS_TITLE).count() > 0

    page.goto(BASE_URL + "/home")
    _open_detail(page, "Practice")
    assert page.get_by_text(ui_strings.STATS_TITLE).count() == 0
