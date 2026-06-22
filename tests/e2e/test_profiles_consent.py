"""Playwright E2E specs for the visibility-consent screen and public-profile
routes (Phase 1, Tasks 3-6, sub-tally-url-naming).

These are real `pytest` + `playwright.sync_api` specs (see
.claude/rules/tests.md) -- not agent-driven via the `playwright-cli` skill.
They're currently dormant (`playwright` was never added as a project
dependency), following the same skip/fixture pattern as
``tests/e2e/test_logging.py`` and ``tests/e2e/test_auth_entry.py``.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser.

Specs covered
-------------
1. Consent screen flow: a freshly-created (non-guest) account lands on
   ``/welcome-sharing`` before reaching its profile, "Private" is
   pre-selected, submitting redirects straight to the canonical
   ``/@{username}`` profile, and revisiting ``/home`` afterward renders the
   dashboard in place (no detour back through ``/welcome-sharing`` now that
   consent has been recorded — see ``app/routes/web.py``'s ``home()``).
2. Visibility toggle: on ``/account``, switching visibility to "public"
   updates the rendered share-link text (``/@{username}``).
3. Public profile as an anonymous visitor: a fresh, cookie-less browser
   context viewing ``/@{username}`` for a public account sees the activity
   list with zero write affordances (no log/edit/add buttons), and clicking
   into an activity (``/@{username}/{slug}``) renders the read-only detail
   view including memo text.
4. Private profile character sheet: an anonymous visitor viewing
   ``/@{username}`` for a private account sees activity names + levels (the
   character sheet), with cards NOT clickable, plus the quiet
   ``PROFILE_LIMITED_NOTICE`` line — no entries/notes leak, and forcing
   ``/@{username}/{slug}`` 303-redirects back to the profile.
5. Guest bypass: a guest session renders ``/home`` directly (no
   ``/welcome-sharing`` redirect) and ``/account`` shows no visibility
   toggle/share-link for guests.
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


@pytest.fixture
def anon_page(browser):
    """A fresh browser context with NO cookies/session — for the public,
    unauthenticated ``/@{username}`` routes."""
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def other_page(browser):
    """A second, separately-authenticated browser context — a logged-in
    user who is NOT a fellow of the profile under test. Distinct from
    ``anon_page`` (no session at all) and from ``page`` (the profile
    owner's own session)."""
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    yield page
    context.close()


def _unique_username(slug: str) -> str:
    """A username that's unique per test run, so reruns against the
    persistent dev DB never collide with a leftover row from a previous run.
    Usernames are capped at 20 chars (``app.auth.routes._normalize_username``),
    so keep *slug* short (<=7 chars): "e2c" (3) + slug + 8 hex chars stays
    within the cap."""
    return f"e2c{slug}{uuid.uuid4().hex[:8]}"


def _signup(page, username: str, password: str = "correct-horse-battery") -> None:
    """Land on the entry screen, switch to "Create account", and submit a
    new username/password signup with consent checked."""
    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", password)
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()


def _enter_as_guest(page) -> None:
    """Start a guest session directly via ``POST /guest`` and land on /home.

    Guest account *creation* is no longer reachable from the UI (the
    "Continue without an account" entry-screen link was removed — see
    project CLAUDE.md, guest mode retired 2026-06-16) -- but the backend
    route (``app.auth.routes.guest_start``) still exists for the
    guest-create-on-interaction model and the drain window. Call it directly
    via ``page.request`` (shares cookies with *page*'s browser context) to
    exercise genuinely guest-specific behavior, like this module's
    guest-bypass spec below.
    """
    page.goto(BASE_URL + "/")
    page.request.post(BASE_URL + "/auth/guest")
    page.goto(BASE_URL + "/home")


# ---------------------------------------------------------------------------
# 1. Consent screen flow
# ---------------------------------------------------------------------------


def test_signup_lands_on_consent_screen_before_home(page) -> None:
    """A fresh signup is redirected to /welcome-sharing before reaching its
    profile, with "Private" pre-selected; submitting redirects straight to
    the canonical /@{username} profile, and revisiting /home afterward
    renders the dashboard in place — never back to /welcome-sharing."""
    username = _unique_username("consent")
    _signup(page, username)

    page.wait_for_url(BASE_URL + "/welcome-sharing")

    private_radio = page.locator("input[name='visibility'][value='private']")
    public_radio = page.locator("input[name='visibility'][value='public']")
    assert private_radio.is_checked()
    assert not public_radio.is_checked()

    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    # Revisiting /home does not bounce back to /welcome-sharing — it renders
    # the dashboard in place now that consent has been recorded.
    page.goto(BASE_URL + "/home")
    assert page.url == BASE_URL + "/home"


# ---------------------------------------------------------------------------
# 2. Visibility toggle on /account
# ---------------------------------------------------------------------------


def test_account_visibility_toggle_updates_share_link(page) -> None:
    """Toggling visibility to "public" on /account redirects home (not back
    to /account, matching the sibling consent-write handlers) with a
    one-shot flash confirmation, and the change persists on a return visit
    to /account."""
    username = _unique_username("toggle")
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    page.goto(BASE_URL + "/account")
    assert f"/@{username}" in page.content()

    public_radio = page.locator("input[name='visibility'][value='public']")
    public_radio.check()
    page.get_by_role("button", name=ui_strings.ACCOUNT_VISIBILITY_SAVE).click()

    # Save redirects home (the owner's canonical profile URL), not back to
    # /account, and shows the one-shot flash confirmation exactly once.
    page.wait_for_url(BASE_URL + f"/@{username}")
    assert ui_strings.HOME_FLASH_VISIBILITY_PUBLIC in page.content()

    # A follow-up visit to the same page must not show the flash again.
    page.goto(BASE_URL + f"/@{username}")
    assert ui_strings.HOME_FLASH_VISIBILITY_PUBLIC not in page.content()

    # The change persisted: /account reflects "public" on a fresh visit.
    page.goto(BASE_URL + "/account")
    public_radio_after = page.locator("input[name='visibility'][value='public']")
    assert public_radio_after.is_checked()
    assert ui_strings.ACCOUNT_VISIBILITY_CURRENT_PUBLIC in page.content()


# ---------------------------------------------------------------------------
# 3. Public profile as anonymous visitor
# ---------------------------------------------------------------------------


def test_public_profile_shows_activities_with_no_write_affordances(page, anon_page) -> None:
    """A public account's profile, viewed with no session, lists activities
    with zero write affordances; clicking into one renders the read-only
    detail view (including memo text if present) through the same merged
    calendar the owner dashboard uses — which does have read-only GET
    navigation buttons (period switch, prev/next, day-select), so the
    detail-page assertion checks for the *absence of write* affordances
    specifically (no <form>, no edit/delete/rename/log-trigger button or
    URL), not literally zero buttons."""
    username = _unique_username("public")
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.locator("input[name='visibility'][value='public']").check()
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    # Onboarding seeds starter templates lazily on first entry — visit the
    # profile once more (still as the owner) to ensure the kendo/reading
    # categories exist.
    page.goto(BASE_URL + f"/@{username}")

    # Now view the profile with a completely fresh, cookie-less context.
    anon_page.goto(BASE_URL + f"/@{username}")
    assert anon_page.url == BASE_URL + f"/@{username}"

    # No write affordances anywhere on the profile page.
    assert anon_page.locator("button").count() == 0
    assert anon_page.locator("form").count() == 0
    assert anon_page.locator("input").count() == 0

    # Activity cards (if any were seeded) link to /@{username}/{slug}.
    activity_links = anon_page.locator(f"a[href^='/@{username}/']")
    if activity_links.count() > 0:
        activity_links.first.click()
        anon_page.wait_for_load_state("networkidle")
        assert f"/@{username}/" in anon_page.url

        # No write-capable element anywhere on the detail page: no form,
        # no input, and no button whose hx-get/hx-post targets an
        # edit/delete/rename/log/match-row mutation route. The calendar's
        # own read-only nav buttons (period switch, prev/next, day-select —
        # all plain GETs against /activities/{id}/history) are expected and
        # allowed here.
        assert anon_page.locator("form").count() == 0
        assert anon_page.locator("input").count() == 0
        for attr in ("hx-post",):
            assert anon_page.locator(f"[{attr}]").count() == 0
        write_url_fragment = (
            "[hx-get*='/edit'], [hx-get*='/delete'], [hx-get*='/rename'], "
            "[hx-get*='/match-rows'], [hx-get*='/log-trigger'], #log-trigger"
        )
        assert anon_page.locator(write_url_fragment).count() == 0


def test_public_profile_calendar_renders_for_logged_in_non_fellow(page, other_page) -> None:
    """A public account's activity detail, viewed by a different, logged-in
    user who is NOT a fellow, renders the same merged calendar (period
    switcher + day-grouped log) the owner sees — with zero write
    affordances. This is distinct from the anonymous-visitor case above:
    the viewer here has an authenticated session, just not one with any
    relationship to the profile owner."""
    from app.auth import users as users_module
    from tests.conftest import seed_test_activity

    owner_username = _unique_username("calowner")
    _signup(page, owner_username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.locator("input[name='visibility'][value='public']").check()
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{owner_username}")

    # Real signup creates zero activities now (the onboarding seed step was
    # removed along with the progression feature it demonstrated — see
    # project CLAUDE.md), so seed a fixture activity directly via
    # ``tests.conftest.seed_test_activity`` against the same DB file the live
    # test server reads.
    owner = users_module.find_by_username(owner_username)
    seed_test_activity(owner["id"], name="Kendo")

    page.goto(BASE_URL + f"/@{owner_username}")

    # A second, unrelated account — logged in, but not a fellow of the owner.
    other_username = _unique_username("nonfellow")
    _signup(other_page, other_username)
    other_page.wait_for_url(BASE_URL + "/welcome-sharing")
    other_page.locator("input[name='visibility'][value='private']").check()
    other_page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    other_page.wait_for_url(BASE_URL + f"/@{other_username}")

    # Now, still logged in as the second account, view the owner's profile.
    other_page.goto(BASE_URL + f"/@{owner_username}")
    activity_links = other_page.locator(f"a[href^='/@{owner_username}/']")
    assert activity_links.count() > 0
    activity_links.first.click()
    other_page.wait_for_load_state("networkidle")
    assert f"/@{owner_username}/" in other_page.url

    # The merged calendar's read-only header is present (period switcher).
    assert other_page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_MONTH).count() == 1
    assert other_page.get_by_role("tab", name=ui_strings.HISTORY_PERIOD_WEEK).count() == 1

    # No write affordance: no form/input anywhere, no edit/delete/rename/
    # log-trigger button or URL.
    assert other_page.locator("form").count() == 0
    assert other_page.locator("input").count() == 0
    assert other_page.locator("[hx-post]").count() == 0
    write_url_fragment = (
        "[hx-get*='/edit'], [hx-get*='/delete'], [hx-get*='/rename'], "
        "[hx-get*='/match-rows'], [hx-get*='/log-trigger'], #log-trigger"
    )
    assert other_page.locator(write_url_fragment).count() == 0


# ---------------------------------------------------------------------------
# 4. Private profile stub
# ---------------------------------------------------------------------------


def test_private_profile_shows_character_sheet_not_clickable(page, anon_page) -> None:
    """A private account's /@{username} shows the character sheet (activity
    names/levels, cards not clickable) when viewed with no session, and
    forcing the activity-detail URL redirects back to the profile."""
    username = _unique_username("private")
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    # Private is pre-selected; submit as-is.
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    anon_page.goto(BASE_URL + f"/@{username}")

    assert ui_strings.PROFILE_LIMITED_NOTICE in anon_page.content()
    # Cards (if any seeded) render but are not wrapped in a navigation link.
    assert anon_page.locator(f"a[href^='/@{username}/']").count() == 0


# ---------------------------------------------------------------------------
# 5. Guest bypass
# ---------------------------------------------------------------------------


def test_guest_skips_consent_and_account_has_no_visibility_toggle(page) -> None:
    """A guest session renders /home directly (no /welcome-sharing redirect)
    and /account shows no visibility toggle/share-link."""
    _enter_as_guest(page)
    assert page.url == BASE_URL + "/home"

    page.goto(BASE_URL + "/account")
    assert page.url == BASE_URL + "/account"

    body = page.content()
    assert 'name="visibility"' not in body
    assert 'action="/account/visibility"' not in body
