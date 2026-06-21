"""Playwright E2E specs for the match-list sub-form + competition stats (Task 8).

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
They're currently dormant: `playwright` was never added as a project
dependency, so `pytest.importorskip` skips this module.

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

import uuid

import pytest

from app import ui_strings

pytestmark = pytest.mark.e2e

# Skip the whole module when there's no Playwright browser available (plain
# `uv run pytest` on a dev machine / CI without a browser install -- the
# `playwright` pip package was never added as a dependency). This is a real
# pytest + playwright.sync_api spec, unrelated to the agent-driven
# `playwright-cli` skill; it'll start running once `playwright` + a browser
# are installed.
playwright_sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is not installed; this dormant pytest-playwright spec is unrelated to the playwright-cli skill",
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


def _unique_username(slug: str) -> str:
    """A username that's unique per test run, so reruns against the
    persistent dev DB never collide with a leftover row from a previous run.
    Usernames are capped at 20 chars (``app.auth.routes._normalize_username``),
    so keep *slug* short (<=4 chars) -- "e2c" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2c{slug}{uuid.uuid4().hex[:13]}"


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a new
    username/password signup with consent checked, then complete the
    one-time sharing-consent screen to reach the dashboard. A fresh
    username/password signup now seeds the same starter templates a guest
    used to get (``app.auth.routes._lazy_seed``)."""
    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", password)
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()

    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    page.goto(BASE_URL + "/home")


def _open_detail(page, heading: str):
    """Navigate from /home to a sub-tally's detail screen via its card link,
    returning the detail-screen's `<article>` locator for that sub-tally.

    The card links to ``/activities/{id}``, which 301-redirects to the
    canonical ``/@{username}/{slug}`` URL for any account with a username
    (every signup in this module has one). Wait for navigation away from
    /home generically rather than for one specific URL shape.
    """
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
    page.wait_for_load_state("load")
    return page.locator("article", has=page.get_by_role("heading", name=heading))


def test_add_match_row_appends_without_reload_and_keeps_values(page) -> None:
    """Tapping "+ Add match" appends a bout row via an HTMX fragment swap,
    and a value typed into the first row survives the swap."""
    _signup(page, _unique_username("a"))

    _open_detail(page, "Kendo")
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
    _signup(page, _unique_username("b"))

    _open_detail(page, "Kendo")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    sheet = page.locator("#log-panel")
    sheet.locator('input[name^="match_opponent_"][name$="_0"]').fill("Kim Chulsoo")
    sheet.locator('input[name^="match_score_"][name$="_0"]').fill("2-1")
    sheet.locator('label:has(input[name^="match_result_"][value="win"])').first.click()

    sheet.get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # The Record section is already on the page (empty) before this submit,
    # so wait for the opponent name itself -- the out-of-band swap that
    # refreshes the W/L/D record/timeline/head-to-head -- rather than the
    # ever-present "Record" heading, which would resolve before the swap.
    page.wait_for_selector("#competition-stats >> text=Kim Chulsoo")
    assert "Kim Chulsoo" in page.content()


def test_competition_stats_only_on_tournament_detail(page) -> None:
    """The Record (competition stats) section appears on the Kendo detail
    screen (it carries a match-list field) and not on a non-match-list
    detail screen like Reading."""
    _signup(page, _unique_username("c"))

    _open_detail(page, "Kendo")
    assert page.get_by_text(ui_strings.STATS_TITLE).count() > 0

    page.goto(BASE_URL + "/home")
    _open_detail(page, "Reading")
    assert page.get_by_text(ui_strings.STATS_TITLE).count() == 0
