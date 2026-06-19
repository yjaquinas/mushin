"""Playwright E2E specs for the home/activity-card visual-polish pass (Task 6).

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
1. Empty state for a fresh guest with zero sub-tallies: the home page shows
   the 無心 glyph, ``HOME_EMPTY``, and ``APP_GLOSS`` text — not the old bare
   ``<p>{{ strings.HOME_EMPTY }}</p>`` markup.
2. Card icon + hierarchy: each activity card renders an
   ``<svg aria-hidden="true">`` icon in the label row, and the hero numeral
   is the only element on the card with ``text-brand``.
3. Log -> micro-moment: on the sub-tally detail screen, submitting the
   quick-add log form returns a card fragment whose hero numeral has
   ``hero--bumped`` immediately after the swap, while the initial page
   load's card does not.
4. Progress bar update: for a progression-mode sub-tally, ``.progress-fill``'s
   inline ``width`` style changes after logging (from the detail screen).
5. Log-panel focus + double-submit guard: expanding the inline log panel (via
   the detail screen's trigger above the activity card) moves focus inside
   ``#log-panel``; a successful submit collapses the panel
   (``aria-expanded="false"``); the submit button has
   ``hx-disabled-elt="this"``.
6. Theme toggle: clicking the masthead theme toggle cycles
   light -> dark -> system, setting/clearing ``data-theme`` on ``<html>``
   accordingly, and the choice persists across a page reload via the
   ``mushin_theme`` cookie.
7. Home cards: every card on ``/home`` is a single ``<a>`` link to its
   ``/activities/{id}`` detail page, has no visible action button, and a
   freshly-created category card (via ``POST /categories``) is clickable
   without a reload too.
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
    """Land on the entry screen and tap "Get started" to start a guest session."""
    page.goto(BASE_URL + "/")
    page.get_by_text("Get started").click()
    page.wait_for_url(BASE_URL + "/home")


def test_home_masthead_links_to_home(page) -> None:
    """The sitewide masthead above <main> links to /home and shows both the
    Hangul and Hanja wordmarks."""
    _enter_as_guest(page)

    masthead = page.locator('a[href="/home"]').first
    assert "무심" in masthead.inner_text()
    assert "無心" in masthead.inner_text()


def test_empty_state_shows_glyph_and_gloss_for_fresh_guest(page) -> None:
    """A fresh guest with zero sub-tallies sees the 無心 glyph, HOME_EMPTY,
    and APP_GLOSS — not the old bare-paragraph empty state.

    Note: onboarding lazy-seeds the kendo + reading templates "on first
    entry" per the domain model, so a brand-new guest's /home may already
    have cards. If seeding has already happened by the time /home renders,
    this spec is a no-op (the empty-state branch is unreachable for that
    guest) — but if the empty branch *is* rendered, it must use the new
    markup, never the old bare <p>.
    """
    _enter_as_guest(page)

    empty_glyph = page.locator('span[aria-hidden="true"]', has_text="無心")
    if empty_glyph.count() == 0:
        pytest.skip("guest already has seeded cards; empty-state branch not reached")

    assert empty_glyph.first.get_attribute("class") is not None
    assert "var(--spacing-icon-lg)" in (empty_glyph.first.get_attribute("class") or "")

    assert page.get_by_text("Nothing started yet.").count() > 0
    assert page.get_by_text("No-mind. Just show up, and watch it add up.").count() > 0


def test_activity_cards_render_icon_and_single_hero_numeral(page) -> None:
    """Each activity card renders an <svg aria-hidden="true"> icon in the
    label row, and the hero numeral is the only element on the card with
    `text-brand`."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="Practice"))

    # An aria-hidden svg icon is present in the card's label row.
    icon_svg = card.locator('header svg[aria-hidden="true"]')
    assert icon_svg.count() >= 1

    # The hero numeral is the only `text-brand` element on the card.
    brand_elements = card.locator(".text-brand")
    assert brand_elements.count() == 1
    hero_class = brand_elements.first.get_attribute("class") or ""
    assert "text-hero-numeral" in hero_class


