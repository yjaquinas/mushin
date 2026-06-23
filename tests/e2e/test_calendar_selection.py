"""Playwright E2E specs for the calendar "selected day" affordance (month and
week views): tapping a ``.cal-day`` cell swaps the log area below the
always-visible grid/strip to a day-detail state showing that day's entries
inline, all via an HTMX fragment swap (no full navigation).

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

This docstring previously claimed a fresh signup is lazy-seeded with the
kendo + reading starter templates via ``app.auth.routes._lazy_seed``. That
seam, the onboarding templates, and the progression feature they
demonstrated have all been removed (meetings/MEETING-2026-06-21-simplify-onboarding);
a fresh signup now has zero activities. ``_signup`` here seeds a fixture
"Kendo" activity directly via ``tests.conftest.seed_test_activity`` (the same
pattern used in ``tests/e2e/test_entry_comments.py`` and
``tests/e2e/test_comment_notifications.py``) so these specs still have a card
to exercise.

As of the calendar-selection rework (history.html.jinja2's persistent
grid/swappable-log-area restructure), selecting a day no longer removes the
month grid / week strip from the DOM. The period visual (table or week strip)
ALWAYS renders, regardless of day selection. Only the log area *below* the
visual swaps between two mutually exclusive states:
  - no day selected (the default): the full-period log
    (components/period_log.html.jinja2).
  - a day selected: a "Clear selection" control followed by *only* that
    day's entries (components/day_entries.html.jinja2, ``#calendar-day-detail``).

The tapped day's cell carries both the ``cal-day--selected`` class and
``aria-pressed="true"``. Tapping an already-selected cell toggles the
selection off (same effect as clicking "Clear selection") rather than
re-selecting it, since its own ``hx-get`` omits ``&day=...`` while selected.

Specs covered
-------------
1. Tapping a date in the month view keeps the grid in the DOM, marks that
   cell ``cal-day--selected`` / ``aria-pressed="true"``, and renders the
   day-detail panel (``#calendar-day-detail``) below it instead of the
   full-period log.
2. Tapping a different date while a day's detail is showing (without
   clearing first) selects that one instead.
3. A date that has a logged entry shows ``cal-day--marked`` before it's
   tapped; after tapping, the day-detail panel for that day renders the
   logged entry, and the grid (with the mark) is still visible.
4. Navigating to the next/prev month, or switching period tabs, lands back
   on the default (no day selected, full-period log) body state.
5. On first load of the month view (no tap yet), no cell carries
   ``cal-day--selected`` and the grid + full-period log are visible.
6. Clicking "Clear selection" from the day-detail state restores the
   full-period log, the grid is still present, and no cell is marked
   ``cal-day--selected``.
7. Re-tapping the already-selected day clears the selection -- same effect
   as the "Clear selection" control.
8. Switching to week view and tapping a day in the week strip behaves
   identically to month view's day tap (the week strip stays visible, the
   day-detail panel renders below it).
9. After a day-select swap, focus lands on the day-detail panel
   (``#calendar-day-detail``), per ``data-history-focus`` /
   ``hx-on::after-swap`` in components/history.html.jinja2.
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
    cal-day--selected, and the grid + full-period log are both visible."""
    username = _unique_username("a")
    _signup(page, username)

    _open_detail(page, "Kendo")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("table").count() == 1
    assert page.locator("#calendar-day-detail").count() == 0


def test_tapping_a_day_keeps_grid_and_renders_entries_inline(page) -> None:
    """Tapping a date in the month view keeps the grid in the DOM, marks the
    tapped cell selected, and renders the day-detail panel below it via an
    HTMX fragment swap -- no full navigation."""
    username = _unique_username("b")
    _signup(page, username)

    _open_detail(page, "Kendo")

    navigated = _track_navigations(page)

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")
    assert navigated["count"] == 0, "tapping a calendar day should swap a fragment, not navigate"

    # The grid is still present -- only the log area below it swapped.
    assert page.locator("table").count() == 1
    assert page.locator(".cal-day").count() > 0

    selected_cell = page.locator(".cal-day--today").first
    assert "cal-day--selected" in (selected_cell.get_attribute("class") or "")
    assert selected_cell.get_attribute("aria-pressed") == "true"

    assert page.locator("#calendar-day-detail").count() == 1
    heading = page.locator("#calendar-day-detail h4")
    assert ui_strings.CALENDAR_DAY_ENTRIES_TITLE in heading.inner_text()


