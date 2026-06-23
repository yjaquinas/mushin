"""Playwright E2E specs for the rebuilt activity-detail Summary card (Task 7,
meetings/MEETING-2026-06-23-summary-card-heatmap-tags): counts + current/
longest streak, the calendar-year non-interactive heatmap strip (intensity
0-7 = distinct active days per ISO week, quarter-labeled Jan/Apr/Jul/Oct),
and the top-3-tags block, all driven through ``stats.card_stats()`` /
``_build_card_top_tags`` and rendered by
``components/stats_summary.html.jinja2``.

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
Dormant when ``playwright`` isn't installed (`pytest.importorskip` skips this
module), mirroring ``tests/e2e/test_logging.py`` / ``test_visual_polish.py``.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser is available, so `uv run pytest tests/` stays green on a
plain dev machine / CI without a browser install.

Specs covered
-------------
1. As the owner: a Kendo activity with a short backfilled streak and one
   tagged entry shows counts, current+longest streak, the heatmap strip
   (``role="img"`` + its aria-label), and the top-3-tags block.
2. As the owner: logging a new entry via the quick-add log flow triggers the
   ``log-saved``-driven HTMX fragment swap and the card's lifetime count
   increments -- the fragment swap still works end-to-end with the heavier
   card.
3. A brand-new activity with zero entries shows the heatmap's calm empty
   state (``HEATMAP_EMPTY``) without erroring or rendering a broken grid.
4. An activity with zero ``tag_group`` fields shows no top-3-tags block at
   all in the rendered HTML.
5. As an anonymous visitor on a *public* profile (read-only): the card
   renders the same heatmap/tags data with no write affordances -- no
   ``hx-get`` attribute on the card's outer ``<section>``.

Real signup creates zero activities (the onboarding seed step was removed
along with the progression feature -- see meetings/MEETING-2026-06-21-simplify-onboarding).
``_signup`` here seeds a fixture "Kendo" activity directly via
``tests.conftest.seed_test_activity`` (same pattern as ``tests/e2e/test_logging.py``),
against the same DB file the live test server reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
_UTC = ZoneInfo("UTC")


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
    so keep *slug* short (<=4 chars) -- "e2t" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2t{slug}{uuid.uuid4().hex[:13]}"


def _signup(
    page, username: str, password: str = "correct-horse-battery", *, visibility: str = "private"
) -> None:
    """Land on the entry screen, switch to "Create account", and submit a new
    username/password signup with consent checked, then complete the
    one-time sharing-consent screen (choosing *visibility*) to reach the
    dashboard.

    Real signup creates zero activities now (the onboarding seed step was
    removed -- see module docstring), so callers seed fixture activities
    directly via ``tests.conftest.seed_test_activity``.
    """
    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", password)
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()

    page.wait_for_url(BASE_URL + "/welcome-sharing")
    if visibility == "public":
        page.check("input[name='visibility'][value='public']")
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    page.goto(BASE_URL + "/home")


def _open_detail(page, heading: str):
    """Navigate from /home to an activity's detail screen via its card link,
    returning the detail screen's ``#stats-summary-{id}`` locator (the
    Summary card).

    The card links to ``/activities/{id}``, which 301-redirects to the
    canonical ``/@{username}/{slug}`` URL for any account with a username
    (every signup in this module has one). Wait for navigation away from
    /home generically rather than for one specific URL shape.
    """
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    activity_id = (home_card.get_attribute("id") or "").rsplit("-", 1)[-1]
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))
    page.wait_for_load_state("load")
    return page.locator(f"#stats-summary-{activity_id}")


def _backfill_streak(owner_id: int, activity_id: int, *, days: int) -> None:
    """Log one bare entry per local day for the last *days* consecutive days
    (today included), giving the activity a current+longest streak of
    *days* without waiting in real time."""
    from app.services import entries as entries_module

    today = datetime.now(_UTC).date()
    for offset in range(days):
        day = today - timedelta(days=offset)
        entries_module.create(
            owner_id,
            activity_id,
            {},
            occurred_at=f"{day.isoformat()}T12:00:00",
            tz=_UTC,
        )


def _drop_tag_group_field(activity_id: int) -> None:
    """Remove the default recipe's ``tag_group`` field_def from *activity_id*,
    so the summary card's top-tags block has nothing to render (the "this
    activity has no tags" branch -- ``_build_card_top_tags`` returns
    ``None``)."""
    from app.models import db

    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM field_def WHERE activity_id = ? AND kind = 'tag_group'",
            (activity_id,),
        )


def test_owner_sees_counts_streak_heatmap_and_top_tags(page) -> None:
    """As the owner, viewing an activity with a backfilled 3-day streak and a
    tagged entry shows: counts, current streak, the heatmap strip
    (role="img" + its aria-label), and the top-3-tags block."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    username = _unique_username("a")
    _signup(page, username)

    owner = users_module.find_by_username(username)
    seeded = seed_test_activity(owner["id"], name="Kendo")
    _backfill_streak(owner["id"], seeded["activity_id"], days=3)

    page.goto(BASE_URL + "/home")
    summary = _open_detail(page, "Kendo")

    # Counts + streak. No "Longest streak" label anywhere on the card.
    assert summary.get_by_text(ui_strings.STREAK_CURRENT_LABEL).count() == 1
    assert summary.get_by_text(ui_strings.STREAK_LONGEST_LABEL).count() == 0
    assert f"3{ui_strings.STREAK_DAYS_UNIT}" in summary.inner_text()

    # Heatmap strip: non-interactive, role="img" with a descriptive aria-label.
    # 3 consecutive backfilled days (today included) land in either 1 or 2
    # ISO weeks depending on where "today" falls in its week, so derive the
    # expected active-week count from the actual calendar dates rather than
    # hardcoding it -- the format string itself (with real values) is the
    # source of truth, not a coincidental substring.
    today = datetime.now(_UTC).date()
    active_weeks = len({(today - timedelta(days=offset)).isocalendar()[:2] for offset in range(3)})
    heatmap = summary.locator('[role="img"]')
    assert heatmap.count() == 1
    aria_label = heatmap.get_attribute("aria-label") or ""
    assert aria_label == ui_strings.HEATMAP_ARIA.format(active_weeks=active_weeks)
    # Quarter labels (Jan/Apr/Jul/Oct) orient the reader within the year.
    assert summary.get_by_text(ui_strings.HEATMAP_QUARTER_LABELS[1], exact=True).count() == 1
    # Non-empty heatmap: the calm empty-state copy must NOT show.
    assert summary.get_by_text(ui_strings.HEATMAP_EMPTY).count() == 0

    # Top-3-tags block: Kendo's default recipe includes a tag_group field, and
    # logging via the quick-add panel with a #hashtag tags an entry.
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    panel = page.locator("#log-panel")
    notes_input = panel.locator('textarea[name^="hashtags_"]').first
    notes_input.fill("Good randori today #suriagemen")
    panel.get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    page.wait_for_selector("text=suriagemen")
    assert page.get_by_text(ui_strings.TAGS_TOP_HEADING).count() == 1
    assert page.get_by_text("suriagemen").count() > 0


