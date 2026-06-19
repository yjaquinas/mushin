"""Playwright E2E specs for the entry-screen auth toggle (Task 6,
auth-entry-flow).

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md). They are written ahead of
being run by an agent with MCP browser tools attached, and follow the same
skip/fixture pattern as ``tests/e2e/test_logging.py``.

Specs covered
-------------
1. The entry screen (``/``) defaults to the "Log in" tab active.
2. Clicking "Create account" swaps the form via HTMX (no full navigation).
3. Submitting the login form with a previously guest-upgraded account's
   credentials redirects to its canonical ``/@{username}`` profile.
4. "Continue without an account" still starts a guest session and lands on
   ``/home`` (guests have no public profile to redirect to).
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


def test_entry_screen_defaults_to_login_tab(page) -> None:
    """The entry screen lands with "Log in" selected and its fields visible."""
    page.goto(BASE_URL + "/")

    login_tab = page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_LOGIN)
    create_tab = page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE)
    assert login_tab.get_attribute("aria-selected") == "true"
    assert create_tab.get_attribute("aria-selected") == "false"

    # Login form fields are visible; the create-only consent checkbox is not.
    assert page.locator("#auth-form input[name='username']").is_visible()
    assert page.locator("#auth-form input[name='password']").is_visible()
    assert page.locator("#auth-form input[name='consent']").count() == 0


def test_clicking_create_account_tab_swaps_form_without_navigation(page) -> None:
    """Tapping "Create account" swaps #auth-form via HTMX — no page reload."""
    page.goto(BASE_URL + "/")

    navigated = {"count": 0}
    page.on("framenavigated", lambda _frame: navigated.__setitem__("count", navigated["count"] + 1))

    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()

    create_tab = page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE)
    page.wait_for_function(
        "() => document.getElementById('auth-tab-create')?.getAttribute('aria-selected') === 'true'"
    )
    assert create_tab.get_attribute("aria-selected") == "true"

    # The signup-only fields (email, consent) are now present.
    assert page.locator("#auth-form input[name='email']").is_visible()
    assert page.locator("#auth-form input[name='consent']").is_visible()

    assert navigated["count"] == 0, "tab switch should swap a fragment, not navigate"


def test_login_with_guest_upgraded_credentials_redirects_to_home(page) -> None:
    """A guest upgraded to username/password can log back in via the Log in
    tab, landing on its canonical /@{username} profile (the JSON success
    response carries `redirect_url`; auth-form.js navigates there)."""
    username = "e2eupgradeuser"

    # First, become a guest and upgrade in place via the Create account tab.
    page.goto(BASE_URL + "/")
    page.get_by_text(ui_strings.ENTRY_GUEST_LINK).click()
    page.wait_for_url(BASE_URL + "/home")

    page.goto(BASE_URL + "/")
    page.get_by_role("tab", name=ui_strings.ENTRY_AUTH_TAB_CREATE).click()
    page.wait_for_selector("#auth-form input[name='consent']")
    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", "passsword1")
    page.check("#auth-form input[name='consent']")
    page.get_by_role("button", name=ui_strings.ENTRY_CREATE_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")

    # Log out, then log back in with the same credentials.
    page.request.post(BASE_URL + "/auth/logout")
    page.goto(BASE_URL + "/")

    page.fill("#auth-form input[name='username']", username)
    page.fill("#auth-form input[name='password']", "passsword1")
    page.get_by_role("button", name=ui_strings.ENTRY_LOGIN_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")


def test_continue_without_account_still_starts_guest_session(page) -> None:
    """"Continue without an account" still mints a guest session and lands on /home."""
    page.goto(BASE_URL + "/")
    page.get_by_text(ui_strings.ENTRY_GUEST_LINK).click()
    page.wait_for_url(BASE_URL + "/home")
