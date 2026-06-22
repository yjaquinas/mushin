"""Integration tests for the web (HTMX) routes (Task 6).

Covers:

1. The logged-out entry screen (``GET /``) renders the 無心 gloss, the
   guest-start CTA, and the no-signup framing — and never claims data stays
   only on-device (guest data lives on the server).
2. The guest flow: ``POST /auth/guest`` mints a session, and ``GET /home``
   then renders activity cards for activities created explicitly via the
   shared ``tests/conftest.py::seed_test_activity`` helper (there are no
   onboarding starter templates any more — every account starts empty).
3. ``POST /activities/{id}/log`` under ``HX-Request: true`` returns an HTMX
   fragment (not a full document) and increments the sub-tally's count.
4. A strings-centralization guard scanning ``app/templates/**`` for hardcoded
   user-facing Hangul text.

Setup mirrors ``tests/integration/test_auth.py``: a fresh migrated temp SQLite
DB per test, ``SESSION_SECRET`` set, and an HTTPS base URL so the ``Secure``
session cookie round-trips through httpx's cookie jar.
"""

from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app import ui_strings as strings_module
from app.auth import users as users_module
from app.main import app
from app.models import db
from app.models.migrate import run_migrations
from app.services import categories, competition, entries, stats
from app.services import comments as comments_service
from tests.conftest import seed_test_activity

# Default timezone used by tests that don't exercise timezone-specific
# behavior directly.
_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def web_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh migrated DB; point db.connect() at it and set SESSION_SECRET."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-do-not-use-in-prod")
    return db_path


@pytest.fixture
async def client(web_db: Path) -> AsyncClient:
    """Async client with an HTTPS base URL so the Secure session cookie persists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.fixture
async def client2(web_db: Path) -> AsyncClient:
    """A second, independent client sharing the same DB (a different user)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


async def _guest_login(client: AsyncClient) -> int:
    """Mint a guest session and return its owner_id (user id)."""
    resp = await client.post("/auth/guest")
    assert resp.status_code == 200
    return int(resp.json()["user_id"])


