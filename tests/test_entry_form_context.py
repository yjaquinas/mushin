import sqlite3

from app.routes.web._entry_form_context import _build_log_sheet_fields


def test_log_sheet_fields_omit_value_input() -> None:
    fields = _build_log_sheet_fields(sqlite3.connect(":memory:"), activity_id=1)

    assert fields == [{"id": "memo", "kind": "memo", "label": "Memo"}]
