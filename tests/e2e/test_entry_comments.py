"""Playwright E2E specs for entry comments (Task 4 of the entry-comments build
plan: ``meetings/MEETING-2026-06-19-entry-comments/3-BUILD-PLAN.md``).

Same dormant `pytest` + `playwright.sync_api` pattern as
``tests/e2e/test_fellows_e2e.py`` / ``tests/e2e/test_profiles_consent.py`` --
unrelated to the agent-driven `playwright-cli` skill. Skipped outright when no
Playwright browser is available (the `playwright` pip package was never added
as a project dependency), so `uv run pytest tests/` stays green on a plain dev
machine / CI without a browser.

Specs covered
-------------
1. A logged-in user visits a public profile's activity, expands an entry's
   comment affordance, types a comment, submits, and sees it appear without a
   full page reload (HTMX swap).
2. A logged-out visitor on the same public profile sees existing comments
   read-only with a "log in to comment" link and no textarea/submit button in
   the DOM.
3. A private-profile non-fellow visitor never sees a comment glyph/affordance
   at all (the character-sheet view has no clickable activity cards to begin
   with); forcing the direct detail/fragment URLs is rejected server-side.

NOTE on two pre-existing gaps found while writing these specs (neither
introduced by this test file -- both are flagged in the test-engineer report,
not silently routed around):

1. Real signup (``POST /auth/signup``) and guest creation
   (``POST /auth/guest``) never call ``app.services.seeding.seed_account`` --
   the only call site is the dormant, never-invoked ``_lazy_seed`` seam in
   ``app/auth/routes.py`` (a leftover from the retired guest-first-interaction
   flow). A brand-new account has zero starter activities and therefore zero
   entries to comment on. ``_make_user`` below seeds starter templates
   directly via ``app.services.seeding.seed_account`` (server-side, against
   the same DB file the live test server reads) to work around this and reach
   the actual comments feature under test.
2. ``public_activity.html.jinja2`` only renders the comment glyph/affordance
   when ``entry.comment_count > 0`` (matching Task 3's "zero-comment rows
   render no glyph/count at all" acceptance criterion literally) -- but that
   means there is currently no rendered affordance anywhere for posting an
   entry's FIRST comment; only a thread that already has at least one comment
   can ever be opened from the UI. The specs below seed the thread's first
   comment directly via ``app.services.comments.create_comment`` (server-side,
   same DB file) before driving the rest of the flow through the browser.

Environment note: seeding the first comment is done via the service layer
rather than an in-browser ``page.request.post`` to the comments route.
Playwright's ``APIRequestContext`` (``page.request``/``ctx.request``) does not
attach the session cookie on plain-``http://127.0.0.1`` requests in this
environment, even though the same cookie *is* sent correctly for ordinary page
navigations and ``page.request.get`` calls (Chromium treats ``127.0.0.1`` as a
secure context for navigation purposes, but the separate API-request network
stack enforces "Secure cookies require TLS" literally and silently drops it).
This is a Playwright/Chromium environment quirk, not an application bug --
confirmed by reproducing it against a debug user with a real session and a
known-good ``GET`` that returns the logged-out thread view despite a valid
cookie in the context's cookie jar.

Content-level access assertions (private+non-fellow 404, fellow read/write,
revoke-hides-comment, delete permissions, account-deletion cascade, home
badge) are covered at the HTTP level in
``tests/integration/test_entry_comments.py``.
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
    so keep *slug* short (<=7 chars): "e2m" (3) + slug + 8 hex chars stays
    within the cap."""
    return f"e2m{slug}{uuid.uuid4().hex[:8]}"


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

    Also seeds the starter templates (kendo/reading) directly via
    ``app.services.seeding.seed_account`` -- see the module docstring's note
    on real signup never triggering seeding itself. This call hits the same
    DB file the live test server reads, so the row is visible to the next
    request the browser makes.
    """
    from app.auth import users as users_module
    from app.services import seeding

    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    if visibility == "public":
        page.locator("input[name='visibility'][value='public']").check()
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    owner = users_module.find_by_username(username)
    seeding.seed_account(owner["id"])

    return context, page


def _open_detail(page, heading: str):
    """Navigate from /home to a sub-tally's detail screen via its card link.

    The card links to ``/activities/{id}``, which 301-redirects to the
    owner's own ``/@{username}/{slug}`` detail page -- so wait for the URL to
    leave ``/home`` rather than for an ``/activities/*`` URL that never
    settles (the redirect lands one hop later)."""
    home_card = page.locator("article", has=page.get_by_role("heading", name=heading))
    home_card.locator("a").first.click()
    page.wait_for_url(lambda url: not url.endswith("/home"))


def _log_one_entry(page) -> None:
    """From the owner's own Kendo detail screen, log one bare entry so the
    read-only public activity page has an entry row to comment on."""
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


# ---------------------------------------------------------------------------
# 1. Logged-in viewer on a public profile: post + see it without reload
# ---------------------------------------------------------------------------


def test_logged_in_viewer_can_post_comment_via_fragment_swap(browser) -> None:
    from app.auth import users as users_module
    from app.models import db
    from app.services import comments as comments_service

    username_owner = _unique_username("o1")
    username_viewer = _unique_username("v1")
    owner_ctx, owner_page = _make_user(browser, username_owner, visibility="public")
    viewer_ctx, viewer_page = _make_user(browser, username_viewer)
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(viewer_page, f"/@{username_owner}/kendo")

        # Seed the thread's first comment directly via the service layer --
        # see the module docstring's "Environment note" on why this isn't
        # driven through page.request.post, plus the "zero comments -> no
        # rendered affordance" UI gap: there is currently no in-page way to
        # open a brand-new, comment-less thread, so the *second* comment is
        # the one driven through the browser below.
        viewer_id = users_module.find_by_username(username_viewer)["id"]
        with db.connect() as conn:
            conn.execute("BEGIN")
            comments_service.create_comment(
                conn, int(entry_id), author_id=viewer_id, body="First comment, seeded directly"
            )

        viewer_page.goto(BASE_URL + f"/@{username_owner}/kendo")
        viewer_page.wait_for_load_state("networkidle")

        # Track full-page navigations: posting a comment must swap a
        # fragment, never trigger one.
        navigated = {"count": 0}
        viewer_page.on(
            "framenavigated",
            lambda _frame: navigated.__setitem__("count", navigated["count"] + 1),
        )

        glyph = viewer_page.locator(f"button[hx-get*='/entries/{entry_id}/comments']")
        assert glyph.count() == 1
        glyph.click()
        viewer_page.wait_for_selector(f"#comment-thread-{entry_id} textarea")

        viewer_page.fill(f"#comment-thread-{entry_id} textarea", "Great session today!")
        viewer_page.locator(f"#comment-thread-{entry_id} form").get_by_role(
            "button", name=ui_strings.COMMENTS_SUBMIT
        ).click()

        viewer_page.wait_for_selector("text=Great session today!")
        assert navigated["count"] == 0, "posting a comment should swap a fragment, not navigate"
    finally:
        owner_ctx.close()
        viewer_ctx.close()


# ---------------------------------------------------------------------------
# 2. Logged-out visitor: read-only thread, no composer
# ---------------------------------------------------------------------------


def test_logged_out_visitor_sees_read_only_thread_no_composer(browser) -> None:
    from app.auth import users as users_module
    from app.models import db
    from app.services import comments as comments_service

    username_owner = _unique_username("o2")
    username_viewer = _unique_username("v2")
    owner_ctx, owner_page = _make_user(browser, username_owner, visibility="public")
    viewer_ctx, viewer_page = _make_user(browser, username_viewer)
    anon_ctx = browser.new_context(viewport={"width": 360, "height": 800})
    anon_page = anon_ctx.new_page()
    try:
        _log_one_entry(owner_page)
        entry_id = _first_entry_id(viewer_page, f"/@{username_owner}/kendo")

        # Seed directly via the service layer -- see the module docstring's
        # "Environment note" on why this isn't driven through
        # page.request.post.
        viewer_id = users_module.find_by_username(username_viewer)["id"]
        with db.connect() as conn:
            conn.execute("BEGIN")
            comments_service.create_comment(
                conn, int(entry_id), author_id=viewer_id, body="Visible to all visitors"
            )

        # An anonymous (cookie-less) visitor: the glyph+count affordance
        # shows (comment_count > 0); expanding it shows the comment
        # read-only with a login link and no textarea/submit anywhere.
        anon_page.goto(BASE_URL + f"/@{username_owner}/kendo")
        anon_page.wait_for_load_state("networkidle")
        glyph = anon_page.locator(f"button[hx-get*='/entries/{entry_id}/comments']")
        assert glyph.count() == 1
        glyph.click()
        anon_page.wait_for_selector("text=Visible to all visitors")

        assert anon_page.locator(f"#comment-thread-{entry_id} textarea").count() == 0
        assert anon_page.locator(f"#comment-thread-{entry_id} form").count() == 0
        assert ui_strings.COMMENTS_LOGIN_TO_COMMENT in anon_page.content()
    finally:
        owner_ctx.close()
        viewer_ctx.close()
        anon_ctx.close()


# ---------------------------------------------------------------------------
# 3. Private profile, non-fellow visitor: no comment affordance anywhere
# ---------------------------------------------------------------------------


def test_private_profile_non_fellow_sees_no_comment_affordance(browser) -> None:
    username_owner = _unique_username("o3")
    username_visitor = _unique_username("vs3")
    owner_ctx, owner_page = _make_user(browser, username_owner, visibility="private")
    visitor_ctx, visitor_page = _make_user(browser, username_visitor)
    try:
        _log_one_entry(owner_page)

        # A non-fellow visitor sees the character sheet only -- no clickable
        # activity cards (the limited view), so there's no path to an
        # entry/comment affordance at all.
        visitor_page.goto(BASE_URL + f"/@{username_owner}")
        assert visitor_page.locator(f"a[href^='/@{username_owner}/']").count() == 0
        assert visitor_page.locator("[id^='comment-slot-']").count() == 0
        assert "message-circle" not in visitor_page.content()

        # Forcing the direct activity-detail URL redirects back to the
        # profile (limited view never exposes the slug route).
        visitor_page.goto(BASE_URL + f"/@{username_owner}/kendo")
        assert visitor_page.url == BASE_URL + f"/@{username_owner}"

        # And forcing the comment-fragment URL directly is rejected
        # server-side (404 -- no existence/content oracle), never a 200 with
        # a composer.
        fragment_resp = visitor_page.request.get(
            BASE_URL + f"/@{username_owner}/kendo/entries/1/comments"
        )
        assert fragment_resp.status == 404
    finally:
        owner_ctx.close()
        visitor_ctx.close()
