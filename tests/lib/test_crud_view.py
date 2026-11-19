"""Tests for the CrudTableView base class."""

from __future__ import annotations

import pytest

from vweb.lib.crud.view import Column, CrudTableView


class _MissingParentHandler:
    """Stand in for a handler whose parent resource does not exist."""

    def __init__(self, parent_id: str) -> None:
        msg = f"parent {parent_id} not found"
        raise ValueError(msg)


class _View(CrudTableView):
    handler_class = _MissingParentHandler
    table_name = "Test"
    item_name = "Item"
    table_id = "crud-test"
    form_component = "test.Form"
    columns = (
        Column("title", "Title"),
        Column("content", "Content", markdown=True, sortable=False),
        Column("type", "Type"),
    )


def test_columns_derive_table_metadata() -> None:
    """Verify fields, headers, markdown, and sortable sets follow the column declarations."""
    assert _View.fields == ("title", "content", "type")
    assert _View.headers == ("Title", "Content", "Type")
    assert _View.markdown_fields == frozenset({"content"})
    assert _View.sortable_fields == frozenset({"title", "type"})


@pytest.mark.parametrize(
    ("rule", "path", "status"),
    [
        ("/test-crud/<string:parent_id>/items", "/test-crud/gone/items", 404),
        ("/test-crud-no-parent/items", "/test-crud-no-parent/items", 400),
    ],
)
def test_unresolvable_parent_is_rejected(app, client, rule: str, path: str, status: int) -> None:
    """Verify a table whose parent cannot be resolved answers 404, or 400 with no parent id."""
    app.add_url_rule(rule, defaults={"item_id": None}, view_func=_View.as_view("test_crud"))

    response = client.get(path, headers={"HX-Request": "true"})

    assert response.status_code == status
