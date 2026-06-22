"""Playwright E2E specs for the home/activity-card visual-polish pass (Task 6).

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
1. Empty state for a fresh guest with zero sub-tallies: the home page shows
   the 無心 glyph, ``HOME_EMPTY``, and ``APP_GLOSS`` text — not the old bare
   ``<p>{{ strings.HOME_EMPTY }}</p>`` markup.
2. Card icon + hierarchy: each activity card renders an
   ``<svg aria-hidden="true">`` icon in the label row, and the hero numeral
   is the only element on the card with ``text-text-primary``.
3. Log -> micro-moment: on the sub-tally detail screen, submitting the
   quick-add log form returns a card fragment whose hero numeral has
   ``hero--bumped`` immediately after the swap, while the initial page
   load's card does not.
4. Log-panel focus + double-submit guard: expanding the inline log panel (via
   the detail screen's trigger above the activity card) moves focus inside
   ``#log-panel``; a successful submit collapses the panel
   (``aria-expanded="false"``); the submit button has
   ``hx-disabled-elt="this"``.
5. Theme toggle: clicking the masthead theme toggle flips light <-> dark,
   setting ``data-theme`` on ``<html>`` accordingly (default with no cookie
   is light), and the choice persists across a page reload via the
   ``mushin_theme`` cookie.
6. Home cards: every card on ``/home`` is a single ``<a>`` link to its
   ``/activities/{id}`` detail page, has no visible action button, and a
   freshly-created category card (via ``POST /categories``) is clickable
   without a reload too.

The progress-bar spec that previously lived here (".progress-fill"'s inline
width style changing after logging on a progression-mode sub-tally) tested
the progression/level-ladder feature, removed wholesale in
meetings/MEETING-2026-06-21-simplify-onboarding. It's been deleted rather
than adapted -- there is no progress bar left to assert on.

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
    so keep *slug* short (<=4 chars) -- "e2v" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2v{slug}{uuid.uuid4().hex[:13]}"


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
    returning the detail-screen's hero `<article>` locator for that sub-tally.

    The card links to ``/activities/{id}``, which 301-redirects to the
    canonical ``/@{username}/{slug}`` URL for any account with a username
    (every signup in this module has one). Wait for navigation away from
    /home generically rather than for one specific URL shape.

    The detail screen's hero card is deliberately "chrome-less" (see
    ``components/activity_card.html.jinja2``'s unlinked branch) -- it has no
    heading of its own, since the page's own ``<h1>`` already names the
    activity. So scope by the stable ``#card-{id}`` id (read off the /home
    card before navigating) rather than by heading, which only exists on
    /home's linked card.
    """
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    card_id = home_card.get_attribute("id")
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
    page.wait_for_load_state("load")
    return page.locator(f"#{card_id}")


def test_home_masthead_links_to_home(page) -> None:
    """The sitewide masthead above <main> links to the signed-in user's
    canonical profile URL (``home_url`` -- ``/@{username}`` for any account
    with a username, never the bare ``/home`` path) and shows both the
    English and Hanja wordmarks (``ui_strings.APP_NAME`` /
    ``APP_NAME_HANJA`` -- copy was translated to English; there is no
    Hangul wordmark)."""
    username = _unique_username("a")
    _signup(page, username)

    masthead = page.locator(f'a[href="/@{username}"]').first
    assert ui_strings.APP_NAME in masthead.inner_text()
    assert ui_strings.APP_NAME_HANJA in masthead.inner_text()


def test_empty_state_shows_glyph_and_gloss_for_fresh_account(page) -> None:
    """A fresh account with zero activities sees the 無心 glyph, HOME_EMPTY,
    and APP_GLOSS — not the old bare-paragraph empty state.

    Real signup creates zero activities (no onboarding seed step any more --
    see module docstring), so unlike the other specs in this module this one
    signs up directly without going through ``_signup``'s fixture-seeding
    step, to actually exercise the empty-state branch.
    """
    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", _unique_username("b"))
    page.fill("#auth-form input[name='password']", "correct-horse-battery")
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()

    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(lambda url: "/welcome-sharing" not in url)

    page.goto(BASE_URL + "/home")

    empty_glyph = page.locator('span[aria-hidden="true"]', has_text="無心")
    assert empty_glyph.count() > 0

    assert empty_glyph.first.get_attribute("class") is not None
    assert "var(--spacing-icon-lg)" in (empty_glyph.first.get_attribute("class") or "")

    assert page.get_by_text("Nothing started yet.").count() > 0
    assert page.get_by_text("No-mind. Just show up, and watch it add up.").count() > 0


def test_activity_cards_render_single_hero_numeral(page) -> None:
    """The hero numeral is the only element on an activity card with
    `text-text-primary` -- cards no longer carry a per-activity icon in the
    label row (decluttered to name + hero numeral only)."""
    _signup(page, _unique_username("c"))

    card = page.locator("article", has=page.get_by_role("heading", name="Kendo"))

    # The hero numeral is the only `text-text-primary` element on the card.
    brand_elements = card.locator(".text-text-primary")
    assert brand_elements.count() == 1
    hero_class = brand_elements.first.get_attribute("class") or ""
    assert "text-hero-numeral" in hero_class


