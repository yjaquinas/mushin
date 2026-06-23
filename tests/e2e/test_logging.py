"""Playwright E2E specs for the quick-add log flow + character-sheet home (Task 6).

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
They're currently dormant: `playwright` was never added as a project
dependency, so `pytest.importorskip` skips this module.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser.

Specs covered
-------------
1. Quick-add log refreshes the detail screen's Summary card via an HTMX
   fragment swap — no full page reload (e.g. assert no `load` navigation
   event / the page's `<head>` script tags are not re-executed). Quick-add
   only lives on the sub-tally detail screen now, so the spec navigates
   there first.
2. A `#hashtag` typed into the free-text notes field before submit is parsed
   and persisted, and surfaces in the tag-frequency section once the
   `log-saved` fragment refresh fires (see `components/field_stats.html.jinja2`).
3. The notes textarea wraps long text (never horizontal-scroll) at a 360px
   viewport and at a 1.5x font scale.

NOTE: real signup creates zero activities -- the kendo/reading onboarding
seed and the progression feature it demonstrated were removed wholesale
(meetings/MEETING-2026-06-21-simplify-onboarding). ``_signup`` here seeds a
fixture "Kendo" activity directly via ``tests.conftest.seed_test_activity``
(same pattern as ``tests/e2e/test_entry_comments.py``), against the same DB
file the live test server reads.
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
    so keep *slug* short (<=4 chars) -- "e2l" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2l{slug}{uuid.uuid4().hex[:13]}"


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a new
    username/password signup with consent checked, then complete the
    one-time sharing-consent screen to reach the dashboard.

    Real signup creates zero activities now (the onboarding seed step was
    removed along with the progression feature it demonstrated -- see module
    docstring), so this seeds a fixture "Kendo" activity directly via
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
    """Navigate from /home to an activity's detail screen via its card link,
    returning the detail screen's ``#stats-summary-{id}`` locator (the
    Summary card).

    The card links to ``/activities/{id}``, which 301-redirects to the
    canonical ``/@{username}/{slug}`` URL for any account with a username
    (every signup in this module has one). Wait for navigation away from
    /home generically rather than for one specific URL shape.

    The detail screen has no hero-card swap target of its own any more (the
    redundant numeral+streak zone above the Summary card was retired) — the
    Summary card is the one element that visibly changes after a quick-add
    log, via its own ``log-saved``-triggered self-refresh. Derive the
    activity id from the /home card's stable ``card-{id}`` id rather than
    by heading, which only exists on /home's card.
    """
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    activity_id = (home_card.get_attribute("id") or "").rsplit("-", 1)[-1]
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
    page.wait_for_load_state("load")
    return page.locator(f"#stats-summary-{activity_id}")


def test_quick_add_updates_card_via_fragment_swap(page) -> None:
    """On the activity detail screen, logging via the quick-add panel
    refreshes the Summary card's counts without a full page reload."""
    _signup(page, _unique_username("a"))

    summary = _open_detail(page, "Kendo")
    before_text = summary.inner_text()
    summary_id = summary.get_attribute("id")

    # Track full-page navigations: a fragment swap must NOT trigger one.
    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    page.locator("#log-panel form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # The Summary card self-refreshes in place (HTMX outerHTML swap on
    # #stats-summary-{id}, triggered by the "log-saved" HX-Trigger header).
    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.innerText !== args.before;
        }""",
        arg={"sel": f"#{summary_id}", "before": before_text},
    )

    assert navigated["count"] == 0, "logging should swap a fragment, not navigate"


def test_hashtag_in_notes_survives_fragment_swap_and_appears_in_tag_frequency(page) -> None:
    """A `#hashtag` typed into the free-text notes field is parsed and
    persisted on submit, and shows up in the tag-frequency section, which
    auto-refreshes via the `log-saved` HX-Trigger the log POST fires (see
    `components/field_stats.html.jinja2`)."""
    _signup(page, _unique_username("b"))

    _open_detail(page, "Kendo")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    panel = page.locator("#log-panel")
    notes_input = panel.locator('textarea[name^="hashtags_"]').first
    notes_input.fill("Good randori today #suriagemen")

    panel.get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # field-stats refreshes off the same `log-saved` trigger as the hero-card
    # swap, so the new tag's frequency chip appears without a reload.
    page.wait_for_selector("text=suriagemen")


def test_notes_textarea_wraps_long_text_at_360px(page) -> None:
    """At a 360px viewport, the free-text notes field wraps long input
    (never horizontal-scroll) -- it's a plain `<textarea>`, not a row of
    tap-select chips, so there's no separate selected-state signal to check."""
    _signup(page, _unique_username("c"))

    _open_detail(page, "Kendo")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    notes_input = page.locator('#log-panel textarea[name^="hashtags_"]').first
    notes_input.fill(
        "A very long line of notes text that should wrap onto several lines "
        "inside the textarea rather than overflowing it horizontally #randori"
    )

    overflow_x = page.evaluate(
        "(el) => el.scrollWidth > el.clientWidth + 1", notes_input.element_handle()
    )
    assert not overflow_x, "the notes textarea must wrap, not horizontal-scroll, at 360px"


def test_notes_textarea_wraps_at_1_5x_font_scale(page) -> None:
    """Notes-textarea wrapping holds up at a 1.5x browser font-scale (zoom)."""
    _signup(page, _unique_username("d"))
    page.evaluate("document.documentElement.style.fontSize = '150%'")

    _open_detail(page, "Kendo")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()

    notes_input = page.locator('#log-panel textarea[name^="hashtags_"]').first
    notes_input.fill(
        "A very long line of notes text that should wrap onto several lines "
        "inside the textarea rather than overflowing it horizontally #randori"
    )

    overflow_x = page.evaluate(
        "(el) => el.scrollWidth > el.clientWidth + 1", notes_input.element_handle()
    )
    assert not overflow_x, "the notes textarea must still wrap at 1.5x font scale"


def test_submitting_log_collapses_panel_and_updates_card(page) -> None:
    """Expanding the inline log panel, filling and submitting the form
    collapses the panel (`aria-expanded="false"`, `#log-panel` empty/hidden)
    and updates the detail screen's Summary card."""
    _signup(page, _unique_username("g"))

    summary = _open_detail(page, "Kendo")
    trigger = page.locator('button[id^="log-trigger-"]')
    before_text = summary.inner_text()

    trigger.click()

    panel = page.locator("#log-panel")
    panel.wait_for(state="visible")
    assert trigger.get_attribute("aria-expanded") == "true"

    panel.locator("form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # The HX-Trigger: log-saved response collapses the panel.
    page.wait_for_function(
        "(id) => document.getElementById(id)?.getAttribute('aria-expanded') === 'false'",
        arg=trigger.get_attribute("id"),
    )
    assert not panel.is_visible()

    # The Summary card self-refreshes with updated counts.
    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.innerText !== args.before;
        }""",
        arg={"sel": f"#{summary.get_attribute('id')}", "before": before_text},
    )
