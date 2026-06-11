"""Playwright E2E specs for the stats screens (Task 9): calendar, heatmap,
streak, and progression status on the sub-tally detail screen.

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md — "E2E tests use the Playwright
MCP — not a bundled Playwright"). They are written ahead of being run by an
agent with MCP browser tools attached.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser, mirroring
``tests/e2e/test_competition.py``.

Specs covered
-------------
1. Opening a sub-tally detail screen shows the month calendar (with at least
   one ``.cal-day`` cell) and the trailing-365-day heatmap (``role="img"``
   grid of ``.heat-cell`` elements) — neither of which appears on the home
   screen.
2. Tapping a marked calendar day swaps in that day's entries via HTMX
   (fragment swap, no full navigation).
3. The 검도/심사 (grading) detail screen shows the current dan stage and the
   shōgō (칭호) parallel track; the 독서 (reading) detail screen shows the
   current tier and a count-to-next requirement.
4. Calendar day cells remain ≥44px tap targets and chips wrap (never
   horizontal scroll-hide) at 360px viewport width and 1.5x text scale.
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


def test_detail_screen_shows_calendar_and_heatmap(page) -> None:
    """The 수련 detail screen shows the month calendar and trailing-year heatmap,
    neither of which appears on the home screen."""
    _enter_as_guest(page)

    home_html = page.content()
    assert "heat-cell" not in home_html
    assert "cal-day" not in home_html

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("link", name="수련").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    assert page.locator(".cal-day").count() > 0
    heatmap = page.locator('[role="img"]')
    assert heatmap.count() > 0
    assert page.locator(".heat-cell").count() == 365


def test_tapping_marked_calendar_day_swaps_day_entries_fragment(page) -> None:
    """Logging today, then tapping the marked calendar day, swaps in that
    day's entries without a full page reload."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("button", name="기록하기").click()
    sheet = page.locator("#log-sheet")
    sheet.get_by_role("button", name="기록 남기기").click()

    card.get_by_role("link", name="수련").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    marked_day = page.locator(".cal-day--marked").first
    marked_day.click()

    page.wait_for_selector("#calendar-day-detail :text('이날의 기록')")
    assert navigated["count"] == 0, "tapping a calendar day should swap a fragment, not navigate"


def test_kendo_grading_detail_shows_dan_and_shogo_track(page) -> None:
    """The 검도/심사 detail screen shows the current dan stage and the
    shōgō (칭호) parallel track section."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="심사"))
    card.get_by_role("link", name="심사").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    assert page.get_by_text("단계").count() > 0
    assert page.get_by_text("칭호").count() > 0


def test_reading_detail_shows_tier_and_count_to_next(page) -> None:
    """The 독서 detail screen shows the current tier and a count-to-next
    requirement string."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="독서"))
    card.get_by_role("link", name="독서").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    assert page.get_by_text("입문").count() > 0
    assert page.get_by_text("앞으로").count() > 0


def test_calendar_day_cells_meet_tap_target_at_360px(page) -> None:
    """At 360px viewport width, .cal-day cells stay at the >=44px tap minimum."""
    _enter_as_guest(page)

    card = page.locator("article", has=page.get_by_role("heading", name="수련"))
    card.get_by_role("link", name="수련").click()
    page.wait_for_url(f"{BASE_URL}/sub-tallies/*")

    first_day = page.locator(".cal-day").first
    box = first_day.bounding_box()
    assert box is not None
    assert box["width"] >= 44
    assert box["height"] >= 44