def _clear_seeded_data(owner_id: int) -> None:
    """Remove any of an account's categories, to exercise the empty-home state.

    Fresh accounts start with zero activities by default. This helper is a
    defensive no-op guard for tests that assert the *empty* home UI — it
    deletes any categories (children cascade) so the assertion holds even if
    an earlier step in the test created one.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM category WHERE owner_id = ?", (owner_id,))


# ---------------------------------------------------------------------------
# Entry screen (logged out)
# ---------------------------------------------------------------------------


async def test_entry_screen_renders_for_logged_out_client(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "無心" in resp.text
    assert strings_module.ENTRY_AUTH_TAB_LOGIN in resp.text
    assert strings_module.ENTRY_AUTH_TAB_CREATE in resp.text
    # Guest link retired 2026-06-16 — must NOT appear on the entry screen.
    assert strings_module.ENTRY_GUEST_LINK not in resp.text
    assert strings_module.ENTRY_GUEST_SUB not in resp.text


async def test_entry_screen_does_not_claim_device_only_storage(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    # Guest data lives on the server, not on-device — never imply otherwise.
    assert "only on this device" not in resp.text
    assert "only on your device" not in resp.text


async def test_entry_screen_consent_line_links_to_privacy_policy(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text
    assert strings_module.ENTRY_CONSENT_LINK_TEXT in resp.text


async def test_entry_screen_defaults_to_login_tab_active(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    # The Log in tab is selected by default; Create account is not.
    assert 'id="auth-tab-login"\n            aria-selected="true"' in resp.text
    assert 'id="auth-tab-create"\n            aria-selected="false"' in resp.text
    # The Log in form's fields are present (username + password, no email/consent).
    assert 'name="username"' in resp.text
    assert 'name="password"' in resp.text


async def test_create_form_fragment_renders_standalone_with_signup_fields(
    client: AsyncClient,
) -> None:
    resp = await client.get("/auth/create-form")
    assert resp.status_code == 200
    assert 'id="auth-tab-create"\n            aria-selected="true"' in resp.text
    assert 'hx-post="/auth/signup"' in resp.text
    assert 'name="username"' in resp.text
    assert 'name="password"' in resp.text
    assert 'name="email"' in resp.text
    assert 'name="consent"' in resp.text


async def test_login_form_fragment_renders_standalone_with_login_fields(
    client: AsyncClient,
) -> None:
    resp = await client.get("/auth/login-form")
    assert resp.status_code == 200
    assert 'id="auth-tab-login"\n            aria-selected="true"' in resp.text
    assert 'hx-post="/auth/login"' in resp.text
    assert 'name="username"' in resp.text
    assert 'name="password"' in resp.text
    # The login form has no email/consent fields.
    assert 'name="email"' not in resp.text
    assert 'name="consent"' not in resp.text


# ---------------------------------------------------------------------------
# Privacy policy page (logged out)
# ---------------------------------------------------------------------------


async def test_privacy_policy_renders_for_logged_out_client(client: AsyncClient) -> None:
    resp = await client.get("/privacy")
    assert resp.status_code == 200
    assert strings_module.PRIVACY_PAGE_TITLE in resp.text
    assert "11. Changes to this policy" in resp.text
    assert "2026-06-11" in resp.text
    assert "mushin@aqnas.xyz" in resp.text


async def test_privacy_policy_excludes_internal_meta_content(client: AsyncClient) -> None:
    resp = await client.get("/privacy")
    assert resp.status_code == 200
    assert "초안(DRAFT)" not in resp.text
    assert "검토를 받으시기를 권장" not in resp.text


async def test_footer_privacy_link_present_on_entry_and_home(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert 'href="/privacy"' in resp.text


# ---------------------------------------------------------------------------
# Guest flow -> home renders created activities
# ---------------------------------------------------------------------------


async def test_guest_home_renders_seeded_starter_templates(client: AsyncClient) -> None:
    """Regression coverage for the rendering path when a guest has activities
    — decoupled from the (now-removed) auto-seed-on-guest trigger.
    """
    owner_id = await _guest_login(client)

    seed_test_activity(owner_id, name="Kendo")
    seed_test_activity(owner_id, name="Reading")

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert "Kendo" in resp.text
    assert "Reading" in resp.text


async def test_home_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_home_renders_in_place_for_real_user_past_consent_gate(
    client: AsyncClient,
) -> None:
    """A real (non-guest, has a username) account hitting /home renders the
    dashboard in place — no redirect to /@{username}. The consent gate (303
    to /welcome-sharing) only fires while consent_seen_at is NULL; signup
    here records consent via the form's checkbox in the same request."""
    resp = await client.post(
        "/auth/signup",
        data={"username": "homeinplace1", "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/welcome-sharing", data={"visibility": "private"}, follow_redirects=False
    )
    assert resp.status_code == 303

    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 200


async def test_home_renders_in_place_for_guest(client: AsyncClient) -> None:
    """A guest (no username) hitting /home still renders the activity list
    in place — no redirect. Guests have no public profile to redirect to."""
    await _guest_login(client)

    resp = await client.get("/home", follow_redirects=False)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Empty-state home: example cards + create-category
# ---------------------------------------------------------------------------


async def test_empty_home_shows_example_cards_and_start_from_scratch(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    _clear_seeded_data(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.HOME_EMPTY in text
    for example in categories.EXAMPLE_CATEGORIES:
        assert example["name"] in text
    assert 'hx-get="/activities/new"' in text
    assert strings_module.HOME_START_FROM_SCRATCH in text


async def test_new_category_form_renders(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/activities/new")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.ACTIVITY_NEW_TITLE in text
    assert strings_module.ACTIVITY_FORM_NAME_LABEL in text


async def test_new_category_form_hx_returns_sheet_fragment(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/activities/new", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    text = resp.text

    # A fragment (the sheet dialog), not a full document.
    assert "<!DOCTYPE html>" not in text
    assert 'role="dialog"' in text
    assert 'aria-modal="true"' in text

    # The category form is present: name input only (no icon picker).
    assert "<form" in text
    assert strings_module.ACTIVITY_FORM_NAME_LABEL in text
    assert 'id="category-name"' in text
    assert 'name="name"' in text


async def test_new_category_form_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/activities/new", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_create_category_manual_returns_card_fragment(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "Guitar"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    # A fragment, not a full document.
    assert "<!DOCTYPE html>" not in text
    assert "Guitar" in text

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT name, icon FROM category WHERE owner_id = ? AND name = 'Guitar'",
            (owner_id,),
        ).fetchone()
    assert row is not None
    # No icon picker in the create form -- the route doesn't accept/forward
    # an icon field, so the service default applies.
    assert row["icon"] == categories.DEFAULT_ICON


async def test_create_category_example_adopt(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)

    example = categories.EXAMPLE_CATEGORIES[0]
    resp = await client.post(
        "/activities",
        data={"name": example["name"]},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert example["name"] in resp.text

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT name, icon FROM category WHERE owner_id = ? AND name = ?",
            (owner_id, example["name"]),
        ).fetchone()
    assert row is not None
    # No icon picker in the create form -- the example's icon is metadata
    # the route no longer forwards; the service default applies.
    assert row["icon"] == categories.DEFAULT_ICON


async def test_create_category_via_sheet_hx_returns_activity_card_fragment(
    client: AsyncClient,
) -> None:
    """Regression: the sheet's HX flow (hx-post /categories, hx-target #cards,
    hx-swap beforeend) still returns an activity_card fragment for a valid name."""
    owner_id = await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "Calligraphy"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    # A fragment, not a full document.
    assert "<!DOCTYPE html>" not in text
    assert "<html" not in text
    assert "Calligraphy" in text

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT name FROM category WHERE owner_id = ? AND name = 'Calligraphy'",
            (owner_id,),
        ).fetchone()
    assert row is not None


async def test_create_category_no_js_redirects_to_home(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "Plain Category"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/home"

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT name FROM category WHERE owner_id = ? AND name = 'Plain Category'",
            (owner_id,),
        ).fetchone()
    assert row is not None

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert "Plain Category" in resp.text


async def test_create_category_no_js_empty_name_redirects_home(
    client: AsyncClient,
) -> None:
    """No-JS submission of a blank name has no standalone error page to
    re-render anymore — it redirects back to /home (the HTMX path below is
    the one that matters for real validation feedback)."""
    await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "   "},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/home"


async def test_create_category_hx_empty_name_rerenders_form_fragment_with_error(
    client: AsyncClient,
) -> None:
    await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "   "},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 400
    text = resp.text

    # Re-renders the bare form fragment (not the deleted standalone page).
    assert "<!DOCTYPE html>" not in text
    assert strings_module.ACTIVITY_FORM_NAME_REQUIRED in text
    assert 'id="category-name"' in text


async def test_create_category_ignores_stray_icon_field_and_uses_default(
    client: AsyncClient,
) -> None:
    """The create form has no icon picker and the route no longer accepts an
    icon field at all -- a stray `icon` in the POST body (e.g. from an old
    client) is simply ignored and the service default applies."""
    owner_id = await _guest_login(client)

    resp = await client.post(
        "/activities",
        data={"name": "Mystery", "icon": "not-a-real-icon"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT icon FROM category WHERE owner_id = ? AND name = 'Mystery'",
            (owner_id,),
        ).fetchone()
    assert row["icon"] == categories.DEFAULT_ICON


async def test_create_category_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.post(
        "/activities",
        data={"name": "Nope"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_home_with_categories_shows_add_category_row_last_in_cards(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.HOME_ADD_ACTIVITY in text

    cards_start = text.index('id="cards"')
    sheet_start = text.index('id="sheet"')
    add_category_idx = text.index(strings_module.HOME_ADD_ACTIVITY)
    # The "Add a category" row sits inside #cards, after the existing cards
    # and before the #cards div closes (i.e. before the #sheet mount point).
    assert cards_start < add_category_idx < sheet_start


async def test_empty_home_does_not_show_add_category_row(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    _clear_seeded_data(owner_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text

    # Empty-state stays unchanged: hanja gloss + empty message + example
    # adopt-cards + "start from scratch" link, with no "Add a category" row.
    assert strings_module.APP_NAME_HANJA in text
    assert strings_module.APP_GLOSS in text
    assert strings_module.HOME_EMPTY in text
    for example in categories.EXAMPLE_CATEGORIES:
        assert example["name"] in text
    assert strings_module.HOME_START_FROM_SCRATCH in text

    assert strings_module.HOME_ADD_ACTIVITY not in text


async def test_activity_card_falls_back_to_circle_dot_when_icon_null(
    client: AsyncClient,
) -> None:
    """A category row with icon IS NULL (pre-migration data) renders the
    circle-dot fallback icon rather than erroring."""
    owner_id = await _guest_login(client)

    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "INSERT INTO category (owner_id, name, icon, sort_order) VALUES (?, ?, NULL, 0)",
            (owner_id, "No Icon"),
        )
        category_id = cur.lastrowid
        conn.execute(
            "INSERT INTO activity (owner_id, category_id, name, count_mode, sort_order)"
            " VALUES (?, ?, ?, 'running', 0)",
            (owner_id, category_id, "No Icon"),
        )

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert "No Icon" in resp.text


# ---------------------------------------------------------------------------
# Masthead + footer — guest-only build: no account menu, delete-data dialog
# ---------------------------------------------------------------------------


async def test_account_route_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/account", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_masthead_has_wordmark_and_theme_toggle_only(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.APP_NAME in text
    assert 'hx-post="/preferences/theme"' in text
    assert "components/account_menu" not in text


async def test_logged_in_footer_has_privacy_export_import_and_logout(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.FOOTER_PRIVACY in text
    assert 'href="/privacy"' in text

    assert strings_module.FOOTER_EXPORT_DATA in text
    assert 'href="/export"' in text

    assert strings_module.FOOTER_IMPORT_DATA in text
    assert 'role="dialog"' in text
    assert 'aria-modal="true"' in text

    assert strings_module.FOOTER_LOGOUT in text
    assert 'hx-post="/auth/logout"' in text

    assert strings_module.FOOTER_DELETE_DATA not in text
    assert strings_module.DELETE_DATA_TITLE not in text
    assert 'hx-post="/auth/delete"' not in text


async def test_entry_footer_has_only_privacy_policy(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.FOOTER_PRIVACY in text
    assert 'href="/privacy"' in text

    assert strings_module.FOOTER_EXPORT_DATA not in text
    assert strings_module.FOOTER_IMPORT_DATA not in text
    assert strings_module.FOOTER_LOGOUT not in text
    assert 'hx-post="/auth/logout"' not in text
    assert 'hx-post="/auth/delete"' not in text


# ---------------------------------------------------------------------------
# Log -> fragment swap, count increments
# ---------------------------------------------------------------------------


async def test_log_returns_fragment_and_increments_count(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")

    with db.connect() as conn:
        conn.execute("BEGIN")
        activity_id = conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Kendo' AND st.name = 'Kendo'""",
            (owner_id,),
        ).fetchone()["id"]

    before = stats.counts(activity_id, owner_id, tz=_UTC)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    # A fragment, not a full document.
    assert "<!DOCTYPE html>" not in resp.text
    assert "<html" not in resp.text

    after = stats.counts(activity_id, owner_id, tz=_UTC)
    assert after["lifetime"] == before["lifetime"] + 1


async def test_log_unknown_activity_returns_404(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.post(
        "/activities/999999/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Date-only occurred_at field (log sheet)
# ---------------------------------------------------------------------------


async def test_log_sheet_renders_date_only_occurred_at_field(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/log",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    assert 'type="date"' in text
    assert strings_module.LOG_OCCURRED_AT_LABEL in text

    today = stats._today_local(_UTC).isoformat()
    assert f'value="{today}"' in text


async def test_log_with_no_occurred_at_preserves_time_of_day(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_row = conn.execute(
            "SELECT occurred_at FROM entry WHERE owner_id = ? AND activity_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()

    occurred_at = entry_row["occurred_at"]
    # No time given → date-only sentinel stored, time_known=0.
    assert "T00:00:00" in occurred_at


async def test_log_with_todays_date_preserves_time_of_day(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    today = stats._today_local(_UTC).isoformat()

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={"date": today},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_row = conn.execute(
            "SELECT occurred_at, time_known FROM entry WHERE owner_id = ? AND activity_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()

    occurred_at = entry_row["occurred_at"]
    # No time given → date-only sentinel, time_known=0, day is correct.
    assert "T00:00:00" in occurred_at
    assert entry_row["time_known"] == 0
    from app.services.entries import _local_day

    assert _local_day(occurred_at, _UTC).isoformat() == today


async def test_log_with_backfilled_past_date_sets_local_day(client: AsyncClient) -> None:
    from datetime import timedelta

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    yesterday = (stats._today_local(_UTC) - timedelta(days=1)).isoformat()

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={"date": yesterday},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_row = conn.execute(
            "SELECT occurred_at, time_known FROM entry WHERE owner_id = ? AND activity_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()

    from app.services.entries import _local_day

    occurred_at = entry_row["occurred_at"]
    assert _local_day(occurred_at, _UTC).isoformat() == yesterday
    # date-only submission must mark time as not known
    assert entry_row["time_known"] == 0


# ---------------------------------------------------------------------------
# Match-list sub-form (tournament entries) + competition stats (Task 8)
# ---------------------------------------------------------------------------


def _tournament_ids(owner_id: int) -> tuple[int, int]:
    """(activity_id, match_list field_def_id) for the seeded Kendo activity's
    match-list field — Task 3 merged the old standalone Tournament activity
    into the single Kendo activity, which still carries a match_list field_def."""
    activity_id = _practice_activity_id(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        field_def_id = conn.execute(
            "SELECT id FROM field_def WHERE activity_id = ? AND kind = 'match_list'",
            (activity_id,),
        ).fetchone()["id"]
    return activity_id, field_def_id


async def test_log_sheet_renders_match_sub_form_for_tournament(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/log",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert f"match_opponent_{field_def_id}_0" in resp.text
    assert f"match_score_{field_def_id}_0" in resp.text
    assert f"match_result_{field_def_id}_0" in resp.text


async def test_log_sheet_does_not_render_match_sub_form_for_non_tournament(
    client: AsyncClient,
) -> None:
    # The merged Kendo activity always carries a match_list field_def now
    # (Task 3), so the no-match-form fixture is the Reading activity, which
    # has no match_list field_def at all.
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Reading")
    activity_id = _reading_activity_id(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/log",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "match_opponent_" not in resp.text


async def test_add_match_row_appends_row_preserving_existing_values(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/match-rows/{field_def_id}/add",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Existing row's value survives the swap.
    assert 'value="김철수"' in resp.text
    # A second, empty row was appended.
    assert f"match_opponent_{field_def_id}_1" in resp.text


async def test_remove_match_row_drops_the_requested_row(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/match-rows/{field_def_id}/remove/0",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
            f"match_opponent_{field_def_id}_1": "박영희",
            f"match_score_{field_def_id}_1": "1-0",
            f"match_result_{field_def_id}_1": "loss",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # Row 0 (김철수) was removed; the remaining row is renumbered to index 0.
    assert "김철수" not in resp.text
    assert 'value="박영희"' in resp.text
    assert f"match_opponent_{field_def_id}_0" in resp.text
    assert f"match_opponent_{field_def_id}_1" not in resp.text


async def test_submitting_tournament_entry_persists_match_rows(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={
            f"match_opponent_{field_def_id}_0": "김철수",
            f"match_score_{field_def_id}_0": "2-1",
            f"match_result_{field_def_id}_0": "win",
            f"match_opponent_{field_def_id}_1": "박영희",
            f"match_score_{field_def_id}_1": "0-2",
            f"match_result_{field_def_id}_1": "loss",
            f"match_opponent_{field_def_id}_2": "이민수",
            f"match_score_{field_def_id}_2": "1-1",
            f"match_result_{field_def_id}_2": "draw",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]

    matches = competition.list_matches(owner_id, entry_id)
    assert len(matches) == 3
    assert {m["opponent"] for m in matches} == {"김철수", "박영희", "이민수"}
    assert {m["result"] for m in matches} == {"win", "loss", "draw"}

    record = competition.record(owner_id, activity_id)
    assert record["wins"] == 1
    assert record["losses"] == 1
    assert record["draws"] == 1
    assert record["decided"] == 3
    assert record["win_rate"] == pytest.approx(1 / 3)


async def test_submitting_tournament_entry_drops_incomplete_rows(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, field_def_id = _tournament_ids(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={
            f"match_opponent_{field_def_id}_0": "",
            f"match_score_{field_def_id}_0": "",
            f"match_result_{field_def_id}_0": "",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]

    assert competition.list_matches(owner_id, entry_id) == []


# ---------------------------------------------------------------------------
# Hashtag tag input (replaces chip-group)
# ---------------------------------------------------------------------------


def _technique_field_id(owner_id: int) -> tuple[int, int]:
    """(activity_id, tag_group field_def_id) for the test-fixture "Kendo" activity."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        activity_id = conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Kendo' AND st.name = 'Kendo'""",
            (owner_id,),
        ).fetchone()["id"]
        field_def_id = conn.execute(
            "SELECT id FROM field_def WHERE activity_id = ? AND kind = 'tag_group'",
            (activity_id,),
        ).fetchone()["id"]
    return activity_id, field_def_id


@pytest.mark.anyio
async def test_log_entry_with_hashtag_creates_tags(client: AsyncClient) -> None:
    """POSTing hashtags_{field_def_id}='#waza #randori' creates tags and entry_tag rows."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "#waza #randori"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]
        tag_rows = conn.execute(
            "SELECT t.name FROM entry_tag et JOIN tag t ON t.id = et.tag_id"
            " WHERE et.entry_id = ? ORDER BY t.name",
            (entry_id,),
        ).fetchall()

    tag_names = {r["name"] for r in tag_rows}
    assert "waza" in tag_names
    assert "randori" in tag_names


@pytest.mark.anyio
async def test_log_entry_hashtag_deduplicates(client: AsyncClient) -> None:
    """Duplicate hashtag tokens produce only one entry_tag row per tag."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "#waza #waza"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM entry_tag et JOIN tag t ON t.id = et.tag_id"
            " WHERE et.entry_id = ? AND t.name = 'waza'",
            (entry_id,),
        ).fetchone()["n"]

    assert count == 1


@pytest.mark.anyio
async def test_entry_edit_prepopulates_hashtag_field(client: AsyncClient) -> None:
    """The entry edit form pre-populates the hashtag input with existing tags."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    # Create an entry with a tag via the log route.
    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "#men"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]

    resp = await client.get(
        f"/activities/{activity_id}/entries/{entry_id}/edit",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # The hashtag text input must be pre-filled with the tag name.
    assert "#men" in resp.text


# ---------------------------------------------------------------------------
# Unified memo+hashtag field (combined "Notes" textarea)
# ---------------------------------------------------------------------------


async def test_log_entry_memo_with_hashtags(client: AsyncClient) -> None:
    """POSTing free text with hashtags stores the full text as memo and creates tag rows."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={
            f"hashtags_{field_def_id}": "Good session. #waza #tired",
            "date": stats._today_local(_UTC).isoformat(),
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_row = conn.execute(
            "SELECT id, memo FROM entry WHERE owner_id = ? AND activity_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()
        assert entry_row is not None
        assert entry_row["memo"] == "Good session. #waza #tired"

        entry_id = entry_row["id"]
        tag_rows = conn.execute(
            "SELECT t.name FROM entry_tag et JOIN tag t ON t.id = et.tag_id"
            " WHERE et.entry_id = ? ORDER BY t.name",
            (entry_id,),
        ).fetchall()

    tag_names = {r["name"] for r in tag_rows}
    assert len(tag_names) == 2
    assert "waza" in tag_names
    assert "tired" in tag_names


async def test_edit_entry_removes_tags_when_cleared(client: AsyncClient) -> None:
    """Editing an entry with plain text (no hashtags) clears all existing tags."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    # Create an entry with two tags.
    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "#morning #pr"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]
        initial_tag_count = conn.execute(
            "SELECT COUNT(*) AS n FROM entry_tag WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()["n"]

    assert initial_tag_count == 2

    # Edit the entry, replacing the combined field with plain text (no hashtags).
    resp = await client.post(
        f"/activities/{activity_id}/entries/{entry_id}",
        data={
            f"hashtags_{field_def_id}": "just notes no tags",
            "date": stats._today_local(_UTC).isoformat(),
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        memo_row = conn.execute(
            "SELECT memo FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        ).fetchone()
        remaining_tags = conn.execute(
            "SELECT COUNT(*) AS n FROM entry_tag WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()["n"]

    assert memo_row["memo"] == "just notes no tags"
    assert remaining_tags == 0


async def test_edit_form_prepopulates_memo_verbatim(client: AsyncClient) -> None:
    """The entry edit form pre-fills the combined field with the full stored memo."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "Felt strong. #morning"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200

    with db.connect() as conn:
        conn.execute("BEGIN")
        entry_id = conn.execute(
            "SELECT id FROM entry WHERE owner_id = ? AND activity_id = ? ORDER BY id DESC LIMIT 1",
            (owner_id, activity_id),
        ).fetchone()["id"]

    resp = await client.get(
        f"/activities/{activity_id}/entries/{entry_id}/edit",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    # The full stored memo must appear verbatim in the edit form response.
    assert "Felt strong. #morning" in resp.text


# ---------------------------------------------------------------------------
# Sub-tally detail screen + competition stats
# ---------------------------------------------------------------------------


async def test_detail_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/activities/1", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_detail_unknown_activity_returns_404(client: AsyncClient) -> None:
    await _guest_login(client)
    resp = await client.get("/activities/999999")
    assert resp.status_code == 404


async def test_non_tournament_detail_has_no_competition_stats(client: AsyncClient) -> None:
    # The merged Kendo activity always carries a match_list field_def now
    # (Task 3), so the no-competition-stats fixture is the Reading activity,
    # which has no match_list field_def at all.
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Reading")
    activity_id = _reading_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_TITLE not in resp.text


async def test_tournament_detail_shows_record_and_head_to_head(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, _field_def_id = _tournament_ids(owner_id)

    # Build a fixture: two outings, three bouts total against two opponents.
    from app.services import entries as entries_service

    entry_a = entries_service.create(owner_id, activity_id, {}, tz=_UTC)
    competition.add_matches(
        owner_id,
        entry_a["id"],
        [
            {"opponent": "김철수", "score": "2-1", "result": "win"},
            {"opponent": "박영희", "score": "0-2", "result": "loss"},
        ],
    )
    entry_b = entries_service.create(owner_id, activity_id, {}, tz=_UTC)
    competition.add_matches(
        owner_id,
        entry_b["id"],
        [{"opponent": "김철수", "score": "1-1", "result": "draw"}],
    )

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_TITLE in resp.text
    # Record: 1 win, 1 loss, 1 draw.
    assert "1" in resp.text and strings_module.MATCH_RESULT_WIN in resp.text
    # Head-to-head opponents both appear.
    assert "김철수" in resp.text
    assert "박영희" in resp.text


async def test_tournament_detail_win_rate_none_with_no_bouts(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id, _field_def_id = _tournament_ids(owner_id)

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    assert strings_module.STATS_WIN_RATE_NONE in resp.text


# ---------------------------------------------------------------------------
# Stats screens: calendar, heatmap, streak, distributions, progression
# ---------------------------------------------------------------------------


def _practice_activity_id(owner_id: int) -> int:
    """The id of the test-fixture "Kendo" activity created via
    ``seed_test_activity(owner_id, name="Kendo", ...)`` — a plain general-log
    activity (memo + tag_group, plus a match_list field for the tournament
    fixtures below); "Kendo" is just a fixture name here, not a feature."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Kendo' AND st.name = 'Kendo'""",
            (owner_id,),
        ).fetchone()["id"]


def _reading_activity_id(owner_id: int) -> int:
    """The id of the test-fixture "Reading" activity (a second, distinct
    general-log activity created via ``seed_test_activity(owner_id,
    name="Reading")`` — used where a test needs an activity with no
    match_list field_def)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Reading'""",
            (owner_id,),
        ).fetchone()["id"]


async def test_detail_shows_calendar_with_marked_today(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    assert "cal-day--marked" in resp.text
    assert "cal-day--today" in resp.text


async def test_history_year_view_shows_heatmap_grid_with_bucketed_cells(
    client: AsyncClient,
) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    resp = await client.get(f"/activities/{activity_id}/history?period=year")
    assert resp.status_code == 200
    # Calendar-year (Jan 1 - Dec 31) -> 365 .heat-cell elements (non-leap years).
    assert resp.text.count('class="heat-cell heat-cell--') == 365
    assert 'role="img"' in resp.text
    assert strings_module.HISTORY_YEAR_HEATMAP_ARIA_LABEL in resp.text
    # At least one bucketed cell reflects today's entry.
    assert "heat-cell--0" in resp.text
    assert any(f"heat-cell--{n}" in resp.text for n in (1, 2, 3, 4))


async def test_detail_streak_matches_stats_service(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    expected = stats.streaks(activity_id, owner_id, tz=_UTC)

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    assert f"{expected['current']}{strings_module.STREAK_DAYS_UNIT}" in resp.text
    assert f"{expected['longest']}{strings_module.STREAK_DAYS_UNIT}" in resp.text


def _hero_streak_caption(streak: int) -> str:
    """The exact text the hero-zone advance-line caption renders for a given
    streak value — ``"{HOME_STREAK_LABEL} {n}{HOME_STREAK_DAYS_UNIT}"`` inside
    ``activity_card.html.jinja2``'s ``<span class="ms-2">``. Built from the
    label + days-unit together (not the bare ``HOME_STREAK_LABEL`` alone)
    because ``STATS_STREAKS_LABEL`` ("Streaks") on the Summary card contains
    ``HOME_STREAK_LABEL`` ("Streak") as a substring."""
    return f"{strings_module.HOME_STREAK_LABEL} {streak}{strings_module.HOME_STREAK_DAYS_UNIT}"


async def test_home_card_hero_keeps_streak_caption(client: AsyncClient) -> None:
    """The home card's advance-line caption still carries the streak caption
    (label + count + unit) — the dedup macro's ``show_streak`` default is
    ``True`` for the linked (home-card) branch, since home has no nearby
    Summary card repeating it (Task 13's "home card unaffected")."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)
    expected_streak = stats.streaks(activity_id, owner_id, tz=_UTC)["current"]

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert _hero_streak_caption(expected_streak) in resp.text


async def test_detail_hero_suppresses_streak_caption_but_summary_card_keeps_it_once(
    client: AsyncClient,
) -> None:
    """The activity-detail hero zone (the dedup'd ``card_body(show_streak=...)``
    macro, ``hero_only=True``) no longer repeats the streak caption: the
    hero-style "Streak {n} days" caption is entirely absent from the detail
    page, while the Summary card's own (differently-labeled) current/longest
    streak still renders exactly once via ``STREAK_CURRENT_LABEL``/
    ``STREAK_LONGEST_LABEL`` (Task 13 build-plan item)."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)
    expected_streak = stats.streaks(activity_id, owner_id, tz=_UTC)["current"]

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    body = resp.text
    # Hero-zone streak caption (home card's exact wording) never appears here.
    assert _hero_streak_caption(expected_streak) not in body
    # The Summary card's streak labels appear exactly once each.
    assert body.count(strings_module.STREAK_CURRENT_LABEL) == 1
    assert body.count(strings_module.STREAK_LONGEST_LABEL) == 1


async def test_history_context_week_anchor_math(web_db: Path) -> None:
    from datetime import date

    from app.routes.web import _build_history_context

    # Anchor=2026-06-08 is a Monday -> week is 06-08..06-14.
    # Uses a fresh migrated DB (no entries); tests only the date-arithmetic shape.
    ctx = _build_history_context(
        activity_id=1, owner_id=1, period="week", anchor=date(2026, 6, 8), tz=_UTC
    )
    assert ctx["start"] == "2026-06-08"
    assert ctx["end"] == "2026-06-14"
    assert ctx["prev_anchor"] == "2026-06-01"
    assert ctx["next_anchor"] == "2026-06-15"
    assert ctx["period"] == "week"
    assert ctx["label"] == "2026-06-08 – 2026-06-14"
    assert ctx["visual"]["days"][0]["date"] == "2026-06-08"
    assert len(ctx["visual"]["days"]) == 7


async def test_history_context_month_anchor_math(web_db: Path) -> None:
    from datetime import date

    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=1, owner_id=1, period="month", anchor=date(2026, 6, 15), tz=_UTC
    )
    assert ctx["start"] == "2026-06-01"
    assert ctx["end"] == "2026-06-30"
    assert ctx["prev_anchor"] == "2026-05-01"
    assert ctx["next_anchor"] == "2026-07-01"
    assert ctx["label"] == "2026.06"
    # Reuses the calendar context shape.
    assert "weeks" in ctx["visual"]


async def test_history_context_year_anchor_math(web_db: Path) -> None:
    from datetime import date

    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=1, owner_id=1, period="year", anchor=date(2026, 6, 15), tz=_UTC
    )
    assert ctx["start"] == "2026-01-01"
    assert ctx["end"] == "2026-12-31"
    assert ctx["prev_anchor"] == "2025-01-01"
    assert ctx["next_anchor"] == "2027-01-01"
    assert ctx["label"] == "2026"
    assert "cells" in ctx["visual"]
    assert len(ctx["visual"]["cells"]) == 365


async def test_history_context_log_groups_entries_by_day_newest_first(
    client: AsyncClient,
) -> None:
    from app.routes.web import _build_history_context
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    today = stats._today_local(_UTC)
    ctx = _build_history_context(
        activity_id=activity_id, owner_id=owner_id, period="month", anchor=today, tz=_UTC
    )
    assert ctx["log"], "expected at least one day group"
    assert ctx["log"][0]["day"] == today.isoformat()
    assert len(ctx["log"][0]["entries"]) == 1


async def test_history_context_week_selected_populates_day_entries(
    client: AsyncClient,
) -> None:
    """*selected* support extends to ``period="week"`` (Task 3 build-plan item),
    not just ``month`` — same ``_entries_on_day`` call, same return shape."""
    from app.routes.web import _build_history_context
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    today = stats._today_local(_UTC)
    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    ctx = _build_history_context(
        activity_id=activity_id,
        owner_id=owner_id,
        period="week",
        anchor=today,
        tz=_UTC,
        selected=today,
    )
    assert ctx["selected_day"] == today.isoformat()
    assert ctx["day_entries"] is not None
    assert len(ctx["day_entries"]) == 1


async def test_history_context_week_selected_with_no_entries_is_empty_not_none(
    web_db: Path,
) -> None:
    """A selected day with no entries returns an empty list, distinguishing
    "selected, nothing logged" from "nothing selected" (``None``)."""
    from datetime import date

    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=1,
        owner_id=1,
        period="week",
        anchor=date(2026, 6, 8),
        tz=_UTC,
        selected=date(2026, 6, 9),
    )
    assert ctx["selected_day"] == "2026-06-09"
    assert ctx["day_entries"] == []


async def test_history_context_decorates_log_entries_with_comment_count(
    client: AsyncClient,
) -> None:
    """Every entry in ``log`` carries a ``comment_count`` key, derived from
    ``comments.counts_for_entries`` — not a leftover/missing key."""
    from app.routes.web import _build_history_context
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    entry = entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    with db.connect() as conn:
        conn.execute("BEGIN")
        comments_service.create_comment(conn, entry["id"], author_id=owner_id, body="nice work")

    today = stats._today_local(_UTC)
    ctx = _build_history_context(
        activity_id=activity_id, owner_id=owner_id, period="month", anchor=today, tz=_UTC
    )
    logged_entry = ctx["log"][0]["entries"][0]
    assert logged_entry["comment_count"] == 1


async def test_history_context_decorates_day_entries_with_comment_count(
    client: AsyncClient,
) -> None:
    """``day_entries`` (the selected-day detail list) also carries
    ``comment_count`` per entry, not just the day-grouped ``log``."""
    from app.routes.web import _build_history_context
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    entry = entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    with db.connect() as conn:
        conn.execute("BEGIN")
        comments_service.create_comment(conn, entry["id"], author_id=owner_id, body="great")
        comments_service.create_comment(conn, entry["id"], author_id=owner_id, body="great again")

    today = stats._today_local(_UTC)
    ctx = _build_history_context(
        activity_id=activity_id,
        owner_id=owner_id,
        period="month",
        anchor=today,
        tz=_UTC,
        selected=today,
    )
    assert ctx["day_entries"][0]["comment_count"] == 2


async def test_history_context_no_entries_skips_comment_lookup(web_db: Path) -> None:
    """An empty log/day_entries doesn't blow up the comment-count decoration
    (no entry ids to look up)."""
    from datetime import date

    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=1, owner_id=1, period="all", anchor=date(2026, 6, 8), tz=_UTC
    )
    assert ctx["log"] == []


async def test_history_context_passes_through_new_kwargs_unchanged(web_db: Path) -> None:
    """*is_owner*/*can_comment*/*username*/*slug* pass straight through into
    the returned context, faithfully including ``None`` (e.g. a guest-owned
    activity with no public URL) — this function does no suppression itself."""
    from datetime import date

    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=1,
        owner_id=1,
        period="week",
        anchor=date(2026, 6, 8),
        tz=_UTC,
        is_owner=True,
        can_comment=True,
        username="alice",
        slug="practice",
    )
    assert ctx["is_owner"] is True
    assert ctx["can_comment"] is True
    assert ctx["username"] == "alice"
    assert ctx["slug"] == "practice"

    ctx_defaults = _build_history_context(
        activity_id=1, owner_id=1, period="all", anchor=date(2026, 6, 8), tz=_UTC
    )
    assert ctx_defaults["is_owner"] is False
    assert ctx_defaults["can_comment"] is False
    assert ctx_defaults["username"] is None
    assert ctx_defaults["slug"] is None


async def test_history_route_week_day_tap_selects_cell_and_renders_entries(
    client: AsyncClient,
) -> None:
    """Tapping a day in week view (Task 4 build-plan item) renders the same
    day-entries affordance as month view: the day-detail body state replaces
    the week strip entirely (Task 5) and the day's entries are rendered via
    the shared ``day_entries.html.jinja2`` partial."""
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    entries_service.create(owner_id, activity_id, {"memo": "week tap test"}, tz=_UTC)

    today = stats._today_local(_UTC)
    resp = await client.get(
        f"/activities/{activity_id}/history?period=week&anchor={today.isoformat()}"
        f"&day={today.isoformat()}"
    )
    assert resp.status_code == 200
    # The week strip's own .cal-day cells are gone once a day is selected --
    # only the back-control + that day's entries remain.
    assert "cal-day--selected" not in resp.text
    assert strings_module.CALENDAR_DAY_ENTRIES_TITLE in resp.text
    assert "week tap test" in resp.text
    assert strings_module.CALENDAR_BACK_TO_CALENDAR in resp.text


async def test_history_route_week_day_tap_button_targets_week_period(
    client: AsyncClient,
) -> None:
    """The week strip's day cells are real ``hx-get`` buttons parameterized
    for ``period=week`` (not month) -- the gap this task closes."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}/history?period=week")
    assert resp.status_code == 200
    assert f"/activities/{activity_id}/history?period=week&anchor=" in resp.text
    assert f'hx-target="#history-{activity_id}"' in resp.text


async def test_history_route_day_grouping_uses_owners_stored_timezone(
    client: AsyncClient,
) -> None:
    """The ``/history`` route buckets entries by the *owner's* stored
    ``user.timezone`` (fetched via ``get_user_timezone``), not UTC.

    An entry logged at 02:00 UTC on 2026-06-15 is 2026-06-14 in
    America/Los_Angeles (UTC-7 in June) but still 2026-06-15 in UTC — the
    route must reflect the owner's timezone in the rendered log grouping.
    """
    from app.services import entries as entries_service

    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    # Pin the owner's timezone to America/Los_Angeles (UTC-7 in June).
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET timezone = ? WHERE id = ?",
            ("America/Los_Angeles", owner_id),
        )

    entries_service.create(
        owner_id,
        activity_id,
        {},
        occurred_at="2026-06-15T02:00:00+00:00",
        tz=ZoneInfo("America/Los_Angeles"),
    )

    resp = await client.get(f"/activities/{activity_id}/history?period=month&anchor=2026-06-15")
    assert resp.status_code == 200
    # 02:00 UTC on 2026-06-15 is 2026-06-14 19:00 in America/Los_Angeles —
    # the log entry should be grouped under the 14th, not the 15th.
    assert "2026-06-14" in resp.text


async def test_history_route_unknown_activity_anonymous_returns_404(client: AsyncClient) -> None:
    """No session, unknown activity id: 404, not 401 — this route now serves
    non-owner viewers too (per the read-only calendar parity fix), so an
    unauthenticated request is just another viewer the capability helper has
    to resolve; with no activity to resolve an owner from, it fails closed to
    404 rather than leaking a stale "you must be logged in" 401 that implied
    the activity might exist for *someone* logged in."""
    resp = await client.get("/activities/1/history?period=week")
    assert resp.status_code == 404


async def test_history_route_private_activity_anonymous_returns_404(client: AsyncClient) -> None:
    """No session, a real activity owned by a private (non-public) account:
    404 — the anonymous viewer fails ``can_view_activity_detail`` (limited),
    so this fails closed exactly like the page-load route does for `limited`
    detail requests, never leaking entry data."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    await client.post("/auth/logout")

    resp = await client.get(f"/activities/{activity_id}/history?period=week")
    assert resp.status_code == 404


async def test_history_route_unknown_activity_returns_404(client: AsyncClient) -> None:
    await _guest_login(client)
    resp = await client.get("/activities/999999/history?period=week")
    assert resp.status_code == 404


async def test_history_route_invalid_period_returns_400(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}/history?period=decade")
    assert resp.status_code == 400


async def test_history_route_invalid_anchor_returns_400(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}/history?period=week&anchor=not-a-date")
    assert resp.status_code == 400


async def test_history_route_default_anchor_is_today(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    today = stats._today_local(_UTC)
    # The route 500s until Task 3 lands components/history.html.jinja2; we only
    # assert it gets as far as building context (no 400/401/404) by checking
    # the context directly instead of the rendered route.
    from app.routes.web import _build_history_context

    ctx = _build_history_context(
        activity_id=activity_id, owner_id=owner_id, period="week", anchor=today, tz=_UTC
    )
    assert ctx["anchor"] == today.isoformat()


# NOTE: test_kendo_grading_detail_shows_dan_and_next_stage_and_shogo and
# test_reading_detail_shows_tier_and_count_to_next previously lived here.
# Both tested the progression/level-ladder feature (dan/shōgō gates, reading
# tiers) removed wholesale in meetings/MEETING-2026-06-21-simplify-onboarding
# (migration 0013_drop_progression.sql drops field_def.kind 'level'/'result'
# from the CHECK entirely, plus the level/level_rule tables). They are deleted
# rather than adapted — there is no replacement feature for a fixture helper
# to stand in for. Out of scope for this fixture migration; owned by whoever
# does the progression-removal cleanup pass over app/ui_strings.py and
# app/templates/components/progression_status.html.jinja2, which still
# reference the dead feature.


async def test_home_does_not_render_heavy_stats(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")

    resp = await client.get("/home")
    assert resp.status_code == 200
    text = resp.text
    assert "heat-cell" not in text
    assert "cal-day" not in text
    assert strings_module.STATS_SUMMARY_TITLE not in text


# ---------------------------------------------------------------------------
# Owner-view comment affordance on /@{username}/{slug}
# (meetings/MEETING-2026-06-20-comment-notifications/3-BUILD-PLAN.md, Task 1)
# ---------------------------------------------------------------------------


async def _signup_with_username(client: AsyncClient, username: str) -> int:
    """Sign up a username/password account and clear its one-time consent gate.

    Returns the owner_id. Mirrors ``tests/integration/test_entry_comments.py``'s
    ``_signup`` helper (kept local here since that module isn't shared/imported
    across test files).
    """
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    owner_id = int(resp.json()["user_id"])
    from app.auth import users as users_module

    users_module.set_visibility_consent(owner_id, "private")
    return owner_id


def _make_activity_with_entry(owner_id: int, *, name: str = "Running") -> tuple[str, int]:
    """Create a fresh activity + one entry for *owner_id*; return (slug, entry_id)."""
    from app.services import entries as entries_service

    result = categories.create_activity(owner_id, name=name)
    activity_id = result["activity_id"]
    entry = entries_service.create(owner_id, activity_id, tz=_UTC)
    with db.connect() as conn:
        conn.execute("BEGIN")
        slug = conn.execute("SELECT slug FROM activity WHERE id = ?", (activity_id,)).fetchone()[
            "slug"
        ]
    return slug, entry["id"]


async def test_owner_view_shows_comment_affordance_and_can_post_on_own_entry(
    client: AsyncClient,
) -> None:
    owner_id = await _signup_with_username(client, "owner_comment1")
    slug, entry_id = _make_activity_with_entry(owner_id)

    resp = await client.get(f"/@owner_comment1/{slug}")
    assert resp.status_code == 200
    # Zero-comment entry still renders the toggle affordance (can_comment is
    # True for the owner), so the composer is reachable for the first comment.
    assert f"/entries/{entry_id}/comments" in resp.text
    assert f'id="comment-slot-{entry_id}"' in resp.text

    comments_url = f"/@owner_comment1/{slug}/entries/{entry_id}/comments"
    get_resp = await client.get(comments_url)
    assert get_resp.status_code == 200
    assert "<form" in get_resp.text
    assert "<textarea" in get_resp.text

    post_resp = await client.post(comments_url, data={"body": "noting my own progress"})
    assert post_resp.status_code == 200
    assert "noting my own progress" in post_resp.text

    # Reloading the page now shows a non-zero comment count.
    second_page = await client.get(f"/@owner_comment1/{slug}")
    assert second_page.status_code == 200
    assert strings_module.COMMENTS_COUNT_LABEL.format(count=1) in second_page.text


async def test_owner_view_zero_comment_entries_render_no_count_glyph(
    client: AsyncClient,
) -> None:
    """Zero-comment entries must not show a count — the affordance itself
    renders (so the owner can start a thread), but the count ``<span>`` is
    absent from markup for that entry (the toggle button renders bare,
    glyph-only, with no inner count span at all when ``comment_count`` is
    zero — ``COMMENTS_COUNT_LABEL`` is just ``"{count}"``, too generic to
    assert on directly without colliding with unrelated digits elsewhere on
    the page, e.g. the htmx CDN script tag's version pin)."""
    owner_id = await _signup_with_username(client, "owner_comment2")
    slug, entry_id = _make_activity_with_entry(owner_id)

    resp = await client.get(f"/@owner_comment2/{slug}")
    assert resp.status_code == 200
    # The toggle button is present (can_comment is True for the owner)...
    assert f"/entries/{entry_id}/comments" in resp.text
    # ...but it carries no inner <span> (the count span only renders when
    # comment_count is truthy) — assert by isolating the button's own markup.
    button_start = resp.text.index(f"/entries/{entry_id}/comments")
    button_end = resp.text.index("</button>", button_start)
    button_markup = resp.text[button_start:button_end]
    assert "<span>" not in button_markup


async def test_owner_view_invalid_c_param_falls_back_to_collapsed(
    client: AsyncClient,
) -> None:
    owner_id = await _signup_with_username(client, "owner_comment4")
    slug, entry_id = _make_activity_with_entry(owner_id)

    # Non-numeric value.
    resp = await client.get(f"/@owner_comment4/{slug}?c=not-a-number")
    assert resp.status_code == 200
    assert 'hx-trigger="load"' not in resp.text

    # Unknown entry id.
    resp2 = await client.get(f"/@owner_comment4/{slug}?c=999999")
    assert resp2.status_code == 200
    assert 'hx-trigger="load"' not in resp2.text


async def test_owner_view_cross_activity_c_param_is_ignored(client: AsyncClient) -> None:
    owner_id = await _signup_with_username(client, "owner_comment5")
    slug_a, _entry_a_id = _make_activity_with_entry(owner_id, name="Running")
    _slug_b, entry_b_id = _make_activity_with_entry(owner_id, name="Reading log")

    # entry_b_id belongs to a different activity than slug_a's.
    resp = await client.get(f"/@owner_comment5/{slug_a}?c={entry_b_id}")
    assert resp.status_code == 200
    assert 'hx-trigger="load"' not in resp.text


async def test_owner_view_c_param_for_past_month_entry_selects_day_and_expands(
    client: AsyncClient,
) -> None:
    """``?c={entry_id}`` for an entry logged in a past month lands the owner

    on that month (not the current one), with that day pre-selected in the
    calendar and that entry's comment-thread toggle carrying the extra
    ``load`` trigger so it auto-expands — no manual day-tap needed.
    """
    owner_id = await _signup_with_username(client, "owner_comment6")
    result = categories.create_activity(owner_id, name="Running")
    activity_id = result["activity_id"]

    past_day = "2026-03-14"
    entry = entries.create(owner_id, activity_id, occurred_at=f"{past_day}T09:00:00", tz=_UTC)
    entry_id = entry["id"]
    with db.connect() as conn:
        conn.execute("BEGIN")
        slug = conn.execute("SELECT slug FROM activity WHERE id = ?", (activity_id,)).fetchone()[
            "slug"
        ]

    resp = await client.get(f"/@owner_comment6/{slug}?c={entry_id}")
    assert resp.status_code == 200
    # Landed on March 2026 (the entry's month), not the current month.
    assert "2026.03" in resp.text
    # The day-detail body state renders -- the month grid is gone entirely
    # (Task 5: a selected day replaces the grid, it doesn't coexist with it),
    # and the back-control + this day's detail panel are present instead.
    assert "cal-day--selected" not in resp.text
    assert strings_module.CALENDAR_BACK_TO_CALENDAR in resp.text
    assert f"{strings_module.CALENDAR_DAY_ENTRIES_TITLE} — {past_day}" in resp.text
    # The day-entries comment toggle for this entry auto-fires on load.
    assert f'id="comment-slot-{entry_id}"' in resp.text
    assert 'hx-trigger="click, load"' in resp.text


# ---------------------------------------------------------------------------
# Hardcoded-copy guard (English/US pivot — no Hangul anywhere in app-facing
# source; templates/ui_strings.py stay English-only)
# ---------------------------------------------------------------------------

# Matches Hangul syllable codepoints (가-힣). Does NOT match the 無心 hanja
# mark (Mushin's brand gloss, U+7121 U+5FC3), which is in the CJK Unified
# Ideographs block, not the Hangul Syllables block — it is intentionally
# allowed everywhere.
_HANGUL_RE = re.compile(r"[가-힣]")

# Jinja comments, possibly spanning multiple lines: {# ... #}
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)


def _strip_jinja_comments(text: str) -> str:
    """Remove ``{# ... #}`` Jinja comments (incl. multi-line) from *text*.

    Replaces each comment with the same number of newlines it spanned, so
    line numbers in the remaining text are unaffected.
    """

    def _blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return _JINJA_COMMENT_RE.sub(_blank, text)


def test_no_hardcoded_copy_in_templates() -> None:
    """No Hangul (U+AC00-U+D7A3) anywhere in ``app/templates/**`` or
    ``app/ui_strings.py``.

    Following the English/US pivot, the app is English-only — including
    template comments. The 無心 hanja brand mark (CJK Unified Ideographs, not
    Hangul) is unaffected by this guard and may appear freely.

    This test enumerates every line containing Hangul and fails loudly,
    naming the file + line, so any reintroduced non-English hardcoded copy
    (UI text or comments) is caught immediately.
    """
    app_dir = Path(__file__).resolve().parents[2] / "app"
    templates_dir = app_dir / "templates"
    offenders: list[str] = []

    paths = sorted(templates_dir.rglob("*.jinja2"))
    paths += sorted(templates_dir.rglob("*.html"))
    paths.append(app_dir / "ui_strings.py")

    for path in paths:
        raw_text = path.read_text(encoding="utf-8")
        stripped_text = _strip_jinja_comments(raw_text)
        raw_lines = raw_text.splitlines()
        stripped_lines = stripped_text.splitlines()
        for lineno, (raw_line, stripped_line) in enumerate(
            zip(raw_lines, stripped_lines, strict=True), start=1
        ):
            if _HANGUL_RE.search(stripped_line):
                rel = path.relative_to(app_dir.parent)
                offenders.append(f"{rel}:{lineno}: {raw_line.strip()}")

    assert not offenders, (
        "Hardcoded Hangul text found in app/ (English/US pivot — non-English "
        "copy should not remain in templates or ui_strings.py):\n" + "\n".join(offenders)
    )


async def test_history_fragment_renders_for_all_periods(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    from app.services import entries as entries_service

    entries_service.create(owner_id, activity_id, {}, tz=_UTC)

    resp = await client.get(f"/activities/{activity_id}")
    assert resp.status_code == 200
    # Detail page renders the unified history component for the default
    # month view, with no leftover references to removed calendar/heatmap
    # context keys.
    assert f'id="history-{activity_id}"' in resp.text
    assert 'role="tablist"' in resp.text

    for period in ("week", "month", "year"):
        r = await client.get(f"/activities/{activity_id}/history?period={period}")
        assert r.status_code == 200, (period, r.text[:500])
        txt = r.text
        assert f'id="history-{activity_id}"' in txt
        assert 'role="tablist"' in txt


# ---------------------------------------------------------------------------
# Stats-summary fragment (GET /activities/{id}/stats-summary)
# ---------------------------------------------------------------------------


async def test_stats_summary_fragment_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated GET returns 401."""
    resp = await client.get("/activities/1/stats-summary")
    assert resp.status_code == 401


async def test_stats_summary_fragment_404_for_wrong_owner(client: AsyncClient) -> None:
    """Authenticated as user A, GET stats-summary for user B's sub-tally returns 404."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    # Switch to a different user.
    client.cookies.clear()
    await _guest_login(client)

    resp = await client.get(f"/activities/{activity_id}/stats-summary")
    assert resp.status_code == 404


async def test_stats_summary_fragment_returns_section_html(client: AsyncClient) -> None:
    """Authenticated as owner, returns 200 with the stats-summary section and HTMX attrs."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}/stats-summary")
    assert resp.status_code == 200
    text = resp.text

    # Not a full document — a bare section fragment.
    assert "<!DOCTYPE html>" not in text
    assert "<html" not in text

    # The section id targets the correct sub-tally.
    assert f'id="stats-summary-{activity_id}"' in text
    # HTMX self-refresh wiring is present (is_owner=True path).
    assert "hx-trigger" in text
    assert f'hx-get="/activities/{activity_id}/stats-summary"' in text


# ---------------------------------------------------------------------------
# Field-stats fragment (GET /activities/{id}/field-stats)
# ---------------------------------------------------------------------------


async def test_field_stats_fragment_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated GET returns 401."""
    resp = await client.get("/activities/1/field-stats")
    assert resp.status_code == 401


async def test_field_stats_fragment_404_for_wrong_owner(client: AsyncClient) -> None:
    """Authenticated as user A, GET field-stats for user B's activity returns 404."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    client.cookies.clear()
    await _guest_login(client)

    resp = await client.get(f"/activities/{activity_id}/field-stats")
    assert resp.status_code == 404


async def test_field_stats_fragment_returns_htmx_wrapper(client: AsyncClient) -> None:
    """Authenticated as owner, returns 200 with the HTMX self-refresh wrapper."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(f"/activities/{activity_id}/field-stats")
    assert resp.status_code == 200
    text = resp.text

    assert "<!DOCTYPE html>" not in text
    assert "<html" not in text
    assert f'id="field-stats-{activity_id}"' in text
    assert f'hx-get="/activities/{activity_id}/field-stats"' in text
    assert "hx-trigger" in text


@pytest.mark.anyio
async def test_field_stats_shows_tag_after_log(client: AsyncClient) -> None:
    """After logging an entry with a hashtag, the field-stats fragment returns that tag."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo")
    activity_id, field_def_id = _technique_field_id(owner_id)

    await client.post(
        f"/activities/{activity_id}/log",
        data={f"hashtags_{field_def_id}": "#kirikaeshi"},
        headers={"HX-Request": "true"},
    )

    resp = await client.get(f"/activities/{activity_id}/field-stats")
    assert resp.status_code == 200
    assert "kirikaeshi" in resp.text


# ---------------------------------------------------------------------------
# Theme toggle
# ---------------------------------------------------------------------------


async def test_theme_toggle_renders_on_logged_out_entry_screen(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert 'hx-post="/preferences/theme"' in resp.text


async def test_theme_toggle_cycles_light_dark_system(client: AsyncClient) -> None:
    # No cookie yet -> current is "system" -> next is "light".
    resp = await client.post("/preferences/theme")
    assert resp.status_code == 200
    assert resp.cookies.get("mushin_theme") == "light"
    assert strings_module.THEME_TOGGLE_LABEL_LIGHT in resp.text
    assert 'hx-post="/preferences/theme"' in resp.text
    assert 'hx-swap="outerHTML"' in resp.text

    # "light" -> "dark"
    resp = await client.post("/preferences/theme")
    assert resp.status_code == 200
    assert resp.cookies.get("mushin_theme") == "dark"
    assert strings_module.THEME_TOGGLE_LABEL_DARK in resp.text

    # "dark" -> "system"
    resp = await client.post("/preferences/theme")
    assert resp.status_code == 200
    assert resp.cookies.get("mushin_theme") == "system"
    assert strings_module.THEME_TOGGLE_LABEL_SYSTEM in resp.text


async def test_theme_cookie_sets_data_theme_attribute_on_html(client: AsyncClient) -> None:
    # Default (no cookie): no data-theme attribute, so prefers-color-scheme applies.
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "data-theme" not in resp.text

    # Cycle to "light" and confirm the next full-page render carries it.
    resp = await client.post("/preferences/theme")
    assert resp.cookies.get("mushin_theme") == "light"

    resp = await client.get("/")
    assert resp.status_code == 200
    assert '<html lang="en" data-theme="light">' in resp.text

    # Cycle to "dark".
    resp = await client.post("/preferences/theme")
    assert resp.cookies.get("mushin_theme") == "dark"

    resp = await client.get("/")
    assert resp.status_code == 200
    assert '<html lang="en" data-theme="dark">' in resp.text

    # Cycle to "system": data-theme attribute disappears again.
    resp = await client.post("/preferences/theme")
    assert resp.cookies.get("mushin_theme") == "system"

    resp = await client.get("/")
    assert resp.status_code == 200
    assert "data-theme" not in resp.text


# ---------------------------------------------------------------------------
# /account settings — visibility toggle (Task 4)
# ---------------------------------------------------------------------------


async def _signup_login(client: AsyncClient, username: str = "owner") -> None:
    """Create a non-guest username/password account and start its session."""
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200


async def test_account_shows_visibility_and_share_link_for_non_guest(
    client: AsyncClient,
) -> None:
    await _signup_login(client, "alice")

    resp = await client.get("/account")
    assert resp.status_code == 200
    text = resp.text

    # Share-link line carries the username as a public handle.
    assert strings_module.ACCOUNT_VISIBILITY_SHARE_LINK.format(username="alice") in text
    # The toggle is present, and a fresh account defaults to private.
    assert 'name="visibility"' in text
    assert 'action="/account/visibility"' in text
    assert strings_module.ACCOUNT_VISIBILITY_CURRENT_PRIVATE in text


async def test_account_toggle_persists_public_and_reflects_after_redirect(
    client: AsyncClient,
) -> None:
    await _signup_login(client, "bob")

    resp = await client.post(
        "/account/visibility", data={"visibility": "public"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/account"

    # The page now reflects the persisted value.
    resp = await client.get("/account")
    assert resp.status_code == 200
    assert strings_module.ACCOUNT_VISIBILITY_CURRENT_PUBLIC in resp.text
    # The public radio is pre-checked (whitespace-tolerant).
    assert re.search(r'value="public"\s+checked', resp.text) is not None


async def test_account_toggle_persists_back_to_private(client: AsyncClient) -> None:
    await _signup_login(client, "carol")

    await client.post("/account/visibility", data={"visibility": "public"})
    resp = await client.post(
        "/account/visibility", data={"visibility": "private"}, follow_redirects=False
    )
    assert resp.status_code == 303

    resp = await client.get("/account")
    assert strings_module.ACCOUNT_VISIBILITY_CURRENT_PRIVATE in resp.text


async def test_account_hides_visibility_ui_for_guest(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/account")
    assert resp.status_code == 200
    text = resp.text

    # No toggle, no share-link section for a guest (no username, no public profile).
    assert 'name="visibility"' not in text
    assert 'action="/account/visibility"' not in text
    assert strings_module.ACCOUNT_VISIBILITY_HEADING not in text


async def test_account_visibility_rejects_invalid_value(client: AsyncClient) -> None:
    await _signup_login(client, "dave")

    resp = await client.post(
        "/account/visibility", data={"visibility": "everyone"}, follow_redirects=False
    )
    assert resp.status_code == 400

    # Nothing persisted — still private.
    resp = await client.get("/account")
    assert strings_module.ACCOUNT_VISIBILITY_CURRENT_PRIVATE in resp.text


async def test_account_visibility_guest_cannot_toggle(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.post(
        "/account/visibility", data={"visibility": "public"}, follow_redirects=False
    )
    assert resp.status_code == 400


async def test_account_visibility_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.post(
        "/account/visibility", data={"visibility": "public"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_footer_has_account_link_for_logged_in_user(client: AsyncClient) -> None:
    await _guest_login(client)

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert 'href="/account"' in resp.text
    assert strings_module.FOOTER_ACCOUNT in resp.text


# ---------------------------------------------------------------------------
# Sub-tally rename (Task 4b)
# ---------------------------------------------------------------------------


async def _create_named_account(client: AsyncClient, username: str = "renamer") -> int:
    """Sign up a non-guest account and return its owner_id."""
    resp = await client.post(
        "/auth/signup",
        data={"username": username, "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200
    resp_json = resp.json()
    return int(resp_json["user_id"])


def _practice_activity_id_for(owner_id: int) -> int:
    """Return the test-fixture "Kendo" activity id for *owner_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        return conn.execute(
            """SELECT st.id FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.owner_id = ? AND c.name = 'Kendo' AND st.name = 'Kendo'""",
            (owner_id,),
        ).fetchone()["id"]


async def test_rename_form_returns_fragment_with_current_name_prefilled(
    client: AsyncClient,
) -> None:
    owner_id = await _create_named_account(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/rename-form",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    # Fragment, not a full page.
    assert "<!DOCTYPE html>" not in text
    # The form posts to the rename endpoint.
    assert f'hx-post="/activities/{activity_id}/rename"' in text
    # Current name pre-fills the input.
    assert 'value="Kendo"' in text
    # The slug-change notice is present.
    assert strings_module.RENAME_SLUG_NOTICE in text
    # Save and Cancel buttons.
    assert strings_module.RENAME_SAVE in text
    assert strings_module.RENAME_CANCEL in text


async def test_rename_form_requires_auth(client: AsyncClient) -> None:
    # No session — should 401 (fragment endpoint convention).
    resp = await client.get("/activities/1/rename-form")
    assert resp.status_code == 401


async def test_rename_form_unknown_activity_returns_404(client: AsyncClient) -> None:
    await _create_named_account(client)

    resp = await client.get("/activities/999999/rename-form")
    assert resp.status_code == 404


async def test_rename_success_redirects_to_new_slug_url(client: AsyncClient) -> None:
    owner_id = await _create_named_account(client, "renamer1")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/rename",
        data={"name": "Morning Kendo"},
    )
    assert resp.status_code == 200
    hx_redirect = resp.headers["hx-redirect"]
    assert hx_redirect.startswith("/@renamer1/")
    assert "morning-kendo" in hx_redirect


async def test_rename_updates_name_and_slug_in_db(client: AsyncClient) -> None:
    owner_id = await _create_named_account(client, "renamer2")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/rename",
        data={"name": "Evening Practice"},
    )
    assert resp.status_code == 200
    assert "hx-redirect" in resp.headers

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT name, slug FROM activity WHERE id = ?", (activity_id,)
        ).fetchone()
    assert row["name"] == "Evening Practice"
    assert row["slug"] == "evening-practice"


async def test_rename_empty_name_returns_form_fragment_with_error(
    client: AsyncClient,
) -> None:
    owner_id = await _create_named_account(client, "renamer3")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.post(
        f"/activities/{activity_id}/rename",
        data={"name": "   "},
        headers={"HX-Request": "true"},
    )
    # Not a redirect, not a bare 400 — a fragment with an error message.
    assert resp.status_code == 422
    text = resp.text
    assert "<!DOCTYPE html>" not in text
    assert f'hx-post="/activities/{activity_id}/rename"' in text
    # Some error text is present.
    assert "empty" in text.lower() or "required" in text.lower() or "must" in text.lower()


async def test_rename_non_owner_returns_404(client: AsyncClient) -> None:
    """A rename attempt against another user's sub-tally returns 404."""
    # Create two accounts.
    owner_id = await _create_named_account(client, "owner4b")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    # Log in as a different user.
    resp = await client.post(
        "/auth/signup",
        data={"username": "attacker4b", "password": "correct-horse", "consent": "true"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/activities/{activity_id}/rename",
        data={"name": "Hijacked"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_rename_cancel_returns_plain_heading_fragment(client: AsyncClient) -> None:
    owner_id = await _create_named_account(client, "renamer5")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/rename-form-cancel",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    # Plain heading fragment — no form.
    assert "<!DOCTYPE html>" not in text
    assert "<form" not in text
    assert "Kendo" in text
    assert 'id="rename-heading"' in text
    # The pencil button to re-open the form is present.
    assert f'hx-get="/activities/{activity_id}/rename-form"' in text


async def test_rename_old_slug_returns_404_after_rename(client: AsyncClient) -> None:
    """After a rename the old slug URL must 404 (it no longer exists in the DB).

    Hits the canonical ``/@{username}/{slug}`` route directly — the legacy
    ``/u/...`` redirect routes have been removed entirely (they 404 now too,
    but for an unrelated reason: there's no route to match).
    """
    owner_id = await _create_named_account(client, "renamer6")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    # Capture the old slug before rename.
    with db.connect() as conn:
        conn.execute("BEGIN")
        old_slug = conn.execute(
            "SELECT slug FROM activity WHERE id = ?", (activity_id,)
        ).fetchone()["slug"]

    await client.post(
        f"/activities/{activity_id}/rename",
        data={"name": "New Name For Practice"},
        follow_redirects=False,
    )

    resp = await client.get(f"/@renamer6/{old_slug}")
    assert resp.status_code == 404


async def test_detail_page_shows_rename_affordance(client: AsyncClient) -> None:
    """The sub-tally detail page renders the rename heading with a pencil button."""
    owner_id = await _create_named_account(client, "renamer7")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    # GET /activities/{id} redirects 301 to /@{username}/{slug} for named users;
    # follow it so we land on the rendered detail page.
    resp = await client.get(f"/activities/{activity_id}", follow_redirects=True)
    assert resp.status_code == 200
    text = resp.text

    assert 'id="rename-heading"' in text
    assert f'hx-get="/activities/{activity_id}/rename-form"' in text


# ---------------------------------------------------------------------------
# Entry delete (two-step inline flow)
# ---------------------------------------------------------------------------


def _create_entry_for(owner_id: int, activity_id: int) -> int:
    """Create a bare entry and return its id."""
    from app.services import entries as entries_service

    entry = entries_service.create(owner_id, activity_id, {}, tz=_UTC)
    return entry["id"]


@pytest.mark.anyio
async def test_delete_confirm_returns_fragment(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    resp = await client.get(
        f"/activities/{activity_id}/entries/{entry_id}/delete-confirm",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text
    assert "<!DOCTYPE html>" not in text
    from app import ui_strings as s

    assert s.ENTRY_DELETE_CONFIRM_BODY in text
    assert f'hx-post="/activities/{activity_id}/entries/{entry_id}/delete"' in text
    assert f'hx-get="/activities/{activity_id}/entries/{entry_id}/edit"' in text


@pytest.mark.anyio
async def test_delete_confirm_non_owner_returns_404(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    # Switch to a different user.
    client.cookies.clear()
    await _guest_login(client)

    resp = await client.get(f"/activities/{activity_id}/entries/{entry_id}/delete-confirm")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_removes_entry_and_returns_empty_200(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    resp = await client.post(
        f"/activities/{activity_id}/entries/{entry_id}/delete",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.text == ""

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        ).fetchone()
    assert row is None


@pytest.mark.anyio
async def test_delete_non_owner_returns_404(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    # Switch to a different user.
    client.cookies.clear()
    await _guest_login(client)

    resp = await client.post(f"/activities/{activity_id}/entries/{entry_id}/delete")
    assert resp.status_code == 404

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id FROM entry WHERE id = ? AND owner_id = ?",
            (entry_id, owner_id),
        ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Category delete (two-step inline flow)
# ---------------------------------------------------------------------------


async def test_category_delete_confirm_returns_fragment(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/delete-confirm",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    # Fragment, not a full page.
    assert "<!DOCTYPE html>" not in text
    # Confirm body text is present.
    assert strings_module.ACTIVITY_DELETE_CONFIRM_BODY in text
    # Confirm button posts to the delete endpoint.
    assert f'hx-post="/activities/{activity_id}/delete"' in text
    # Cancel button restores the heading via the existing cancel-rename route.
    assert f'hx-get="/activities/{activity_id}/rename-form-cancel"' in text
    # The outer swap target is present.
    assert 'id="rename-heading"' in text


async def test_category_delete_confirm_uses_danger_token_not_stock_red(
    client: AsyncClient,
) -> None:
    """The destructive confirm button must use the `--color-danger` design
    token (`bg-danger`/`text-danger`), not Tailwind's stock `red-*` palette.

    `bg-red-600` (#dc2626, hue ~0deg) sits within ~5deg of hue of
    `--color-accent` cinnabar (#E34234, hue ~4.8deg) -- the exact
    danger-vs-accent red ambiguity the 2026-06-19 brand realignment
    deliberately re-hued `--color-danger` (hue ~18.7deg) to avoid. This
    confirm fragment renders inline on the activity-detail page, directly
    above the cinnabar-accented progress bar / focus rings, so a stock red
    button here reads as the same "warning red" as the brand accent.
    """
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/delete-confirm",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    assert "bg-red-" not in text, (
        "category_delete_confirm fragment uses a stock Tailwind red-* "
        "utility instead of the --color-danger token (bg-danger/text-danger)"
    )
    assert "text-red-" not in text


async def test_entry_delete_confirm_uses_danger_token_not_stock_red(
    client: AsyncClient,
) -> None:
    """Same invariant as the category delete-confirm: the per-entry delete
    confirm button must use `--color-danger`, not stock Tailwind red."""
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    resp = await client.get(
        f"/activities/{activity_id}/entries/{entry_id}/delete-confirm",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    assert "bg-red-" not in text, (
        "entry_delete_confirm fragment uses a stock Tailwind red-* utility "
        "instead of the --color-danger token (bg-danger/text-danger)"
    )
    assert "text-red-" not in text


async def test_category_delete_confirm_non_owner_returns_404(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    # Switch to a different user.
    client.cookies.clear()
    await _guest_login(client)

    resp = await client.get(f"/activities/{activity_id}/delete-confirm")
    assert resp.status_code == 404


async def test_category_delete_confirm_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/activities/1/delete-confirm")
    assert resp.status_code == 401


async def test_category_delete_succeeds_and_returns_hx_redirect(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    # Look up the category_id so we can verify it is gone after the delete.
    with db.connect() as conn:
        conn.execute("BEGIN")
        category_id = conn.execute(
            "SELECT category_id FROM activity WHERE id = ?", (activity_id,)
        ).fetchone()["category_id"]

    resp = await client.post(
        f"/activities/{activity_id}/delete",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/home"

    # The category and its sub-tallies/entries must be gone.
    with db.connect() as conn:
        conn.execute("BEGIN")
        cat_row = conn.execute(
            "SELECT id FROM category WHERE id = ? AND owner_id = ?",
            (category_id, owner_id),
        ).fetchone()
        st_row = conn.execute(
            "SELECT id FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
    assert cat_row is None
    assert st_row is None


async def test_category_delete_non_owner_returns_404(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)

    # Switch to a different user.
    client.cookies.clear()
    await _guest_login(client)

    resp = await client.post(f"/activities/{activity_id}/delete")
    assert resp.status_code == 404

    # The original owner's category must still exist.
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
    assert row is not None


async def test_rename_form_shows_delete_activity_button(client: AsyncClient) -> None:
    owner_id = await _create_named_account(client, "deleter1")
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id_for(owner_id)

    resp = await client.get(
        f"/activities/{activity_id}/rename-form",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text

    assert strings_module.ACTIVITY_DELETE in text
    assert f'hx-get="/activities/{activity_id}/delete-confirm"' in text


@pytest.mark.anyio
async def test_delete_edit_form_has_delete_button(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    seed_test_activity(owner_id, name="Kendo", extra_field_kinds=("match_list",))
    activity_id = _practice_activity_id(owner_id)
    entry_id = _create_entry_for(owner_id, activity_id)

    resp = await client.get(
        f"/activities/{activity_id}/entries/{entry_id}/edit",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    text = resp.text
    from app import ui_strings as s

    assert s.ENTRY_DELETE in text
    assert f'hx-get="/activities/{activity_id}/entries/{entry_id}/delete-confirm"' in text


# ---------------------------------------------------------------------------
# GET /comments — dedicated notification history (separate watermark from
# GET /home). See meetings/MEETING-2026-06-20-comment-notifications.
# ---------------------------------------------------------------------------


def _make_activity_with_entry_for(owner_id: int, *, name: str = "Running") -> tuple[str, int, int]:
    """Create a fresh activity + one entry for *owner_id*.

    Returns (slug, activity_id, entry_id).
    """
    result = categories.create_activity(owner_id, name=name)
    activity_id = result["activity_id"]
    entry = entries.create(owner_id, activity_id, tz=_UTC)
    with db.connect() as conn:
        conn.execute("BEGIN")
        slug = conn.execute("SELECT slug FROM activity WHERE id = ?", (activity_id,)).fetchone()[
            "slug"
        ]
    return slug, activity_id, entry["id"]


def _post_comment(entry_id: int, *, author_id: int, body: str = "nice work") -> int:
    with db.connect() as conn:
        conn.execute("BEGIN")
        comment_id = comments_service.create_comment(conn, entry_id, author_id=author_id, body=body)
    return comment_id


async def test_comments_page_redirects_when_logged_out(client: AsyncClient) -> None:
    resp = await client.get("/comments")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_home_visits_do_not_change_comments_seen_at_or_clear_badge(
    client: AsyncClient, client2: AsyncClient
) -> None:
    owner_id = await _guest_login(client)
    commenter_id = await _guest_login(client2)
    _, _, entry_id = _make_activity_with_entry_for(owner_id)
    _post_comment(entry_id, author_id=commenter_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        before = conn.execute(
            "SELECT comments_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()["comments_seen_at"]
    assert before is None

    for _ in range(3):
        resp = await client.get("/home")
        assert resp.status_code == 200
        assert f'aria-label="{strings_module.COMMENTS_UNSEEN_ARIA}"' in resp.text

    with db.connect() as conn:
        conn.execute("BEGIN")
        after = conn.execute(
            "SELECT comments_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()["comments_seen_at"]
    assert after is None


async def test_comments_page_advances_watermark_and_renders_pre_visit_new_state(
    client: AsyncClient, client2: AsyncClient
) -> None:
    owner_id = await _guest_login(client)
    commenter_id = await _guest_login(client2)
    _, _, entry_id = _make_activity_with_entry_for(owner_id)

    # A comment posted before any /comments visit (watermark is NULL) should
    # render as "new" on the first visit -- it predates this visit but there
    # was no prior watermark to have already cleared it.
    _post_comment(entry_id, author_id=commenter_id, body="first comment")

    resp = await client.get("/comments")
    assert resp.status_code == 200
    assert "first comment" in resp.text

    with db.connect() as conn:
        conn.execute("BEGIN")
        watermark_after_first_visit = conn.execute(
            "SELECT comments_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()["comments_seen_at"]
    assert watermark_after_first_visit is not None

    # Home now reflects 0 unseen.
    home_resp = await client.get("/home")
    assert home_resp.status_code == 200
    assert f'aria-label="{strings_module.COMMENTS_UNSEEN_ARIA}"' not in home_resp.text


async def test_comments_page_row_links_to_owner_activity_detail_with_c_param(
    client: AsyncClient, client2: AsyncClient
) -> None:
    owner_id = await _create_named_account(client, "linktest_owner1")
    users_module.set_visibility_consent(owner_id, "public")
    commenter_id = await _guest_login(client2)
    slug, _, entry_id = _make_activity_with_entry_for(owner_id)
    _post_comment(entry_id, author_id=commenter_id)

    username = "linktest_owner1"

    resp = await client.get("/comments")
    assert resp.status_code == 200
    expected_href = f'href="/@{username}/{slug}?c={entry_id}#comment-slot-{entry_id}"'
    assert expected_href in resp.text

    # Follow the link the row points to: lands on the owner's own
    # activity-detail page, on the merged calendar, with that entry's day
    # pre-selected and its comment thread pre-expanded via an extra
    # hx-trigger="load" on the day-entries comment toggle.
    detail_resp = await client.get(f"/@{username}/{slug}?c={entry_id}")
    assert detail_resp.status_code == 200
    assert f'id="comment-slot-{entry_id}"' in detail_resp.text
    assert f'hx-get="/@{username}/{slug}/entries/{entry_id}/comments"' in detail_resp.text
    assert 'hx-trigger="click, load"' in detail_resp.text


async def test_comments_page_excludes_soft_deleted_and_self_comments(
    client: AsyncClient, client2: AsyncClient
) -> None:
    owner_id = await _guest_login(client)
    commenter_id = await _guest_login(client2)
    _, _, entry_id = _make_activity_with_entry_for(owner_id)

    # Owner's own comment on their own entry -- never a notification.
    _post_comment(entry_id, author_id=owner_id, body="my own note to self")

    # A comment that gets soft-deleted before the owner ever visits /comments.
    deleted_id = _post_comment(entry_id, author_id=commenter_id, body="will be deleted")
    with db.connect() as conn:
        conn.execute("BEGIN")
        comments_service.soft_delete_comment(conn, deleted_id, requester_id=commenter_id)

    _post_comment(entry_id, author_id=commenter_id, body="this one stays")

    resp = await client.get("/comments")
    assert resp.status_code == 200
    assert "my own note to self" not in resp.text
    assert "will be deleted" not in resp.text
    assert "this one stays" in resp.text


async def test_comments_page_empty_state_when_no_comments(client: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    _make_activity_with_entry_for(owner_id)

    resp = await client.get("/comments")
    assert resp.status_code == 200
    assert strings_module.COMMENTS_PAGE_EMPTY in resp.text


async def test_home_badge_links_to_comments_page(client: AsyncClient, client2: AsyncClient) -> None:
    owner_id = await _guest_login(client)
    commenter_id = await _guest_login(client2)
    _, _, entry_id = _make_activity_with_entry_for(owner_id)
    _post_comment(entry_id, author_id=commenter_id)

    resp = await client.get("/home")
    assert resp.status_code == 200
    assert 'href="/comments"' in resp.text
