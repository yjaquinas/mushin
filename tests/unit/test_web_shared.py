"""Unit tests for app.routes.web._shared pure helpers (UI polish round 2).

Acceptance criteria
--------------------
``_format_count`` renders a monotonic entry count with "1k"/"1m"-style
compact notation: plain integer below 1000; floored one-decimal "k"/"m"
notation above that, never rounding up past the true value, with the
trailing ".0" stripped and no "+" suffix anywhere.

``_format_streak_days`` renders a streak length with correct singular/plural
day unit: ``"1 day"`` for ``n == 1``, ``"N days"`` otherwise (including
``n == 0``).
"""

from __future__ import annotations

import pytest

from app.routes.web._shared import _format_count, _format_streak_days


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0"),
        (1, "1"),
        (999, "999"),
        (1000, "1k"),
        (1100, "1.1k"),
        (1999, "1.9k"),
        (12340, "12.3k"),
        (999999, "999.9k"),
        (1000000, "1m"),
        (1500000, "1.5m"),
    ],
)
def test_format_count_boundaries(n, expected):
    assert _format_count(n) == expected


def test_format_count_never_rounds_up_past_floor():
    """1999 / 1000 == 1.999 — must floor to "1.9k", never round to "2k"."""
    assert _format_count(1999) == "1.9k"


def test_format_count_999999_does_not_round_to_1m():
    """999999 / 1000 == 999.999 — must floor to "999.9k", never round to "1m"."""
    assert _format_count(999999) == "999.9k"


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0 days"),
        (1, "1 day"),
        (2, "2 days"),
    ],
)
def test_format_streak_days_pluralization(n, expected):
    assert _format_streak_days(n) == expected
