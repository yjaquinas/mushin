from types import SimpleNamespace

from fastapi import Request

from app.routes.web import _account_handlers


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def test_render_account_settings_includes_current_email(monkeypatch) -> None:
    captured = {}

    class FakeResponse(SimpleNamespace):
        def delete_cookie(self, **kwargs):
            captured["deleted_cookie"] = kwargs

    def fake_template_response(*, request, name, context):
        captured["request"] = request
        captured["name"] = name
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr(_account_handlers.templates, "TemplateResponse", fake_template_response)

    user = {"username": "alice", "visibility": "public", "email": "alice@example.com"}

    _account_handlers.render_account_settings(_request(), user)

    assert captured["name"] == "web/account.html.jinja2"
    assert captured["context"]["email"] == "alice@example.com"


def test_render_account_settings_preserves_submitted_email_on_error(monkeypatch) -> None:
    captured = {}

    class FakeResponse(SimpleNamespace):
        def delete_cookie(self, **kwargs):
            captured["deleted_cookie"] = kwargs

    def fake_template_response(*, request, name, context):
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr(_account_handlers.templates, "TemplateResponse", fake_template_response)

    user = {"username": "alice", "visibility": "public", "email": "alice@example.com"}

    _account_handlers.render_account_settings(
        _request(),
        user,
        email_error="invalid",
        email_value="bad@",
    )

    assert captured["context"]["email"] == "bad@"
    assert captured["context"]["email_error"] == "invalid"
