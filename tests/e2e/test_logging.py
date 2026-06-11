"""Playwright E2E specs for the quick-add log flow + character-sheet home (Task 6).

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md — "E2E tests use the Playwright
MCP — not a bundled Playwright"). They are written ahead of being run by an
agent with MCP browser tools attached.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser.

Specs covered
-------------
1. Quick-add log updates the activity card's hero numeral via an HTMX
   fragment swap — no full page reload (e.g. assert no `load` navigation
   event / the page's `<head>` script tags are not re-executed).
2. A tag chip tap-selected before submit survives the fragment swap (the
   swapped-in card's quick-add sheet, if reopened, shows the same chip
   selected — per app.routes.web.create_log's `selected_tags` echo).
3. Chip rendering: chips wrap onto multiple lines (never horizontal-scroll)
   at a 360px viewport, and the selected state is visibly distinguished by
   shape/weight + a glyph (not color alone) at 1.5x font scale.
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


def test_quick_add_updates_card_via_fragment_swap(page) -> None:
    """Logging via the quick-add sheet bumps the card's hero numeral without
    a full page reload."""
    _enter_as_guest(page)

    # 검도 / 수련 is a `running`-mode sub-tally; its hero numeral is the
    # lifetime count.
    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    before_text = card.inner_text()

    # Track full-page navigations: a fragment swap must NOT trigger one.
    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    card.get_by_role("button", name="기록하기").click()
    page.locator("#log-sheet form").get_by_role("button", name="기록 남기기").click()

    # The card re-renders in place (HTMX outerHTML swap on #card-{id}).
    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.innerText !== args.before;
        }""",
        arg={"sel": f"#{card.get_attribute('id')}", "before": before_text},
    )

    assert navigated["count"] == 0, "logging should swap a fragment, not navigate"


def test_tag_selection_survives_fragment_swap(page) -> None:
    """A tag chip selected before submit remains selected after the swap."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("button", name="기록하기").click()

    sheet = page.locator("#log-sheet")
    # Select the first chip in the first tag_group field ("기술").
    first_chip_input = sheet.locator('input[name^="tags_"]').first
    first_chip_label = first_chip_input.locator("xpath=..")
    chip_value = first_chip_input.get_attribute("value")
    first_chip_label.click()
    assert first_chip_input.is_checked()

    sheet.get_by_role("button", name="기록 남기기").click()

    # Reopen the quick-add sheet on the swapped-in card; the same tag should
    # still be checked (selected_tags echo, see create_log).
    card.get_by_role("button", name="기록하기").click()
    reopened_input = page.locator(f'#log-sheet input[value="{chip_value}"]')
    assert reopened_input.is_checked()


def test_chips_wrap_at_360px_and_selected_state_has_non_color_signal(page) -> None:
    """At a 360px viewport, tag chips wrap onto multiple lines (never
    horizontal-scroll), and the selected state is distinguished by more than
    color alone (shape/weight + a glyph via `.chip--selected` /
    `aria-pressed`)."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("button", name="기록하기").click()

    chip_group = page.locator("#log-sheet [id^='tag-group-']").first
    box = chip_group.bounding_box()
    assert box is not None

    # No horizontal overflow at 360px.
    overflow_x = page.evaluate(
        "(el) => el.scrollWidth > el.clientWidth + 1", chip_group.element_handle()
    )
    assert not overflow_x, "tag chips must wrap, not horizontal-scroll, at 360px"

    # Select a chip and confirm the selected-state class + aria-pressed flip
    # (shape/weight + glyph signal, not color alone).
    first_chip_input = chip_group.locator('input[type="checkbox"]').first
    first_chip_label = first_chip_input.locator("xpath=..")
    first_chip_label.click()
    assert first_chip_label.get_attribute("aria-pressed") == "true"
    class_attr = first_chip_label.get_attribute("class") or ""
    assert "chip--selected" in class_attr


def test_chips_wrap_at_1_5x_font_scale(page) -> None:
    """Chip wrapping holds up at a 1.5x browser font-scale (zoom)."""
    _enter_as_guest(page)
    page.evaluate("document.documentElement.style.fontSize = '150%'")

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("button", name="기록하기").click()

    chip_group = page.locator("#log-sheet [id^='tag-group-']").first
    overflow_x = page.evaluate(
        "(el) => el.scrollWidth > el.clientWidth + 1", chip_group.element_handle()
    )
    assert not overflow_x, "tag chips must still wrap at 1.5x font scale"


def test_level_bar_advances_on_log_for_progression_subtally(page) -> None:
    """For a `progression`-mode sub-tally (e.g. 독서), logging an entry that
    crosses a count-gate threshold advances the progress bar fill."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="독서"))
    progress_fill = card.locator(".progress-fill")

    before_width = progress_fill.get_attribute("style") or ""

    card.get_by_role("button", name="기록하기").click()
    page.locator("#log-sheet form").get_by_role("button", name="기록 남기기").click()

    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.getAttribute('style') !== args.before;
        }""",
        arg={"sel": f"#{card.get_attribute('id')} .progress-fill", "before": before_width},
    )