def test_tapping_a_second_day_selects_it_instead(page) -> None:
    """Tapping a different date while a day's detail is showing (without
    clearing first) selects that one instead -- one day's detail is shown at
    a time, and the previously-selected cell is no longer marked."""
    username = _unique_username("c")
    _signup(page, username)

    _open_detail(page, "Kendo")

    all_days = page.locator(".cal-day")
    day_count = all_days.count()
    assert day_count >= 2, "expected at least two day cells in the month grid"

    first_day = all_days.nth(0)
    first_label = first_day.inner_text().strip()
    first_day.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE} — ")
    first_panel_text = page.locator("#calendar-day-detail h4").inner_text()

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
    page.wait_for_load_state("networkidle")
    second_panel_text = page.locator("#calendar-day-detail h4").inner_text()

    assert second_label != first_label
    assert second_panel_text != first_panel_text

    # Only one cell should be marked selected at a time.
    assert page.locator(".cal-day--selected").count() == 1


def test_marked_day_shows_logged_entry_when_selected(page) -> None:
    """A date with a logged entry shows cal-day--marked in the grid; tapping
    it keeps the grid (with the mark) visible and shows that entry in the
    day-detail panel below it."""
    username = _unique_username("d")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    marked_day = page.locator(".cal-day--marked").first
    marked_day.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")
    # The grid (and the mark) is still present alongside the day-detail panel.
    assert page.locator(".cal-day--marked").count() == 1
    assert page.locator("#calendar-day-detail").count() == 1


def test_changing_month_returns_to_default_body_state(page) -> None:
    """Navigating to the next/prev month while a day's detail is showing
    lands back on the default body state -- full-period log restored, no day
    detail, grid (still) present throughout."""
    username = _unique_username("e")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    page.get_by_role("button", name=ui_strings.CALENDAR_NEXT_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("#calendar-day-detail").count() == 0
    assert page.locator("table").count() == 1

    page.get_by_role("button", name=ui_strings.CALENDAR_PREV_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("table").count() == 1


def test_switching_period_tabs_returns_to_default_body_state(page) -> None:
    """Switching period tabs (e.g. month -> week -> month) while a day's
    detail is showing lands back on the default body state -- no day detail,
    grid restored at the new period."""
    username = _unique_username("f")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")

    page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_WEEK).click()
    page.wait_for_load_state("networkidle")

    page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("#calendar-day-detail").count() == 0
    assert page.locator("table").count() == 1


def test_clear_selection_restores_default_body_state(page) -> None:
    """Clicking "Clear selection" from the day-detail state restores the
    full-period log; the grid stays present throughout and no cell remains
    marked selected."""
    username = _unique_username("g")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")
    assert page.locator("table").count() == 1

    navigated = _track_navigations(page)
    page.get_by_role("button", name=ui_strings.HISTORY_CLEAR_SELECTION).click()
    page.wait_for_selector(f"text={ui_strings.HISTORY_LOG_EMPTY}")
    assert navigated["count"] == 0, "clear-selection should swap a fragment, not navigate"

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("#calendar-day-detail").count() == 0
    assert page.locator("table").count() == 1


def test_retapping_selected_day_clears_selection(page) -> None:
    """Re-tapping the already-selected day cell clears the selection -- the
    same effect as clicking "Clear selection" -- without needing the explicit
    control."""
    username = _unique_username("k")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")
    assert "cal-day--selected" in (
        page.locator(".cal-day--today").first.get_attribute("class") or ""
    )

    navigated = _track_navigations(page)
    page.locator(".cal-day--today").first.click()
    page.wait_for_selector(f"text={ui_strings.HISTORY_LOG_EMPTY}")
    assert navigated["count"] == 0, "re-tapping a selected day should swap a fragment, not navigate"

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("#calendar-day-detail").count() == 0
    today_cell_after = page.locator(".cal-day--today").first
    assert today_cell_after.get_attribute("aria-pressed") == "false"
    assert page.locator("table").count() == 1


def test_week_view_day_tap_keeps_strip_and_renders_entries_inline(page) -> None:
    """Tapping a day in the week strip behaves like month view's day tap: the
    strip stays in the DOM, the tapped cell is marked selected, and the
    day-detail panel renders below it via an HTMX fragment swap, no full
    navigation."""
    username = _unique_username("h")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_WEEK).click()
    page.wait_for_load_state("networkidle")

    navigated = _track_navigations(page)

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")
    assert navigated["count"] == 0, "tapping a week-strip day should swap a fragment, not navigate"

    # The week strip is still present; the day-detail panel renders below it.
    assert page.locator(".cal-day").count() > 0
    selected_cell = page.locator(".cal-day--today").first
    assert "cal-day--selected" in (selected_cell.get_attribute("class") or "")
    assert selected_cell.get_attribute("aria-pressed") == "true"
    assert page.locator("#calendar-day-detail").count() == 1


def test_focus_lands_on_day_detail_panel_after_day_select_swap(page) -> None:
    """After a day-select fragment swap, focus lands on the day-detail panel
    (#calendar-day-detail) per the after-swap focus script in
    components/history.html.jinja2 -- not on the period tab or anywhere
    else."""
    username = _unique_username("m")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    focused_id = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused_id == "calendar-day-detail"
    assert page.locator("#calendar-day-detail:focus").count() == 1