def test_log_bumps_hero_numeral_with_micro_moment_class(page) -> None:
    """On the sub-tally detail screen, submitting the quick-add log form
    returns a card fragment whose hero numeral has `hero--bumped`, while the
    initial page load's card does not."""
    _enter_as_guest(page)

    home_card = page.locator("article", has=page.get_by_role("heading", name="Practice"))
    home_card.locator("a").first.click()
    page.wait_for_url(f"{BASE_URL}/activities/*")

    card = page.locator("article", has=page.get_by_role("heading", name="Practice"))
    hero = card.locator(".text-hero-numeral")

    # Initial page load: no `hero--bumped` class.
    initial_class = hero.get_attribute("class") or ""
    assert "hero--bumped" not in initial_class

    card.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
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


def test_progress_fill_width_changes_after_log(page) -> None:
    """For a progression-mode sub-tally (e.g. Reading), `.progress-fill`'s
    inline `width` style reflects the new percentage after logging."""
    _enter_as_guest(page)

    home_card = page.locator("article", has=page.get_by_role("heading", name="Reading"))
    home_card.locator("a").first.click()
    page.wait_for_url(f"{BASE_URL}/activities/*")

    card = page.locator("article", has=page.get_by_role("heading", name="Reading"))
    progress_fill = card.locator(".progress-fill")

    before_style = progress_fill.get_attribute("style") or ""

    card.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    page.locator("#log-sheet form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.getAttribute('style') !== args.before;
        }""",
        arg={"sel": f"#{card.get_attribute('id')} .progress-fill", "before": before_style},
    )

    after_style = page.locator(f"#{card.get_attribute('id')} .progress-fill").get_attribute("style")
    assert after_style != before_style


def test_log_panel_focuses_on_expand_and_collapses_on_submit(page) -> None:
    """On the sub-tally detail screen, expanding the inline log panel moves
    focus inside #log-panel; a successful submit collapses the panel
    (aria-expanded -> "false"), and the submit button has
    hx-disabled-elt="this"."""
    _enter_as_guest(page)

    home_card = page.locator("article", has=page.get_by_role("heading", name="Practice"))
    home_card.locator("a").first.click()
    page.wait_for_url(f"{BASE_URL}/activities/*")

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
    """The masthead theme toggle cycles system -> light -> dark -> system,
    reflecting the active theme as `data-theme` on `<html>` (absent for
    "system"), and the choice survives a page reload via the
    `mushin_theme` cookie."""
    _enter_as_guest(page)

    toggle = page.locator("button[hx-post='/preferences/theme']")

    # Fresh guest: no `mushin_theme` cookie yet -> "system" -> no
    # `data-theme` attribute on <html>.
    assert page.locator("html").get_attribute("data-theme") is None

    # First click: system -> light.
    toggle.click()
    page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'light'")
    assert page.locator("html").get_attribute("data-theme") == "light"

    # Persists across reload.
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "light"

    # Second click: light -> dark.
    toggle = page.locator("button[hx-post='/preferences/theme']")
    toggle.click()
    page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'dark'")
    assert page.locator("html").get_attribute("data-theme") == "dark"

    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"

    # Third click: dark -> system (data-theme attribute removed).
    toggle = page.locator("button[hx-post='/preferences/theme']")
    toggle.click()
    page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === null")
    assert page.locator("html").get_attribute("data-theme") is None

    page.reload()
    assert page.locator("html").get_attribute("data-theme") is None


def test_home_cards_have_no_action_button_and_link_to_detail(page) -> None:
    """On /home, every card is a single <a> link to /activities/{id} and
    has no visible quick-add action button (`#log-trigger-{id}` is absent —
    quick-add only lives on the detail screen)."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="Practice"))
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
    page.wait_for_url(f"{BASE_URL}/activities/{activity_id}")


def test_new_category_card_is_clickable_without_reload(page) -> None:
    """After POST /categories appends a new card to #cards on /home, the new
    card is `linked=True` (clickable, no action button) immediately, with no
    reload needed."""
    _enter_as_guest(page)

    before_count = page.locator("#cards > article").count()

    page.locator("#cards").locator('button[hx-get="/categories/new"]').click()

    sheet = page.locator("#sheet")
    sheet.wait_for(state="visible")

    name_input = sheet.locator('input[name="name"]')
    name_input.fill("Cycling")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    sheet.locator("form").get_by_role("button", name=ui_strings.CATEGORY_FORM_SUBMIT).click()

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
    page.wait_for_url(f"{BASE_URL}/activities/*")
