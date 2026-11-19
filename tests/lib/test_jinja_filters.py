"""Tests for the formatting Jinja filters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from vweb.lib.jinja_filters import (
    format_date,
    from_markdown,
    from_markdown_no_p,
    humanize_date,
    normalize_string,
    to_roman,
)


@pytest.mark.parametrize("render", [from_markdown, from_markdown_no_p])
def test_markdown_escapes_raw_html(render) -> None:
    """Verify raw HTML in user text is escaped while markdown still renders."""
    result = render("**bold** <script>alert(1)</script>")

    assert "<strong>bold</strong>" in result
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_from_markdown_no_p_strips_paragraph_wrapper() -> None:
    """Verify the single wrapping paragraph is removed for inline layouts."""
    assert from_markdown_no_p("*hi*") == "<em>hi</em>"


@pytest.mark.parametrize(
    "value",
    ["2026-03-15T10:30:00+00:00", datetime(2026, 3, 15, 10, 30, tzinfo=UTC)],
)
def test_format_date(value) -> None:
    """Verify ISO strings and datetimes both format as YYYY-MM-DD."""
    assert format_date(value) == "2026-03-15"


def test_humanize_date_accepts_iso_string() -> None:
    """Verify an ISO string from the API is parsed before humanizing."""
    value = (datetime.now(tz=UTC) - timedelta(days=3)).isoformat()

    assert humanize_date(value) == humanize_date(datetime.fromisoformat(value))


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-1, ""), (0, ""), (1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (1994, "MCMXCIV")],
)
def test_to_roman(value, expected) -> None:
    """Verify integers convert to Roman numerals and non-positive values render nothing."""
    assert to_roman(value) == expected


def test_normalize_string() -> None:
    """Verify quotes and surrounding whitespace are removed."""
    assert normalize_string(""" "Ada's" """) == "Adas"
