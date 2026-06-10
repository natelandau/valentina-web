"""Blueprint URL registration helper for CRUD table views."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Blueprint

    from vweb.lib.crud.view import CrudTableView


def register_crud_table_routes(
    bp: Blueprint,
    view_class: type[CrudTableView],
    *,
    base_path: str,
    name_prefix: str,
    table_endpoint: str | None = None,
) -> None:
    """Register the four standard URL rules for a CRUD table view.

    Every CRUD table exposes the same four endpoints relative to its base
    path: the item collection (GET list / POST create), a single item
    (POST update / DELETE), the add form (GET), and the edit form (GET).
    Centralize the registration so each route package declares only its
    base path and endpoint naming.

    Args:
        bp: Blueprint to register the rules on.
        view_class: CrudTableView subclass handling the table.
        base_path: URL prefix for the item collection, including any path
            converters the view's handler reads from ``request.view_args``.
        name_prefix: Endpoint name for the collection/item rules; the form
            rules are named ``{name_prefix}_form`` and ``{name_prefix}_form_edit``.
        table_endpoint: Override for the collection/item endpoint name when
            it does not match ``name_prefix``. Endpoint names are frozen by
            ``url_for`` references in templates, so renaming one is a behavior
            change — campaign_notes keeps its historical ``notes_table`` name
            this way. New tables should not need the override.
    """
    table_view = view_class.as_view(table_endpoint or name_prefix)
    bp.add_url_rule(
        base_path,
        defaults={"item_id": None},
        view_func=table_view,
        methods=["GET", "POST"],
    )
    bp.add_url_rule(
        f"{base_path}/<string:item_id>",
        view_func=table_view,
        methods=["POST", "DELETE"],
    )
    bp.add_url_rule(
        f"{base_path}/form",
        defaults={"item_id": None},
        view_func=view_class.as_view(f"{name_prefix}_form"),
        methods=["GET"],
    )
    bp.add_url_rule(
        f"{base_path}/form/<string:item_id>",
        view_func=view_class.as_view(f"{name_prefix}_form_edit"),
        methods=["GET"],
    )
