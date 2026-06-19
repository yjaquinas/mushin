"""Unit tests for the pure normalization/validation helpers in
``app/auth/routes.py`` (Task 6 gap-fill).

``_normalize_username`` and ``_normalize_email`` are pure functions (no DB, no
HTTP) that the username/password signup and login routes rely on for
case-insensitive identity matching and optional-email shape checking. They
weren't covered by ``tests/unit/test_users.py`` (which covers the repository
layer) or the integration suite's happy-path cases, so this file fills the
edge cases directly.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.routes import _normalize_email, _normalize_username

# ---------------------------------------------------------------------------
# _normalize_username
# ---------------------------------------------------------------------------


def test_normalize_username_lowercases_and_strips() -> None:
    assert _normalize_username("  Foo  ") == "foo"


def test_normalize_username_collapses_case_variants_to_same_identity() -> None:
    assert _normalize_username("Foo") == _normalize_username("FOO") == _normalize_username("foo")


def test_normalize_username_allows_digits_and_underscores() -> None:
    assert _normalize_username("user_123") == "user_123"


@pytest.mark.parametrize(
    "bad",
    [
        "ab",  # too short
        "x" * 21,  # too long
        "foo-bar",  # hyphen not allowed
        "foo bar",  # space not allowed
        "foo@bar",  # special char not allowed
        "",  # empty
        "   ",  # blank after strip
    ],
)
def test_normalize_username_rejects_invalid_shapes(bad: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_username(bad)
    assert exc_info.value.status_code == 400
    assert "Username must be 3-20 characters" in exc_info.value.detail


def test_normalize_username_nfkc_collapses_visually_identical_unicode() -> None:
    # U+FF41 (fullwidth "a") NFKC-normalizes to U+0061 ("a"); combined with
    # casefold this should resolve to the plain-ASCII identity "abcfoo".
    fullwidth = "ａｂｃfoo"  # "abc" in fullwidth + "foo"
    assert _normalize_username(fullwidth) == "abcfoo"


# ---------------------------------------------------------------------------
# _normalize_email
# ---------------------------------------------------------------------------


def test_normalize_email_none_returns_none() -> None:
    assert _normalize_email(None) is None


def test_normalize_email_blank_returns_none() -> None:
    assert _normalize_email("   ") is None
    assert _normalize_email("") is None


def test_normalize_email_lowercases_and_strips() -> None:
    assert _normalize_email("  Alice@Example.COM  ") == "alice@example.com"


@pytest.mark.parametrize("bad", ["not-an-email", "missing-at.example.com", "@example.com", "a@b"])
def test_normalize_email_rejects_malformed_shapes(bad: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_email(bad)
    assert exc_info.value.status_code == 400
    assert "malformed" in exc_info.value.detail