def test_log_bumps_hero_numeral_with_micro_moment_class(page) -> None:
    """On the sub-tally detail screen, submitting the quick-add log form
    returns a card fragment whose hero numeral has `hero--bumped`, while the
    initial page load's card does not."""
    _signup(page, _unique_username("d"))

    card = _open_detail(page, "Kendo")
    hero = card.locator(".text-hero-numeral")

    # Initial page load: no `hero--bumped` class.
    initial_class = hero.get_attribute("class") or ""
    assert "hero--bumped" not in initial_class

    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    page.locator("#log-panel form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    # Wait for the fragment swap, then check the new hero numeral's class.
    page.wait_for_function(
        """(sel) => {
            const el = document.querySelector(sel);
            return el && el.classList.contains('hero--bumped');
        }""",
        arg=f"#card-{card.get_attribute('id').split('-')[-1]} .text-hero-numeral",
    )

    swapped_class = (
        page.locator(
            f"#card-{card.get_attribute('id').split('-')[-1]} .text-hero-numeral"
        ).get_attribute("class")
        or ""
    )
    assert "hero--bumped" in swapped_class


def test_log_panel_focuses_on_expand_and_collapses_on_submit(page) -> None:
    """On the sub-tally detail screen, expanding the inline log panel moves
    focus inside #log-panel; a successful submit collapses the panel
    (aria-expanded -> "false"), and the submit button has
    hx-disabled-elt="this"."""
    _signup(page, _unique_username("f"))

    _open_detail(page, "Kendo")

    trigger = page.locator('button[id^="log-trigger-"]')
    trigger.click()

    panel = page.locator("#log-panel")
    panel.wait_for(state="visible")
    assert trigger.get_attribute("aria-expanded") == "true"

    # Focus moved inside the expanded panel.
    is_focus_inside_panel = page.evaluate(
        "() => { const panel = document.querySelector('#log-panel'); "
        "return panel ? panel.contains(document.activeElement) : false; }"
    )
    assert is_focus_inside_panel

    # The submit button carries the double-submit guard attribute.
    submit_button = panel.locator("form").get_by_role("button", name=ui_strings.LOG_SUBMIT)
    assert submit_button.get_attribute("hx-disabled-elt") == "this"

    submit_button.click()

    # After a successful submit, the panel collapses.
    page.wait_for_function(
        "(id) => document.getElementById(id)?.getAttribute('aria-expanded') === 'false'",
        arg=trigger.get_attribute("id"),
    )


def test_theme_toggle_cycles_and_persists_across_reload(page) -> None:
    """The masthead theme toggle flips light <-> dark, reflecting the active
    theme as `data-theme` on `<html>` (default with no cookie is light), and
    the choice survives a page reload via the `mushin_theme` cookie."""
    _signup(page, _unique_username("g"))

    toggle = page.locator("button[hx-post='/preferences/theme']")

    # Fresh account: no `mushin_theme` cookie yet -> defaults to "light",
    # never inferred from any OS/prefers-color-scheme signal.
    assert page.locator("html").get_attribute("data-theme") == "light"

    # First click: light -> dark.
    toggle.click()
    page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'dark'")
    assert page.locator("html").get_attribute("data-theme") == "dark"

    # Persists across reload.
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"

    # Second click: dark -> light.
    toggle = page.locator("button[hx-post='/preferences/theme']")
    toggle.click()
    page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'light'")
    assert page.locator("html").get_attribute("data-theme") == "light"

    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "light"


def test_home_cards_have_no_action_button_and_link_to_detail(page) -> None:
    """On /home, every card is a single <a> link to /activities/{id} (which
    301-redirects to the canonical ``/@{username}/{slug}`` for any account
    with a username) and has no visible quick-add action button
    (`#log-trigger-{id}` is absent — quick-add only lives on the detail
    screen)."""
    _signup(page, _unique_username("h"))

    card = page.locator("article", has=page.get_by_role("heading", name="Kendo"))
    card_id = card.get_attribute("id")
    activity_id = card_id.split("-")[-1]

    # No action button on the home card.
    assert card.locator(f'button[id="log-trigger-{activity_id}"]').count() == 0
    assert card.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).count() == 0

    # The whole card is a single link to the detail page.
    link = card.locator("a")
    assert link.count() == 1
    assert link.first.get_attribute("href") == f"/activities/{activity_id}"

    link.first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))


def test_new_category_card_is_clickable_without_reload(page) -> None:
    """After POST /activities appends a new card to #cards on /home, the new
    card is `linked=True` (clickable, no action button) immediately, with no
    reload needed."""
    _signup(page, _unique_username("i"))

    before_count = page.locator("#cards > article").count()

    page.locator("#cards").locator('button[hx-get="/activities/new"]').click()

    # #sheet itself is a plain wrapper div around a `position: fixed` dialog,
    # so it collapses to zero height in layout -- Playwright's visibility
    # check needs the dialog element itself, not the wrapper.
    sheet = page.locator("#sheet [role='dialog']")
    sheet.wait_for(state="visible")

    name_input = sheet.locator('input[name="name"]')
    name_input.fill("Cycling")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    sheet.locator("form").get_by_role("button", name=ui_strings.ACTIVITY_FORM_SUBMIT).click()

    page.wait_for_function(
        "(before) => document.querySelectorAll('#cards > article').length > before",
        arg=before_count,
    )
    assert navigated["count"] == 0, "creating a category should swap a fragment, not navigate"

    # The create-category dialog closes itself on a successful submit
    # (hx-on::after-request="close()").
    sheet.wait_for(state="hidden")

    new_card = page.locator("article", has=page.get_by_role("heading", name="Cycling"))
    link = new_card.locator("a")
    assert link.count() == 1

    link.first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
