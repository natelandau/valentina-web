"""Tests for shared form checks."""

from __future__ import annotations

from datetime import date

import pytest

from vweb.lib.form_validation import name_errors, parse_form_date, position_number


@pytest.mark.parametrize(
    ("name", "min_length", "valid"),
    [
        ("B", 1, True),
        ("x" * 50, 1, True),
        ("", 1, False),
        ("x" * 51, 1, False),
        ("ab", 3, False),
        ("abc", 3, True),
    ],
)
def test_name_errors(name: str, min_length: int, valid: bool) -> None:  # noqa: FBT001
    """Verify names are checked against the API's length limits, one message per bad name."""
    assert len(name_errors(name, min_length=min_length)) == (0 if valid else 1)


@pytest.mark.parametrize(
    ("submitted", "number", "valid"),
    [
        ("", 4, True),
        ("2", 2, True),
        ("x", 4, False),
        ("0", 4, False),
        ("-3", 4, False),
    ],
)
def test_position_number(submitted: str, number: int, valid: bool) -> None:  # noqa: FBT001
    """Verify a blank or invalid number keeps the current one, and only invalid ones error."""
    result, error = position_number(submitted, 4)

    assert result == number
    assert (error is None) is valid


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1990-06-01", date(1990, 6, 1)), ("", None), ("1990-02-30", None), ("June", None)],
)
def test_parse_form_date(value: str, expected: date | None) -> None:
    """Verify only real calendar dates parse; anything else reads as no date."""
    assert parse_form_date(value) == expected
