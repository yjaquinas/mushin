"""Playwright E2E specs for the calendar "selected day" affordance (month and
week views): tapping a ``.cal-day`` cell swaps the calendar body to a
day-detail state showing that day's entries inline, all via an HTMX fragment
swap (no full navigation).

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

As of Task 5 (persistent-header / swappable-body restructure), selecting a
day swaps the whole calendar body to a *mutually exclusive* state: the grid
(and the full-period log) is removed from the DOM entirely, replaced by a
"Calendar" back-control + only that day's entries. There is no longer a
state where a cell carries ``cal-day--selected`` while the grid is visible
on screen -- the grid disappears the moment a day is selected. Specs that
previously asserted ``cal-day--selected`` on a still-visible grid now assert
the day-detail body state instead (back-control + day panel present, grid +
full-period log absent), and "deselect" is exercised via the back-control
rather than re-tapping a (now-absent) grid cell.

Specs covered
-------------
1. Tapping a date in the month view swaps to the day-detail body state and
   renders that day's entries (or the empty state) inline, in the same HTMX
   interaction — no full page navigation.
2. Tapping a different date while a day's detail is showing (via the back
   control, then a new tap) selects that one instead.
3. A date that has a logged entry shows ``cal-day--marked`` before it's
   tapped; after tapping, the day-detail panel for that day renders the
   logged entry.
4. Navigating to the next/prev month, or switching period tabs, lands back
   on the default (grid + full-period log) body state -- no day detail.
5. On first load of the month view (no tap yet), no cell carries
   ``cal-day--selected`` and the grid + full-period log are visible.
6. Tapping the "Calendar" back-control from the day-detail state restores
   the default body state (grid + full-period log back, day detail gone).
7. Switching to week view and tapping a day in the week strip behaves
   identically to month view's day tap (Task 4 build-plan item: week's day
   cells previously had no tap affordance at all).
8. Selecting a day removes the month grid and the full-period log from the
   DOM entirely (not just visually hidden) -- only the back-control and that
   day's entries remain. Tapping the "Calendar" back-control restores the
   grid + full-period log at the same period/anchor, and the day detail is
   gone again (Task 5 build-plan item: persistent header / swappable body).
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
    cal-day--selected."""
    username = _unique_username("a")
    _signup(page, username)

    _open_detail(page, "Kendo")

    assert page.locator(".cal-day--selected").count() == 0


def test_tapping_a_day_selects_it_and_renders_entries_inline(page) -> None:
    """Tapping a date in the month view swaps to the day-detail body state
    and renders that day's entries (here: the empty state, since no entry
    was logged) inline via an HTMX fragment swap -- no full navigation. The
    grid disappears entirely once a day is selected (Task 5)."""
    username = _unique_username("b")
    _signup(page, username)

    _open_detail(page, "Kendo")

    navigated = _track_navigations(page)

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")
    assert navigated["count"] == 0, "tapping a calendar day should swap a fragment, not navigate"

    # The grid is gone entirely in the day-detail state -- not merely
    # unselected.
    assert page.locator(".cal-day").count() == 0
    assert page.locator("table").count() == 0
    assert page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR).count() == 1


def test_tapping_a_second_day_after_returning_to_calendar_selects_it(page) -> None:
    """Selecting a date, returning to the calendar via the back-control, then
    selecting a different date renders that second date's detail instead --
    one day's detail is shown at a time."""
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
    # The day-entries heading reads "{title} — {YYYY-MM-DD}" -- capture the
    # full panel heading text so it can be compared against the second tap's.
    first_panel_text = page.locator(
        "h4", has_text=ui_strings.CALENDAR_DAY_ENTRIES_TITLE
    ).inner_text()

    page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR).click()
    page.wait_for_selector("table")

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
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE} — ")
    second_panel_text = page.locator(
        "h4", has_text=ui_strings.CALENDAR_DAY_ENTRIES_TITLE
    ).inner_text()

    assert second_label != first_label
    assert second_panel_text != first_panel_text


def test_marked_day_shows_logged_entry_when_selected(page) -> None:
    """A date with a logged entry shows cal-day--marked in the default grid
    state; tapping it swaps to the day-detail state showing that entry."""
    username = _unique_username("d")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    marked_day = page.locator(".cal-day--marked").first
    marked_day.click()

    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")
    assert page.locator(".cal-day--marked").count() == 0, "grid is gone in the day-detail state"


