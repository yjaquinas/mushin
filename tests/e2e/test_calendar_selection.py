"""Playwright E2E specs for the month-calendar "selected day" affordance:
tapping a ``.cal-day`` cell marks it ``.cal-day--selected`` and renders that
day's entries inline, all via an HTMX fragment swap (no full navigation).

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
They're currently dormant when ``playwright`` isn't installed
(`pytest.importorskip` skips this module), mirroring
``tests/e2e/test_stats.py`` and ``tests/e2e/test_profiles_consent.py``.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser is available, so `uv run pytest tests/` stays green on a
plain dev machine / CI without a browser install.

These specs use the **signup** flow (``tests/e2e/test_profiles_consent.py``'s
``_signup`` pattern), not the retired guest-entry flow — guest mode is
retired per project CLAUDE.md (2026-06-16). ``test_stats.py`` previously had
a broken ``_enter_as_guest`` helper too; it has since been swapped to the same
signup-based flow.

A fresh username/password signup is lazy-seeded with the kendo + reading
starter templates (``app.auth.routes._lazy_seed`` calling
``app.services.seeding.seed_account``), so ``/home`` already has a "Kendo"
card after signup — no need to tap a one-tap example button to get a test
activity. These specs use that seeded "Kendo" activity.

Specs covered
-------------
1. Tapping a date in the month view adds ``cal-day--selected`` to that cell
   and renders that day's entries (or the empty state) inline, in the same
   HTMX interaction — no full page navigation.
2. Tapping a second date moves the affordance: the first date's cell loses
   ``cal-day--selected``, the second gains it.
3. A date that is both marked (has a logged entry) and selected carries both
   ``cal-day--marked`` and ``cal-day--selected`` on the same button.
4. Navigating to the next/prev month, or switching period tabs, clears
   selection: no cell carries ``cal-day--selected`` afterward, and the day
   detail is gone.
5. On first load of the month view (no tap yet), no cell carries
   ``cal-day--selected``.
6. Tapping the already-selected day again deselects it: the cell loses
   ``cal-day--selected`` and the day-entries detail is gone.
"""

from __future__ import annotations

import uuid

import pytest

from app import ui_strings

pytestmark = pytest.mark.e2e

