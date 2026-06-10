"""Tests for the CrudTableView base class and Column dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vweb.lib.crud.view import Column, CrudTableView


class TestColumn:
    """Tests for the Column dataclass."""

    def test_column_defaults(self) -> None:
        """Verify Column has correct defaults for markdown and sortable."""
        col = Column("name", "Name")
        assert col.field == "name"
        assert col.header == "Name"
        assert col.markdown is False
        assert col.sortable is True

    def test_column_markdown_and_not_sortable(self) -> None:
        """Verify Column accepts explicit markdown and sortable values."""
        col = Column("content", "Content", markdown=True, sortable=False)
        assert col.markdown is True
        assert col.sortable is False

    def test_column_is_frozen(self) -> None:
        """Verify Column instances are immutable."""
        col = Column("name", "Name")
        with pytest.raises(AttributeError):
            col.field = "other"  # type: ignore[misc]


class TestCrudTableViewProperties:
    """Tests for CrudTableView derived properties from columns."""

    def _make_view_class(self, columns: tuple[Column, ...]) -> type[CrudTableView]:
        """Create a concrete CrudTableView subclass with given columns."""
        return type(
            "TestView",
            (CrudTableView,),
            {
                "handler_class": MagicMock,
                "table_name": "Test",
                "item_name": "Item",
                "table_id": "crud-test",
                "columns": columns,
                "form_component": "test.Form",
            },
        )

    def test_fields_derived_from_columns(self) -> None:
        """Verify fields property returns field names in column order."""
        view_class = self._make_view_class(
            (
                Column("name", "Name"),
                Column("type", "Type"),
            )
        )
        view = view_class()
        assert view.fields == ("name", "type")

    def test_headers_derived_from_columns(self) -> None:
        """Verify headers property returns header strings in column order."""
        view_class = self._make_view_class(
            (
                Column("name", "Name"),
                Column("type", "Type"),
            )
        )
        view = view_class()
        assert view.headers == ("Name", "Type")

    def test_markdown_fields_derived_from_columns(self) -> None:
        """Verify markdown_fields returns only fields with markdown=True."""
        view_class = self._make_view_class(
            (
                Column("title", "Title"),
                Column("content", "Content", markdown=True),
                Column("summary", "Summary"),
            )
        )
        view = view_class()
        assert view.markdown_fields == frozenset({"content"})

    def test_sortable_fields_derived_from_columns(self) -> None:
        """Verify sortable_fields returns only fields with sortable=True."""
        view_class = self._make_view_class(
            (
                Column("title", "Title"),
                Column("content", "Content", sortable=False),
                Column("type", "Type"),
            )
        )
        view = view_class()
        assert view.sortable_fields == frozenset({"title", "type"})
