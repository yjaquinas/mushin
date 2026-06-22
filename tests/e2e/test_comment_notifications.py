"""Playwright E2E specs for the comment-notification feature (Task 4 of
``meetings/MEETING-2026-06-20-comment-notifications/3-BUILD-PLAN.md``).

Same dormant ``pytest`` + ``playwright.sync_api`` pattern as
``tests/e2e/test_entry_comments.py`` / ``tests/e2e/test_fellows_e2e.py`` --
unrelated to the agent-driven ``playwright-cli`` skill. Skipped outright when
no Playwright browser is available, so ``uv run pytest tests/`` stays green on
a plain dev machine / CI without a browser.

Specs covered
-------------
1. The entry owner can open a thread on their own activity-detail page and
   post a comment to it via the browser (no fellow/visitor involved).
2. The unseen-comment badge persists across repeated ``/home`` visits after a
   fellow comments, and only clears once the owner visits ``/comments``.
3. Clicking a row on ``/comments`` lands the owner on their own
   activity-detail page with that entry's day pre-selected in the merged
   calendar and its comment thread auto-expanded (no manual day-tap or
   toggle-click needed) -- driven by ``?c={entry_id}`` against
   ``components/day_entries.html.jinja2``.
4. A fellow's past comment remains visible in the owner's ``/comments`` feed
   even after the owner blocks that fellow.

What's *not* duplicated here (already covered at the HTTP level)
------------------------------------------------------------------
- Watermark read-then-stamp ordering, ``is_new`` computation, the
  excludes-soft-deleted / excludes-self-comments filters, ``before_id``
  keyset pagination, and per-owner isolation of
  ``list_comments_for_owner`` -- ``tests/unit/test_comments.py``.
- The owner-view ``can_comment``/zero-comment-glyph wiring, the ``?c=``
  auto-expand (valid/invalid/cross-activity), and the home-badge
  persists-then-clears-via-/comments HTTP round trip --
  ``tests/integration/test_web.py`` and
  ``tests/integration/test_entry_comments.py``
  (``test_home_badge_persists_across_home_loads_and_clears_via_comments_page``).
- Anonymous ``/comments`` redirect-to-login -- covered at the HTTP level
  alongside the ``home`` anonymous-redirect test; not re-driven through a
  browser here since it's a plain unauthenticated-redirect check with no
  browser-only behavior to exercise.

This file only adds specs that need a real browser: client-side composer
interaction, multi-visit badge persistence as actually rendered, and the
click-through landing + scroll behavior.
"""

from __future__ import annotations

import uuid

import pytest

from app import ui_strings

pytestmark = pytest.mark.e2e

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


def _unique_username(slug: str) -> str:
    """A username that's unique per test run, so reruns against the
    persistent dev DB never collide with a leftover row from a previous run.
    Usernames are capped at 20 chars (``app.auth.routes._normalize_username``),
    so keep *slug* short (<=7 chars): "e2n" (3) + slug + 8 hex chars stays
    within the cap."""
    return f"e2n{slug}{uuid.uuid4().hex[:8]}"


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a new
    username/password signup with consent checked."""
    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", password)
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()


def _make_user(browser, username: str, *, visibility: str = "private"):
    """Create a fresh browser context, sign up *username*, pick *visibility* on
    the one-time consent screen, and return the logged-in ``(context, page)``
    sitting on its own ``/@{username}`` profile.

    Also creates a fixture "Kendo" activity directly via
    ``tests.conftest.seed_test_activity`` -- real signup never creates any
    activities itself (see ``tests/e2e/test_entry_comments.py``'s module
    docstring for the underlying gap). This call hits the same DB file the
    live test server reads, so the row is visible to the next request the
    browser makes.
    """
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    if visibility == "public":
        page.locator("input[name='visibility'][value='public']").check()
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    owner = users_module.find_by_username(username)
    seed_test_activity(owner["id"], name="Kendo")

    return context, page


def _open_detail(page, heading: str):
    """Navigate from /home to a sub-tally's detail screen via its card link."""
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))


def _log_one_entry(page) -> None:
    """From the owner's own Kendo detail screen, log one bare entry so the
    detail page has an entry row to comment on."""
    page.goto(BASE_URL + "/home")
    _open_detail(page, "Kendo")
    page.get_by_role("button", name=ui_strings.SUBTALLY_LOG_BUTTON).click()
    page.locator("#log-panel form").get_by_role("button", name=ui_strings.LOG_SUBMIT).click()
    page.wait_for_load_state("networkidle")


def _first_entry_id(page, profile_path: str) -> str:
    """Visit *profile_path* and return the numeric id of the first logged
    entry, read off its stable ``comment-slot-{id}`` div."""
    page.goto(BASE_URL + profile_path)
    page.wait_for_load_state("networkidle")
    slot_id = page.locator("[id^='comment-slot-']").first.get_attribute("id")
    return slot_id.rsplit("-", 1)[-1]