def test_changing_month_returns_to_default_body_state(page) -> None:
    """Navigating to the next/prev month while a day's detail is showing
    lands back on the default body state -- grid + full-period log restored,
    no day detail."""
    username = _unique_username("e")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    page.get_by_role("button", name=ui_strings.CALENDAR_NEXT_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0
    assert page.locator("table").count() == 1

    page.get_by_role("button", name=ui_strings.CALENDAR_PREV_MONTH).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.locator("table").count() == 1


def test_switching_period_tabs_returns_to_default_body_state(page) -> None:
    """Switching period tabs (e.g. month -> week -> month) while a day's
    detail is showing lands back on the default body state -- no day detail,
    grid restored."""
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
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0
    assert page.locator("table").count() == 1


def test_back_control_restores_default_body_state(page) -> None:
    """Tapping the "Calendar" back-control from the day-detail state restores
    the default body state: grid + full-period log back, day detail gone."""
    username = _unique_username("g")
    _signup(page, username)

    _open_detail(page, "Kendo")

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_EMPTY}")

    page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR).click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".cal-day--selected").count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_EMPTY).count() == 0
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0
    assert page.locator("table").count() == 1


def test_week_view_day_tap_selects_it_and_renders_entries_inline(page) -> None:
    """Tapping a day in the week strip (Task 4 build-plan item) behaves like
    month view's day tap: it swaps to the day-detail body state and renders
    that day's entries inline via an HTMX fragment swap, no full navigation
    -- exercising the week-specific gap this task closes (week's day cells
    previously weren't interactive at all). The week strip disappears
    entirely once a day is selected (Task 5), same as the month grid."""
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

    # The week strip is gone entirely in the day-detail state.
    assert page.locator(".cal-day").count() == 0
    assert page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR).count() == 1


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
    # the day-detail panel (back-control still present) intact throughout.
    edited_row = page.locator("li.entry-row").first
    comment_toggle = edited_row.locator("button[hx-get*='/comments']")
    assert comment_toggle.count() == 1
    comment_toggle.click()
    page.wait_for_selector("textarea[name='body']")
    page.fill("textarea[name='body']", "noted from the merged calendar")
    page.get_by_role("button", name=ui_strings.COMMENTS_SUBMIT).click()

    page.wait_for_selector("text=noted from the merged calendar")
    # Still inside the day-detail state -- the back-control is present and
    # the grid never came back.
    assert page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR).count() == 1
    assert page.locator("table").count() == 0


def test_selecting_a_day_hides_grid_and_log_then_back_control_restores_them(page) -> None:
    """Selecting a day swaps to a mutually-exclusive body state: the month
    grid and the full-period log are removed from the DOM entirely (not
    merely hidden), leaving only the back-control + that day's entries.
    Tapping the "Calendar" back-control restores the grid + full-period log
    at the same period/anchor, and the day-entries panel is gone again."""
    username = _unique_username("i")
    _signup(page, username)

    _open_detail(page, "Kendo")
    _log_entry_today(page)

    # Default state: month grid (a <table>) and the full-period log are both
    # present. The day-entries panel is absent.
    assert page.locator("table").count() == 1
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0

    today_cell = page.locator(".cal-day--today").first
    today_cell.click()
    page.wait_for_selector(f"text={ui_strings.CALENDAR_DAY_ENTRIES_TITLE}")

    # Selected-day state: the month grid table and the full-period log are
    # both gone from the DOM, not just hidden -- only the back-control and
    # that day's entries remain.
    assert page.locator("table").count() == 0
    assert page.get_by_text(ui_strings.HISTORY_LOG_EMPTY).count() == 0
    back_button = page.get_by_role("button", name=ui_strings.CALENDAR_BACK_TO_CALENDAR)
    assert back_button.count() == 1

    navigated = _track_navigations(page)
    back_button.click()
    page.wait_for_selector("table")
    assert navigated["count"] == 0, "the back-control should swap a fragment, not navigate"

    # Back to default state: grid restored, day-entries panel gone again.
    assert page.locator("table").count() == 1
    assert page.get_by_text(ui_strings.CALENDAR_DAY_ENTRIES_TITLE).count() == 0
    assert page.locator(".cal-day--marked").count() == 1