def test_owner_can_edit_and_comment_on_an_entry_from_the_day_detail_panel(page) -> None:
    """Selecting a day in the merged calendar surfaces both write affordances
    on the same entry row -- the owner-gated edit pencil (Task 6) and the
    comment toggle (Task 6/8) -- and both should keep working on that row
    after an edit-save, not just on first render.

    KNOWN FAILING as of this audit (test-engineer, 2026-06-21) -- flagging,
    not fixing, per this task's tests-only constraint:

    ``update_entry``/``cancel_entry_edit`` in app/routes/web.py re-render the
    row via ``_render_entry_row`` -> ``components/entry_row.html.jinja2``, a
    stale fragment that predates the calendar/log merge. It never carries
    ``history`` (is_owner/can_comment/username/slug) and the entry dict it's
    given (``entries.get(...)``) is never decorated with ``comment_count`` by
    that route either, so the comment toggle (and the live comment count)
    silently disappears from a row the instant it's edited or an edit is
    cancelled -- in BOTH the day-detail panel (this test) and the full
    period log (components/period_log.html.jinja2), since both share the
    same ``hx-target="closest .entry-row"`` edit/cancel routes. This needs an
    app-code fix (route + entry_row.html.jinja2), not a test change."""
    username = _unique_username("j")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")

    entry_row = page.locator("li.entry-row").first
    assert entry_row.count() == 1

    # Edit: the pencil opens the inline edit form, editing the notes persists
    # and the row re-renders with the new text, still inside the day-detail
    # panel (no navigation away from it). Kendo has two tag_group fields
    # (Technique, Location), each rendering its own "Notes"-labeled textarea
    # (components/tag_group.html.jinja2, name="hashtags_{field_id}") rather
    # than a standalone "memo" field. Editing swaps the whole .entry-row <li>
    # (hx-target="closest .entry-row", hx-swap="outerHTML"), so re-locate
    # fresh after the click rather than reuse the pre-edit locator -- select
    # the textarea by its name prefix (get_by_label flakily fails to
    # associate this label/textarea pair in this template).
    entry_row.get_by_role("button", name=ui_strings.ENTRY_EDIT).click()
    page.wait_for_selector("li.entry-row form")
    notes_field = page.locator("li.entry-row form textarea[name^='hashtags_']").first
    notes_field.fill("edited from the calendar")
    page.get_by_role("button", name=ui_strings.ENTRY_SAVE).click()
    page.wait_for_selector("text=edited from the calendar")

    # Comment: the toggle on that same (now-edited) row opens the thread
    # composer and posting a comment renders it via a fragment swap, with
    # the day-detail panel intact throughout.
    edited_row = page.locator("li.entry-row").first
    comment_toggle = edited_row.locator("button[hx-get*='/comments']")
    assert comment_toggle.count() == 1
    comment_toggle.click()
    page.wait_for_selector("textarea[name='body']")
    page.fill("textarea[name='body']", "noted from the merged calendar")
    page.get_by_role("button", name=ui_strings.COMMENTS_SUBMIT).click()

    page.wait_for_selector("text=noted from the merged calendar")
    # Still inside the day-detail state -- the panel and the grid are both
    # present.
    assert page.locator("#calendar-day-detail").count() == 1
    assert page.locator("table").count() == 1


def test_selecting_a_day_swaps_only_the_log_area_then_clear_restores_it(page) -> None:
    """Selecting a day swaps only the log area below the grid: the month
    grid stays in the DOM throughout, the full-period log is replaced by the
    day-detail panel, and clicking "Clear selection" restores the
    full-period log at the same period/anchor with the day-entries panel
    gone again."""
    username = _unique_username("i")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    # Default state: month grid (a <table>) and the full-period log are both
    # present. The day-entries panel is absent.
    assert page.locator("table").count() == 1
    assert page.locator("#calendar-day-detail").count() == 0

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")

    # Selected-day state: the grid is still present (with the mark intact);
    # the full-period log has been replaced by the day-detail panel.
    assert page.locator("table").count() == 1
    assert page.locator(".cal-day--marked").count() == 1
    assert page.get_by_text(ui_strings.HISTORY_LOG_EMPTY).count() == 0
    clear_button = page.get_by_role("button", name=ui_strings.HISTORY_CLEAR_SELECTION)
    assert clear_button.count() == 1

    navigated = _track_navigations(page)
    clear_button.click()
    # An entry was logged today (_log_entry_today), so the full-period log
    # is non-empty -- wait for the day-detail panel to disappear rather than
    # for HISTORY_LOG_EMPTY, which only renders when the period log is empty.
    page.wait_for_selector("#calendar-day-detail", state="detached")
    assert navigated["count"] == 0, "clear-selection should swap a fragment, not navigate"

    # Back to default state: grid still present, day-entries panel gone
    # again, mark still intact.
    assert page.locator("table").count() == 1
    assert page.locator("#calendar-day-detail").count() == 0
    assert page.locator(".cal-day--marked").count() == 1
