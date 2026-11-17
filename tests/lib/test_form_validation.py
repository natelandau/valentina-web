"""Tests for shared form checks."""

from __future__ import annotations

import pytest

from vweb.lib.form_validation import name_errors, position_number


@pytest.mark.parametrize(
    ("name", "min_length", "expected"),
    [
        ("B", 1, []),
        ("x" * 50, 1, []),
        ("", 1, ["Name is required"]),
        ("x" * 51, 1, ["Name must be 50 characters or fewer"]),
        ("ab", 3, ["Name must be at least 3 characters"]),
        ("abc", 3, []),
    ],
)
def test_name_errors(name, min_length, expected) -> None:
    """Verify names are checked against the API's length limits."""
    assert name_errors(name, min_length=min_length) == expected


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        ("", (4, None)),
        ("2", (2, None)),
        ("x", (4, "Number must be a valid integer")),
        ("0", (4, "Number must be 1 or greater")),
        ("-3", (4, "Number must be 1 or greater")),
    ],
)
def test_position_number(submitted, expected) -> None:
    """Verify submitted numbers are parsed and checked against the API's minimum."""
    assert position_number(submitted, 4) == expected