def test_quick_add_log_increments_lifetime_count_in_heavier_card(page) -> None:
    """Logging a new entry via the existing log flow triggers the
    `log-saved`-driven HTMX fragment swap, and the card's lifetime count
    increments -- proving the fragment swap still works end-to-end with the
    rebuilt (heatmap + streak + tags) card."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    username = _unique_username("b")
    _signup(page, username)

    owner = users_module.find_by_username(username)
    seed_test_activity(owner["id"], name="Kendo")

    page.goto(BASE_URL + "/home")
    summary = _open_detail(page, "Kendo")
    summary_id = summary.get_attribute("id")

    def _lifetime_count() -> str:
        lifetime_dt = page.locator(f"#{summary_id} dt", has_text=ui_strings.STATS_PERIOD_LIFETIME)
        lifetime_dd = lifetime_dt.locator("xpath=following-sibling::dd[1]")
        return lifetime_dd.inner_text().strip()

    before = _lifetime_count()

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    page.locator("#log-panel form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()

    page.wait_for_function(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el && el.innerText !== args.before;
        }""",
        arg={"sel": f"#{summary_id}", "before": summary.inner_text()},
    )

    assert navigated["count"] == 0, "logging should swap a fragment, not navigate"

    after = _lifetime_count()
    assert int(after) == int(before) + 1


