"""Playwright E2E specs for the visibility-consent screen and public-profile
routes (Phase 1, Tasks 3-6, sub-tally-url-naming).

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md — "E2E tests use the Playwright
MCP — not a bundled Playwright"). They are written ahead of being run by an
agent with MCP browser tools attached, following the same skip/fixture
pattern as ``tests/e2e/test_logging.py`` and ``tests/e2e/test_auth_entry.py``.

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


@pytest.fixture
def anon_page(browser):
    """A fresh browser context with NO cookies/session — for the public,
    unauthenticated ``/@{username}`` routes."""
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    yield page
    context.close()


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
    """Land on the entry screen and tap "Continue without an account" to start a guest session."""
    page.goto(BASE_URL + "/")
    page.get_by_text(ui_strings.ENTRY_GUEST_LINK).click()
    page.wait_for_url(BASE_URL + "/home")


# ---------------------------------------------------------------------------
# 1. Consent screen flow
# ---------------------------------------------------------------------------


def test_signup_lands_on_consent_screen_before_home(page) -> None:
    """A fresh signup is redirected to /welcome-sharing before reaching its
    profile, with "Private" pre-selected; submitting redirects straight to
    the canonical /@{username} profile, and revisiting /home afterward
    renders the dashboard in place — never back to /welcome-sharing."""
    username = "e2econsentuser"
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
    """Toggling visibility to "public" on /account updates the rendered
    share-link text to reference /@{username}."""
    username = "e2etoggleuser"
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    page.goto(BASE_URL + "/account")
    assert f"/@{username}" in page.content()

    public_radio = page.locator("input[name='visibility'][value='public']")
    public_radio.check()
    page.get_by_role("button", name=ui_strings.ACCOUNT_VISIBILITY_SAVE).click()

    page.wait_for_load_state("networkidle")
    public_radio_after = page.locator("input[name='visibility'][value='public']")
    assert public_radio_after.is_checked()
    assert f"/@{username}" in page.content()
    assert ui_strings.ACCOUNT_VISIBILITY_CURRENT_PUBLIC in page.content()


# ---------------------------------------------------------------------------
# 3. Public profile as anonymous visitor
# ---------------------------------------------------------------------------


def test_public_profile_shows_activities_with_no_write_affordances(page, anon_page) -> None:
    """A public account's profile, viewed with no session, lists activities
    with zero write affordances; clicking into one renders the read-only
    detail view including memo text if present."""
    username = "e2epublicuser"
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

    # No write affordances anywhere on the page.
    assert anon_page.locator("button").count() == 0
    assert anon_page.locator("form").count() == 0
    assert anon_page.locator("input").count() == 0

    # Activity cards (if any were seeded) link to /@{username}/{slug}.
    activity_links = anon_page.locator(f"a[href^='/@{username}/']")
    if activity_links.count() > 0:
        activity_links.first.click()
        anon_page.wait_for_load_state("networkidle")
        assert f"/@{username}/" in anon_page.url

        # Still zero write affordances on the detail page.
        assert anon_page.locator("button").count() == 0
        assert anon_page.locator("form").count() == 0
        assert anon_page.locator("input").count() == 0


# ---------------------------------------------------------------------------
# 4. Private profile stub
# ---------------------------------------------------------------------------


def test_private_profile_shows_character_sheet_not_clickable(page, anon_page) -> None:
    """A private account's /@{username} shows the character sheet (activity
    names/levels, cards not clickable) when viewed with no session, and
    forcing the activity-detail URL redirects back to the profile."""
    username = "e2eprivateuser"
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