def _connect_as_fellows(owner_page, owner_username: str, fellow_page, fellow_username: str) -> None:
    """Drive the full request -> accept handshake through the browser,
    including both sides' sharing-consent confirm step, so the two accounts
    end up at full ``connected`` (sharing_consent_at set both ways) -- the
    private owner profiles used in this module require that for the fellow
    to gain comment access.

    NOTE: the incoming-request Accept/Decline rows are collapsed behind an
    Alpine ``x-show`` "Requests (N)" toggle (``requests_cluster.html.jinja2``)
    that must be expanded with a click before the Accept button is reachable
    -- ``tests/e2e/test_fellows_e2e.py::test_connect_accept_fellow_then_remove``
    clicks ``REQUESTS_ACCEPT`` directly without this expand step and times
    out as a result (a pre-existing gap, not introduced here; flagged
    separately rather than silently fixed in this build's scope).
    """
    fellow_page.goto(BASE_URL + f"/@{owner_username}")
    fellow_page.get_by_role("button", name=ui_strings.CONNECT_ACTION).click()
    fellow_page.get_by_role("button", name=ui_strings.SHARING_CONSENT_CONFIRM).click()
    fellow_page.wait_for_selector(f"text={ui_strings.CONNECT_REQUESTED}")

    owner_page.goto(BASE_URL + "/home")
    owner_page.get_by_role("button", name=ui_strings.REQUESTS_HEADING, exact=False).click()
    owner_page.get_by_role("button", name=ui_strings.REQUESTS_ACCEPT).click()
    owner_page.get_by_role("button", name=ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT).click()
    owner_page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# 1. Owner posts a comment on their own entry via the browser
# ---------------------------------------------------------------------------


def test_owner_can_post_comment_on_own_entry_via_browser(browser) -> None:
    username_owner = _unique_username("o1")
    owner_ctx, owner_page = _make_user(browser, username_owner)
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(owner_page, f"/@{username_owner}/kendo")

        owner_page.goto(BASE_URL + f"/@{username_owner}/kendo")
        owner_page.wait_for_load_state("networkidle")

        # Zero-comment entry still renders the toggle (can_comment is True
        # for the owner) so a brand-new thread is reachable from the UI.
        glyph = owner_page.locator(f"button[hx-get*='/entries/{entry_id}/comments']")
        assert glyph.count() == 1
        glyph.click()
        owner_page.wait_for_selector(f"#comment-thread-{entry_id} textarea")

        owner_page.fill(f"#comment-thread-{entry_id} textarea", "Noting my own progress here")
        owner_page.locator(f"#comment-thread-{entry_id} form").get_by_role(
            "button", name=ui_strings.COMMENTS_SUBMIT
        ).click()

        owner_page.wait_for_selector("text=Noting my own progress here")
    finally:
        owner_ctx.close()


# ---------------------------------------------------------------------------
# 2. Badge persists across home revisits; clears only via /comments
# ---------------------------------------------------------------------------


def test_badge_persists_across_home_visits_and_clears_only_via_comments_page(browser) -> None:
    from app.auth import users as users_module
    from app.models import db
    from app.services import comments as comments_service

    username_owner = _unique_username("o2")
    username_fellow = _unique_username("f2")
    owner_ctx, owner_page = _make_user(browser, username_owner)
    fellow_ctx, fellow_page = _make_user(browser, username_fellow)
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(owner_page, f"/@{username_owner}/kendo")

        _connect_as_fellows(owner_page, username_owner, fellow_page, username_fellow)

        fellow_id = users_module.find_by_username(username_fellow)["id"]
        owner_id = users_module.find_by_username(username_owner)["id"]
        with db.connect() as conn:
            conn.execute("BEGIN")
            comments_service.create_comment(
                conn, int(entry_id), author_id=fellow_id, body="congrats on the streak"
            )
            assert comments_service.unseen_comment_count(conn, owner_id) == 1

        # First home visit: badge shows.
        owner_page.goto(BASE_URL + "/home")
        owner_page.wait_for_load_state("networkidle")
        assert owner_page.locator(f"a[aria-label='{ui_strings.COMMENTS_UNSEEN_ARIA}']").count() == 1

        # Second home visit: badge still shows (home no longer advances the
        # watermark -- this is the bug Task 3 fixed).
        owner_page.goto(BASE_URL + "/home")
        owner_page.wait_for_load_state("networkidle")
        assert owner_page.locator(f"a[aria-label='{ui_strings.COMMENTS_UNSEEN_ARIA}']").count() == 1

        # Visit /comments -- this is the only place the watermark advances.
        owner_page.goto(BASE_URL + "/comments")
        owner_page.wait_for_load_state("networkidle")
        assert "congrats on the streak" in owner_page.content()

        # Next home visit: badge is gone.
        owner_page.goto(BASE_URL + "/home")
        owner_page.wait_for_load_state("networkidle")
        assert owner_page.locator(f"a[aria-label='{ui_strings.COMMENTS_UNSEEN_ARIA}']").count() == 0
    finally:
        owner_ctx.close()
        fellow_ctx.close()


