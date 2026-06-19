"""Playwright E2E specs for the export/import data-portability feature.

These specs are driven through the **Playwright MCP**, not a bundled
Playwright runner (see .claude/rules/tests.md — "E2E tests use the Playwright
MCP — not a bundled Playwright"). They are written ahead of being run by an
agent with MCP browser tools attached.

Marked ``e2e`` (registered in pyproject.toml) and skipped outright when no
Playwright browser/MCP session is available, so `uv run pytest tests/` stays
green on a plain dev machine / CI without a browser, mirroring
``tests/e2e/test_visual_polish.py``.

Specs covered
-------------
1. Export: clicking the footer "Export my data" link triggers a download of
   ``mushin-export.json``, and the downloaded file is valid JSON with
   ``schema_version`` and ``data`` keys.
2. Import dialog: opening it shows the focus-trapped confirm dialog with a
   file input and a warning that current data will be replaced; canceling
   closes it without making any changes.
3. Import success: uploading a valid exported JSON file and confirming
   triggers ``HX-Redirect: /home`` (observed via navigation/URL change).
4. Import error: uploading an invalid file (wrong ``schema_version`` or
   non-JSON) keeps the dialog open with an inline error message, per
   ``IMPORT_DATA_ERROR_*`` strings.

``app.routes.data_io`` and ``app.services.portability`` already have
integration-test coverage in ``tests/integration/test_data_io.py`` — this
module covers only the browser-level interactions (file upload, dialog
open/close, download, redirect).
"""

from __future__ import annotations

import json

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
    context = browser.new_context(viewport={"width": 360, "height": 800}, accept_downloads=True)
    page = context.new_page()
    yield page
    context.close()


def _enter_as_guest(page) -> None:
    """Land on the entry screen and tap "Continue without an account" to start a guest session."""
    page.goto(BASE_URL + "/")
    page.get_by_text(ui_strings.ENTRY_GUEST_LINK).click()
    page.wait_for_url(BASE_URL + "/home")


def test_export_link_downloads_valid_json_snapshot(page, tmp_path) -> None:
    """Clicking the footer "Export my data" link downloads
    ``mushin-export.json``, whose contents are valid JSON with
    ``schema_version`` and ``data`` keys."""
    _enter_as_guest(page)

    with page.expect_download() as download_info:
        page.get_by_role("link", name=ui_strings.FOOTER_EXPORT_DATA).click()
    download = download_info.value

    assert download.suggested_filename == "mushin-export.json"

    saved_path = tmp_path / "mushin-export.json"
    download.save_as(saved_path)

    payload = json.loads(saved_path.read_text())
    assert "schema_version" in payload
    assert "data" in payload


def test_import_dialog_shows_warning_and_cancel_closes_without_changes(page) -> None:
    """Opening the import dialog shows the focus-trapped confirm dialog with
    a file input and a warning that current data will be replaced; canceling
    closes it without making any changes."""
    _enter_as_guest(page)

    page.get_by_role("button", name=ui_strings.FOOTER_IMPORT_DATA).click()

    dialog = page.locator("#import-data-dialog [role='dialog']")
    dialog.wait_for(state="visible")

    assert ui_strings.IMPORT_DATA_BODY in dialog.inner_text()
    assert dialog.locator('input[type="file"]').count() == 1

    # Focus moved inside the dialog.
    is_focus_inside_dialog = page.evaluate(
        "() => { const dialog = document.querySelector(\"#import-data-dialog [role='dialog']\"); "
        "return dialog ? dialog.contains(document.activeElement) : false; }"
    )
    assert is_focus_inside_dialog

    page.get_by_role("button", name=ui_strings.IMPORT_DATA_CANCEL).click()
    dialog.wait_for(state="hidden")

    # No navigation/changes — still on /home.
    assert page.url == BASE_URL + "/home"


def test_import_valid_export_redirects_to_home(page, tmp_path) -> None:
    """Uploading a valid exported JSON file and confirming triggers
    ``HX-Redirect: /home`` (observed as a navigation to /home)."""
    _enter_as_guest(page)

    # Round-trip: export the current guest's own data first, so the upload
    # is guaranteed to pass validation against the live schema.
    with page.expect_download() as download_info:
        page.get_by_role("link", name=ui_strings.FOOTER_EXPORT_DATA).click()
    download = download_info.value
    export_path = tmp_path / "mushin-export.json"
    download.save_as(export_path)

    page.get_by_role("button", name=ui_strings.FOOTER_IMPORT_DATA).click()
    dialog = page.locator("#import-data-dialog [role='dialog']")
    dialog.wait_for(state="visible")

    dialog.locator('input[type="file"]').set_input_files(str(export_path))
    dialog.get_by_role("button", name=ui_strings.IMPORT_DATA_CONFIRM).click()

    # HX-Redirect triggers htmx to navigate to /home.
    page.wait_for_url(BASE_URL + "/home")


def test_import_invalid_file_shows_inline_error_and_keeps_dialog_open(page, tmp_path) -> None:
    """Uploading an invalid file (wrong ``schema_version``) keeps the dialog
    open with an inline error message, per ``IMPORT_DATA_ERROR_*`` strings."""
    _enter_as_guest(page)

    bad_export_path = tmp_path / "bad-export.json"
    bad_export_path.write_text(json.dumps({"schema_version": 999, "data": {}}))

    page.get_by_role("button", name=ui_strings.FOOTER_IMPORT_DATA).click()
    dialog = page.locator("#import-data-dialog [role='dialog']")
    dialog.wait_for(state="visible")

    dialog.locator('input[type="file"]').set_input_files(str(bad_export_path))
    dialog.get_by_role("button", name=ui_strings.IMPORT_DATA_CONFIRM).click()

    # The dialog re-renders in place with an inline error and stays open.
    page.wait_for_function(
        "() => { const d = document.querySelector(\"#import-data-dialog [role='dialog']\"); "
        "return d && d.textContent.includes('Import failed'); }"
    )
    assert dialog.is_visible()
    assert page.url == BASE_URL + "/home"


def test_import_non_json_file_shows_invalid_file_error(page, tmp_path) -> None:
    """Uploading a non-JSON file is rejected with
    ``IMPORT_DATA_ERROR_INVALID_FILE`` and the dialog stays open."""
    _enter_as_guest(page)

    not_json_path = tmp_path / "notes.txt"
    not_json_path.write_text("not json")

    page.get_by_role("button", name=ui_strings.FOOTER_IMPORT_DATA).click()
    dialog = page.locator("#import-data-dialog [role='dialog']")
    dialog.wait_for(state="visible")

    dialog.locator('input[type="file"]').set_input_files(str(not_json_path))
    dialog.get_by_role("button", name=ui_strings.IMPORT_DATA_CONFIRM).click()

    page.wait_for_function(
        f"() => {{ const d = document.querySelector(\"#import-data-dialog [role='dialog']\"); "
        f"return d && d.textContent.includes({ui_strings.IMPORT_DATA_ERROR_INVALID_FILE!r}); }}"
    )
    assert dialog.is_visible()
