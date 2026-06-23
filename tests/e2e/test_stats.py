"""Playwright E2E specs for the stats screens (Task 9): calendar on the
sub-tally detail screen.

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
They're currently dormant: `playwright` was never added as a project
dependency, so `pytest.importorskip` skips this module.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser, mirroring
``tests/e2e/test_competition.py``.

Specs covered
-------------
1. Opening a sub-tally detail screen shows the month calendar (with at least
   one ``.cal-day`` cell), which doesn't appear on the home screen.
2. Calendar day cells remain >=44px tap targets at 360px viewport width.

The trailing-year heatmap ("year" period view) was removed entirely (the
period switcher is now week/month/all only) -- see
``app/templates/components/history.html.jinja2``. The spec that used to
switch to the "year" tab and assert on ``.heat-cell``/``role="img"`` has been
deleted along with the feature, not adapted.

Note: tap-to-select-a-day + inline day-entries-fragment behavior is covered
by ``tests/e2e/test_calendar_selection.py`` (which exercises the current
``.cal-day--selected`` affordance) rather than here — this module previously
had a now-deleted spec asserting on a stale ``#calendar-day-detail`` id that
no longer exists in ``app/templates/components/history.html.jinja2``.

The dan/shōgō grading-track and reading-tier specs that previously lived
here tested the progression/level-ladder feature, removed wholesale in
meetings/MEETING-2026-06-21-simplify-onboarding (migration
0013_drop_progression.sql drops the level/level_rule tables and tightens
field_def.kind's CHECK to exclude 'level'/'result'). They've been deleted
rather than adapted -- there is no replacement feature.

Real signup creates zero activities now (the onboarding seed step was
removed along with progression -- see above), so ``_signup`` here seeds a
fixture "Kendo" activity directly via ``tests.conftest.seed_test_activity``
(same pattern as ``tests/e2e/test_entry_comments.py``).
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
    so keep *slug* short (<=4 chars) -- "e2s" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2s{slug}{uuid.uuid4().hex[:13]}"


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a new
    username/password signup with consent checked, then complete the
    one-time sharing-consent screen to reach the dashboard.

    Real signup creates zero activities now (see module docstring), so this
    seeds a fixture "Kendo" activity directly via
    ``tests.conftest.seed_test_activity`` against the same DB file the live
    test server reads."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

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

    owner = users_module.find_by_username(username)
    seed_test_activity(owner["id"], name="Kendo")

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


def test_detail_screen_shows_calendar(page) -> None:
    """The Kendo detail screen's history section defaults to the month
    calendar (at least one ``.cal-day`` cell), which doesn't appear on the
    home screen."""
    _signup(page, _unique_username("a"))

    home_html = page.content()
    assert "cal-day" not in home_html

    _open_detail(page, "Kendo")

    assert page.locator(".cal-day").count() > 0


def test_calendar_day_cells_meet_tap_target_at_360px(page) -> None:
    """At 360px viewport width, .cal-day cells stay at the >=44px tap minimum."""
    _signup(page, _unique_username("d"))

    _open_detail(page, "Kendo")

    first_day = page.locator(".cal-day").first
    box = first_day.bounding_box()
    assert box is not None
    assert box["width"] >= 44
    assert box["height"] >= 44