# ---------------------------------------------------------------------------
# 3. Click-through from /comments lands on the right entry's comment slot
# ---------------------------------------------------------------------------


def test_comments_page_click_through_lands_on_pre_expanded_thread(browser) -> None:
    from app.auth import users as users_module
    from app.models import db
    from app.services import comments as comments_service

    username_owner = _unique_username("o3")
    username_fellow = _unique_username("f3")
    owner_ctx, owner_page = _make_user(browser, username_owner)
    fellow_ctx, fellow_page = _make_user(browser, username_fellow)
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(owner_page, f"/@{username_owner}/kendo")

        _connect_as_fellows(owner_page, username_owner, fellow_page, username_fellow)

        fellow_id = users_module.find_by_username(username_fellow)["id"]
        with db.connect() as conn:
            conn.execute("BEGIN")
            comments_service.create_comment(
                conn, int(entry_id), author_id=fellow_id, body="great form in that last session"
            )

        owner_page.goto(BASE_URL + "/comments")
        owner_page.wait_for_load_state("networkidle")

        row = owner_page.locator(f"a[href*='c={entry_id}']")
        assert row.count() == 1
        row.first.click()

        owner_page.wait_for_url(
            lambda url: f"/@{username_owner}/kendo" in url and f"c={entry_id}" in url
        )
        owner_page.wait_for_load_state("networkidle")

        # Auto-expand-on-load against the merged calendar: the day-entries
        # comment slot for this entry carries an extra hx-trigger="load" on
        # its toggle button, so the thread fires and renders without a click.
        # (The day-detail panel and the full period log share one canonical
        # #comment-slot-{id} id since they're mutually exclusive views.)
        slot = owner_page.locator(f"#comment-slot-{entry_id}")
        slot.wait_for(state="attached")
        owner_page.wait_for_selector(f"#comment-thread-{entry_id}")
        assert "great form in that last session" in owner_page.content()

        # The URL still carries the #comment-slot-{id} fragment (the
        # /comments page row's anchor target, in the always-rendered
        # chronological log) — the browser scrolls to it natively.
        assert f"#comment-slot-{entry_id}" in owner_page.url
    finally:
        owner_ctx.close()
        fellow_ctx.close()


# ---------------------------------------------------------------------------
# 4. A blocked commenter's past comment still appears in the owner's feed
# ---------------------------------------------------------------------------


def test_blocked_commenters_past_comment_still_appears_in_owner_feed(browser) -> None:
    from app.auth import users as users_module
    from app.models import db
    from app.services import comments as comments_service

    username_owner = _unique_username("o4")
    username_fellow = _unique_username("f4")
    owner_ctx, owner_page = _make_user(browser, username_owner)
    fellow_ctx, fellow_page = _make_user(browser, username_fellow)
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(owner_page, f"/@{username_owner}/kendo")

        _connect_as_fellows(owner_page, username_owner, fellow_page, username_fellow)

        fellow_id = users_module.find_by_username(username_fellow)["id"]
        with db.connect() as conn:
            conn.execute("BEGIN")
            comments_service.create_comment(
                conn, int(entry_id), author_id=fellow_id, body="solid session, keep it up"
            )

        # Owner blocks the fellow. The "fellow" relationship state only
        # renders a "Remove" affordance (relationship_affordance.html.jinja2
        # -- Block is reachable only from "none"/"pending_*" states), so
        # remove the connection first, then block from the resulting "none"
        # state's two-step confirm -- a real, reachable browser path to the
        # same end state (no connection + a block row) the build plan's
        # scenario describes.
        owner_page.goto(BASE_URL + f"/@{username_fellow}")
        owner_page.get_by_role("button", name=ui_strings.CONNECT_REMOVE).click()
        owner_page.get_by_role("button", name=ui_strings.CONNECT_REMOVE_CONFIRM).click()
        owner_page.wait_for_selector(f"text={ui_strings.CONNECT_ACTION}")

        owner_page.get_by_role("button", name=ui_strings.CONNECT_BLOCK).click()
        owner_page.get_by_role("button", name=ui_strings.CONNECT_BLOCK_CONFIRM).click()
        owner_page.wait_for_load_state("networkidle")

        # The block tore down the connection -- forward access for the
        # fellow is now gone -- but the owner's own notification history is
        # never retroactively filtered.
        owner_page.goto(BASE_URL + "/comments")
        owner_page.wait_for_load_state("networkidle")
        assert "solid session, keep it up" in owner_page.content()
        assert owner_page.locator(f"a[href*='c={entry_id}']").count() == 1
    finally:
        owner_ctx.close()
        fellow_ctx.close()
