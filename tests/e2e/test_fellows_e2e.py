"""Playwright E2E specs for the social graph (fellows): the connection
handshake, blocking, and search→connect — a dormant `pytest` +
`playwright.sync_api` spec (see .claude/rules/tests.md), unrelated to the
agent-driven `playwright-cli` skill.

Same skip/fixture pattern as ``tests/e2e/test_profiles_consent.py``: marked
``e2e`` and skipped outright when no Playwright browser/MCP session is
available, so ``uv run pytest tests/`` stays green on a plain dev machine / CI
without a browser (the `playwright` pip package was never added as a
dependency).

Specs covered
-------------
1. Connection handshake (two users): A opens B's profile and clicks "Connect",
   passes the sharing-consent step, and the control flips to "Requested"; B
   sees the incoming request on ``/home`` and Accepts (through its own
   sharing-consent step); A's view of B then reads "You're fellows"; A removes
   the connection and the control returns to "Connect".
2. Block hides + prevents re-contact: after A blocks B, B can no longer find A
   in search, and navigating to ``/@{A}`` returns 404 (the no-existence-oracle
   guarantee), so B cannot re-request.
3. Search → connect: A searches for B by username on ``/search`` and clicks
   "Connect" directly from the result row, which flips that row to "Requested".

These are interaction-level specs (HTMX swaps, click-through consent, the
cross-user handshake). Content-level access assertions (a fellow seeing private
entries + notes, the 303 redirect, the blocked 404) are covered at the HTTP
level in ``tests/integration/test_public_profiles.py`` and ``test_fellows.py``.
"""

from __future__ import annotations

import uuid

import pytest

from app import ui_strings

pytestmark = pytest.mark.e2e

# Skip the whole module when there's no Playwright browser available (plain
# `uv run pytest` on a dev machine / CI without a browser install -- the
# `playwright` pip package was never added as a dependency).
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
    so keep *slug* short (<=4 chars) -- "e2f" (3) + slug + 13 hex chars stays
    within the cap."""
    return f"e2f{slug}{uuid.uuid4().hex[:13]}"


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


def _make_user(browser, username: str):
    """Create a fresh browser context, sign up *username* (private, the
    default), clear the one-time visibility-consent screen, and return the
    logged-in ``(context, page)`` sitting on its own ``/@{username}`` profile."""
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    _signup(page, username)
    page.wait_for_url(BASE_URL + "/welcome-sharing")
    # Private is pre-selected — submit as-is.
    page.get_by_role("button", name=ui_strings.VISIBILITY_CONSENT_SUBMIT).click()
    page.wait_for_url(BASE_URL + f"/@{username}")
    return context, page


# ---------------------------------------------------------------------------
# 1. Connection handshake (two users)
# ---------------------------------------------------------------------------


def test_connect_accept_fellow_then_remove(browser) -> None:
    """A → Connect (with consent) → Requested; B accepts (with consent) from
    /home; A then reads "You're fellows"; A removes and it returns to Connect.

    Exercises the full two-sided handshake through real HTMX fragment swaps and
    both sharing-consent steps."""
    username_a = _unique_username("a")
    username_b = _unique_username("b")
    a_ctx, a_page = _make_user(browser, username_a)
    b_ctx, b_page = _make_user(browser, username_b)
    try:
        # A opens B's profile and connects.
        a_page.goto(BASE_URL + f"/@{username_b}")
        a_page.get_by_role("button", name=ui_strings.CONNECT_ACTION).click()
        # Sharing-consent consequence screen, then confirm.
        a_page.get_by_role("button", name=ui_strings.SHARING_CONSENT_CONFIRM).click()
        # Control flips to "Requested" via the fragment swap.
        a_page.wait_for_selector(f"text={ui_strings.CONNECT_REQUESTED}")

        # B sees the incoming request on /home and accepts (its own consent step).
        # The requests cluster is collapsed by default behind a "Requests (N)"
        # toggle (components/requests_cluster.html.jinja2) -- expand it first.
        b_page.goto(BASE_URL + "/home")
        assert username_a in b_page.content()
        b_page.get_by_role("button", name=ui_strings.REQUESTS_HEADING, exact=False).click()
        b_page.get_by_role("button", name=ui_strings.REQUESTS_ACCEPT).click()
        b_page.get_by_role("button", name=ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT).click()
        b_page.wait_for_load_state("networkidle")

        # A reloads B's profile — now reads "You're fellows".
        a_page.goto(BASE_URL + f"/@{username_b}")
        assert ui_strings.CONNECT_FELLOWS_LABEL in a_page.content()

        # A removes the connection (two-step confirm) → back to "Connect".
        a_page.get_by_role("button", name=ui_strings.CONNECT_REMOVE).click()
        a_page.get_by_role("button", name=ui_strings.CONNECT_REMOVE_CONFIRM).click()
        a_page.wait_for_selector(f"text={ui_strings.CONNECT_ACTION}")
    finally:
        a_ctx.close()
        b_ctx.close()


# ---------------------------------------------------------------------------
# 2. Block hides + prevents re-contact
# ---------------------------------------------------------------------------


def test_block_hides_from_search_and_view(browser) -> None:
    """After A blocks B, B cannot find A in search and /@{A} returns 404 — so B
    cannot view or re-request A (no existence oracle)."""
    username_a = _unique_username("a")
    username_b = _unique_username("b")
    a_ctx, a_page = _make_user(browser, username_a)
    b_ctx, b_page = _make_user(browser, username_b)
    try:
        # A blocks B from B's profile (Block link → two-step confirm).
        a_page.goto(BASE_URL + f"/@{username_b}")
        a_page.get_by_role("button", name=ui_strings.CONNECT_BLOCK).click()
        a_page.get_by_role("button", name=ui_strings.CONNECT_BLOCK_CONFIRM).click()
        a_page.wait_for_load_state("networkidle")

        # B searches for A → no result row (block hides both directions).
        b_page.goto(BASE_URL + "/search")
        b_page.fill("input[name='q']", username_a)
        b_page.wait_for_timeout(500)  # debounce
        assert b_page.locator(f"a[href='/@{username_a}']").count() == 0

        # B navigates directly to A's profile → 404 (no existence oracle).
        resp = b_page.goto(BASE_URL + f"/@{username_a}")
        assert resp is not None and resp.status == 404
    finally:
        a_ctx.close()
        b_ctx.close()


# ---------------------------------------------------------------------------
# 3. Search → connect
# ---------------------------------------------------------------------------


def test_search_then_connect_from_result_row(browser) -> None:
    """A searches for B by username on /search and clicks "Connect" straight
    from the result row; that row flips to "Requested"."""
    username_a = _unique_username("a")
    username_b = _unique_username("b")
    a_ctx, a_page = _make_user(browser, username_a)
    b_ctx, b_page = _make_user(browser, username_b)
    try:
        a_page.goto(BASE_URL + "/search")
        a_page.fill("input[name='q']", username_b)
        a_page.wait_for_timeout(500)  # debounce

        # B appears as a person result linking to the profile.
        assert a_page.locator(f"a[href='/@{username_b}']").count() == 1

        # Connect from the row (scoped to the per-row affordance id).
        row = a_page.locator(f"#relationship-affordance-{username_b}")
        row.get_by_role("button", name=ui_strings.CONNECT_ACTION).click()
        a_page.get_by_role("button", name=ui_strings.SHARING_CONSENT_CONFIRM).click()
        a_page.wait_for_selector(f"text={ui_strings.CONNECT_REQUESTED}")
    finally:
        a_ctx.close()
        b_ctx.close()