# Skip the whole module when there's no Playwright browser available (plain
# `uv run pytest` on a dev machine / CI without a browser install). This is a
# real pytest + playwright.sync_api spec, unrelated to the agent-driven
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


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a
    new username/password signup with consent checked, then complete the
    one-time sharing-consent screen to reach the dashboard."""
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
    """Navigate from /home to an activity's detail screen via its card link,
    returning the detail-screen's `<article>` locator for that activity.

    The card links to ``/activities/{id}``, which 301-redirects to the
    canonical ``/@{username}/{slug}`` URL for any account with a username
    (every signup in this module has one -- only guests, with
    ``username=None``, would stay on ``/activities/{id}``). Wait for
    navigation away from /home generically rather than for one specific
    URL shape.
    """
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
    page.wait_for_load_state("load")
    return page.locator("article", has=page.get_by_role("heading", name=heading))


def _log_entry_today(page) -> None:
    """Open the log panel on the current detail screen and save a bare entry
    (marks today on the calendar)."""
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    sheet = page.locator("#log-panel")
    sheet.get_by_role("button", name=ui_strings.LOG_SUBMIT).click()
    page.wait_for_selector(".cal-day--marked")


def _track_navigations(page) -> dict[str, int]:
    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))
    return navigated


def _unique_username(slug: str) -> str:
    """A username that's unique per test run, so reruns against the
    persistent dev DB never collide with a leftover row from a previous run.
    Usernames are capped at 20 chars
    (``app.auth.routes._normalize_username``), so keep *slug* short (<=4
    chars) -- "e2c" (3) + slug + 13 hex chars stays within the cap."""
    return f"e2c{slug}{uuid.uuid4().hex[:13]}"


def test_initial_month_load_has_no_selected_day(page) -> None:
    """On first load of the month view (no tap yet), no cell carries
    cal-day--selected."""
    username = _unique_username("a")
    _signup(page, username)

    _open_detail(page, "Kendo")

    assert page.locator(".cal-day--selected").count() == 0


def test_tapping_a_day_selects_it_and_renders_entries_inline(page) -> None:
    """Tapping a date in the month view adds cal-day--selected to that cell
    and renders that day's entries (here: the empty state, since no entry
    was logged) inline via an HTMX fragment swap -- no full navigation."""
    username = _unique_username("b")
    _signup(page, username)

    _open_detail(page, "Kendo")

    navigated = _track_navigations(page)

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()

    page.wait_for_selector(".cal-day--selected")
    assert navigated["count"] == 0, "tapping a calendar day should swap a fragment, not navigate"

    assert page.locator(".cal-day--selected").count() == 1
    assert today_cell.evaluate("el => el.classList.contains('cal-day--selected')")

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")


def test_tapping_a_second_day_moves_selection(page) -> None:
    """Tapping a second date moves the affordance: the first date's cell
    loses cal-day--selected, the second gains it."""
    username = _unique_username("c")
    _signup(page, username)

    _open_detail(page, "Kendo")

    all_days = page.locator(".cal-day")
    day_count = all_days.count()
    assert day_count >= 2, "expected at least two day cells in the month grid"

    first_day = all_days.nth(0)
    first_label = first_day.inner_text().strip()
    first_day.click()
    # Wait for *this specific day's* selected state, not just any
    # `.cal-day--selected` match -- the generic selector can transiently
    # match a stale pre-swap node mid-fragment-swap, racing the assertion.
    page.wait_for_selector(f".cal-day--selected >> text='{first_label}'")

    selected_now = page.locator(".cal-day--selected")
    assert selected_now.count() == 1
    assert selected_now.first.inner_text().strip() == first_label

    # Pick a different day (by visible label) for the second tap.
    second_day = None
    second_label = None
    refreshed_days = page.locator(".cal-day")
    for i in range(refreshed_days.count()):
        candidate = refreshed_days.nth(i)
        label = candidate.inner_text().strip()
        if label != first_label:
            second_day = candidate
            second_label = label
            break
    assert second_day is not None, "expected a second distinct day cell to tap"

    second_day.click()
    page.wait_for_selector(f".cal-day--selected >> text='{second_label}'")

    selected_after_second = page.locator(".cal-day--selected")
    assert selected_after_second.count() == 1
    assert selected_after_second.first.inner_text().strip() == second_label
    assert selected_after_second.first.inner_text().strip() != first_label


def test_marked_and_selected_day_shows_both_classes(page) -> None:
    """A date that is both marked (a logged entry) and selected shows both
    cal-day--marked and cal-day--selected on the same button element."""
    username = _unique_username("d")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    marked_day = page.locator(".cal-day--marked").first
    marked_day.click()

    page.wait_for_selector(".cal-day--selected")

    marked_and_selected = page.locator(".cal-day--marked.cal-day--selected")
    assert marked_and_selected.count() == 1


def test_changing_month_clears_selection(page) -> None:
    """Navigating to the next/prev month clears selection -- no cell carries
    cal-day--selected afterward, and the day detail is gone."""
    username = _unique_username("e")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(".cal-day--selected")
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    page.get_by_role("button", name=ui_strings.CALENDAR_NEXT_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0

    page.get_by_role("button", name=ui_strings.CALENDAR_PREV_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0


def test_switching_period_tabs_clears_selection(page) -> None:
    """Switching period tabs (e.g. month -> week -> month) clears selection
    -- no cell carries cal-day--selected afterward, and the day detail is
    gone."""
    username = _unique_username("f")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(".cal-day--selected")

    page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_WEEK).click()
    page.wait_for_load_state("networkidle")

    page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0


def test_tapping_the_selected_day_again_deselects_it(page) -> None:
    """Tapping a day that is already selected deselects it -- the cell loses
    cal-day--selected and the day-entries card disappears."""
    username = _unique_username("g")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(".cal-day--selected")
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    page.locator(".cal-day--selected").first.click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0