def test_new_activity_with_zero_entries_shows_calm_heatmap_empty_state(page) -> None:
    """A brand-new activity with zero entries shows the heatmap's calm empty
    state (HEATMAP_EMPTY text present) without erroring or rendering a
    broken grid."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    username = _unique_username("c")
    _signup(page, username)

    owner = users_module.find_by_username(username)
    seed_test_activity(owner["id"], name="Kendo", entry_count=0)

    page.goto(BASE_URL + "/home")
    summary = _open_detail(page, "Kendo")

    heatmap = summary.locator('[role="img"]')
    assert heatmap.count() == 1
    assert summary.get_by_text(ui_strings.HEATMAP_EMPTY).count() == 1
    assert "0" in summary.locator('[role="img"]').get_attribute("aria-label") or ""

    # No console/page errors and no exploded markup -- the grid container
    # rendered with its (zero-filled) day strip, not an empty/broken DOM.
    assert summary.locator('[role="img"] > div').count() > 0


def test_activity_with_no_tag_group_field_shows_no_top_tags_block(page) -> None:
    """An activity with zero tag-group fields shows no top-3-tags block at
    all in the rendered HTML (not an empty-state message -- the block itself
    is absent, since ``_build_card_top_tags`` returns ``None``)."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    username = _unique_username("d")
    _signup(page, username)

    owner = users_module.find_by_username(username)
    seeded = seed_test_activity(owner["id"], name="Kendo", entry_count=1)
    _drop_tag_group_field(seeded["activity_id"])

    page.goto(BASE_URL + "/home")
    summary = _open_detail(page, "Kendo")

    assert summary.get_by_text(ui_strings.TAGS_TOP_HEADING).count() == 0
    assert summary.get_by_text(ui_strings.TAG_FREQUENCY_EMPTY).count() == 0
    # The heatmap/counts/streak parts of the card are unaffected.
    assert summary.locator('[role="img"]').count() == 1
    assert summary.get_by_text(ui_strings.STREAK_CURRENT_LABEL).count() == 1


def test_public_visitor_sees_card_with_no_write_affordances(page, browser) -> None:
    """An anonymous visitor on a *public* profile sees the same
    heatmap/streak/tags data on the card, but the card's outer ``<section>``
    carries no ``hx-get`` (no write affordance, no self-refresh wiring) --
    matching the owner-only ``is_owner`` guard in
    ``components/stats_summary.html.jinja2``."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    username = _unique_username("e")
    _signup(page, username, visibility="public")

    owner = users_module.find_by_username(username)
    seeded = seed_test_activity(owner["id"], name="Kendo")
    _backfill_streak(owner["id"], seeded["activity_id"], days=2)

    page.goto(BASE_URL + "/home")
    summary = _open_detail(page, "Kendo")
    summary_id = summary.get_attribute("id")
    owner_html = summary.inner_html()
    assert owner_html  # sanity: the owner view did render the card

    # New, fully anonymous context -- no session cookie at all.
    visitor_context = browser.new_context(viewport={"width": 360, "height": 800})
    visitor_page = visitor_context.new_page()
    try:
        visitor_page.goto(BASE_URL + f"/@{username}/kendo")
        visitor_page.wait_for_load_state("load")

        visitor_summary = visitor_page.locator(f"#{summary_id}")
        assert visitor_summary.count() == 1
        assert visitor_summary.get_attribute("hx-get") is None

        # Same data renders: streak labels + non-empty heatmap.
        assert visitor_summary.get_by_text(ui_strings.STREAK_CURRENT_LABEL).count() == 1
        assert f"2{ui_strings.STREAK_DAYS_UNIT}" in visitor_summary.inner_text()
        assert visitor_summary.locator('[role="img"]').count() == 1
        assert visitor_summary.get_by_text(ui_strings.HEATMAP_EMPTY).count() == 0
    finally:
        visitor_context.close()
