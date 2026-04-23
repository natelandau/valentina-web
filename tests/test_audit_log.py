"""Tests for the shared audit log helpers in vweb.lib.audit_log."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vweb.lib.audit_log import (
    FieldDiff,
    OtherEntry,
    format_change_value,
    split_changes,
)


class TestFormatChangeValue:
    """Tests for format_change_value."""

    def test_none_renders_muted_em_dash(self) -> None:
        """Verify None renders as a muted em-dash span."""
        # When formatting None
        result = format_change_value(None)

        # Then the result is a muted em-dash
        assert "—" in str(result)
        assert "opacity-40" in str(result)

    def test_true_renders_yes(self) -> None:
        """Verify True renders as 'Yes'."""
        # When formatting True
        result = format_change_value(value=True)

        # Then the result is 'Yes'
        assert str(result) == "Yes"

    def test_false_renders_no(self) -> None:
        """Verify False renders as 'No'."""
        # When formatting False
        result = format_change_value(value=False)

        # Then the result is 'No'
        assert str(result) == "No"

    def test_string_escapes_html(self) -> None:
        """Verify strings containing HTML are escaped."""
        # When formatting a string containing HTML
        result = format_change_value("<script>alert(1)</script>")

        # Then the HTML is escaped
        assert "<script>" not in str(result)
        assert "&lt;script&gt;" in str(result)

    def test_int_renders_as_string(self) -> None:
        """Verify ints stringify directly."""
        # When formatting an int
        result = format_change_value(42)

        # Then the result is "42"
        assert str(result) == "42"

    def test_list_renders_as_pre_json(self) -> None:
        """Verify lists render as pretty-printed JSON inside a <pre> block."""
        # When formatting a list
        result = format_change_value(["a", "b", "c"])

        # Then the output is a <pre> with JSON
        html = str(result)
        assert html.startswith("<pre")
        assert '"a"' in html
        assert '"b"' in html
        assert '"c"' in html

    def test_dict_renders_as_pre_json(self) -> None:
        """Verify dicts render as pretty-printed JSON inside a <pre> block."""
        # When formatting a dict
        result = format_change_value({"name": "Alice", "age": 30})

        # Then the output is a <pre> with JSON
        html = str(result)
        assert html.startswith("<pre")
        assert '"name"' in html
        assert '"Alice"' in html

    def test_datetime_falls_back_via_default_str(self) -> None:
        """Verify a datetime nested in a list renders via default=str (JSON-safe)."""
        # Given a list containing a datetime
        value = [datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)]

        # When formatting the list
        result = format_change_value(value)

        # Then the datetime is stringified, not an error
        html = str(result)
        assert "2026-04-23" in html


class TestSplitChanges:
    """Tests for split_changes."""

    def test_none_returns_empty_lists(self) -> None:
        """Verify None input returns two empty lists."""
        # When splitting None
        diffs, others = split_changes(None)

        # Then both lists are empty
        assert diffs == []
        assert others == []

    def test_empty_dict_returns_empty_lists(self) -> None:
        """Verify an empty dict returns two empty lists."""
        # When splitting an empty dict
        diffs, others = split_changes({})

        # Then both lists are empty
        assert diffs == []
        assert others == []

    def test_canonical_entry_goes_to_diffs(self) -> None:
        """Verify a canonical {old, new} entry becomes a FieldDiff."""
        # Given a canonical changes dict
        changes = {"name": {"old": "Alice", "new": "Bob"}}

        # When splitting
        diffs, others = split_changes(changes)

        # Then the entry lands in diffs
        assert len(diffs) == 1
        assert isinstance(diffs[0], FieldDiff)
        assert diffs[0].field == "name"
        assert "Alice" in str(diffs[0].old)
        assert "Bob" in str(diffs[0].new)
        assert others == []

    def test_canonical_entry_tolerates_extra_keys(self) -> None:
        """Verify entries with extra keys beyond old/new still count as canonical."""
        # Given an entry with old/new plus an extra metadata key
        changes = {"role": {"old": "PLAYER", "new": "ADMIN", "by": "user-1"}}

        # When splitting
        diffs, others = split_changes(changes)

        # Then it's still treated as canonical (old and new both present)
        assert len(diffs) == 1
        assert diffs[0].field == "role"
        assert others == []

    def test_off_shape_scalar_goes_to_others(self) -> None:
        """Verify a flat scalar value lands in others, not diffs."""
        # Given a non-canonical entry
        changes = {"deleted_by": "user-1"}

        # When splitting
        diffs, others = split_changes(changes)

        # Then it lands in others
        assert diffs == []
        assert len(others) == 1
        assert isinstance(others[0], OtherEntry)
        assert others[0].key == "deleted_by"
        assert "user-1" in str(others[0].value)

    def test_off_shape_dict_goes_to_others(self) -> None:
        """Verify a nested dict without old/new lands in others."""
        # Given a nested dict that doesn't match {old, new}
        changes = {"meta": {"version": 3, "hash": "abc"}}

        # When splitting
        diffs, others = split_changes(changes)

        # Then it lands in others
        assert diffs == []
        assert len(others) == 1
        assert others[0].key == "meta"

    def test_mixed_input(self) -> None:
        """Verify mixed input sorts into diffs and others correctly."""
        # Given a mix of canonical and off-shape entries
        changes = {
            "name": {"old": "A", "new": "B"},
            "meta": {"version": 3},
            "deleted_by": "user-1",
        }

        # When splitting
        diffs, others = split_changes(changes)

        # Then canonical lands in diffs, others in others
        assert len(diffs) == 1
        assert diffs[0].field == "name"
        assert len(others) == 2
        assert {e.key for e in others} == {"meta", "deleted_by"}


@pytest.mark.parametrize(
    ("value", "expected_substring"),
    [
        (None, "—"),
        (True, "Yes"),
        (False, "No"),
        ("plain", "plain"),
        (0, "0"),
        (3.14, "3.14"),
    ],
)
def test_format_change_value_scalars(value, expected_substring) -> None:
    """Verify scalar values render with the expected substring in output."""
    # When formatting the scalar
    result = format_change_value(value)

    # Then the substring is present
    assert expected_substring in str(result)
