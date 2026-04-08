"""Base CRUD table view and column configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from flask import abort, render_template, request
from flask.views import MethodView
from loguru import logger
from vclient.exceptions import APIError

from vweb import catalog
from vweb.lib.global_context import clear_global_context_cache

if TYPE_CHECKING:
    from vweb.lib.crud_handler import CrudHandler


@dataclass(frozen=True)
class Column:
    """Configuration for a single CRUD table column.

    Pair a model field name with its display header and rendering options.
    Used by CrudTableView subclasses to declare table structure.

    Args:
        field: Model attribute name used to read cell values.
        header: Human-readable column header for display.
        markdown: Render this field through the from_markdown filter.
        sortable: Allow users to sort the table by this column.
    """

    field: str
    header: str
    markdown: bool = False
    sortable: bool = True


class CrudTableView(MethodView):
    """Base view for inline-editable CRUD tables.

    Subclass and set class attributes to create a CRUD table for any resource.
    Handle list display, add/edit forms, create, update, delete, and sorting.
    All data access is delegated to the handler class.

    Required class attributes:
        handler_class: Class implementing the CrudHandler protocol.
        table_name: Display heading shown above the table.
        item_name: Singular noun for buttons and modals.
        columns: Tuple of Column instances defining table structure.
        form_component: JinjaX component path for form fields.
        table_id: HTML id for the HTMX swap target div.
    """

    handler_class: ClassVar[type]
    table_name: ClassVar[str]
    item_name: ClassVar[str]
    columns: ClassVar[tuple[Column, ...]]
    form_component: ClassVar[str]
    table_id: ClassVar[str]

    # Derived class-level attributes, computed once by __init_subclass__
    fields: ClassVar[tuple[str, ...]]
    headers: ClassVar[tuple[str, ...]]
    markdown_fields: ClassVar[frozenset[str]]
    sortable_fields: ClassVar[frozenset[str]]
    _default_sort_field: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Compute derived column metadata once at class definition time."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "columns"):
            cls.fields = tuple(c.field for c in cls.columns)
            cls.headers = tuple(c.header for c in cls.columns)
            cls.markdown_fields = frozenset(c.field for c in cls.columns if c.markdown)
            cls.sortable_fields = frozenset(c.field for c in cls.columns if c.sortable)
            cls._default_sort_field = next(
                (c.field for c in cls.columns if c.sortable), cls.columns[0].field
            )

    def _build_handler(self) -> CrudHandler[Any]:
        """Instantiate the handler for the current request.

        Default implementation reads parent_id from URL path params.
        Override in subclasses that need additional context (e.g., campaign_id).

        Raises:
            werkzeug.exceptions.NotFound: If the handler raises ValueError.
        """
        parent_id = (request.view_args or {}).get("parent_id", "")
        if not parent_id:
            abort(400)

        try:
            return self.handler_class(parent_id)
        except ValueError:
            abort(404)

    def _parse_sort(self) -> tuple[str, str]:
        """Parse the sort query parameter into (field, direction).

        Read ?sort=field or ?sort=-field from the request. Validate the field
        is sortable. Fall back to first sortable field ascending on invalid input.

        Returns:
            Tuple of (field_name, "asc" or "desc").
        """
        sortable = self.sortable_fields
        raw = request.args.get("sort", "")

        if raw.startswith("-"):
            field = raw[1:]
            direction = "desc"
        else:
            field = raw
            direction = "asc"

        if not field or field not in sortable:
            return self._default_sort_field, "asc"

        return field, direction

    def _sort_items(self, items: list) -> tuple[list, str, str]:
        """Sort items based on the current request's sort parameter.

        Args:
            items: Unsorted list of items from the API.

        Returns:
            Tuple of (sorted_items, sort_field, sort_direction).
        """
        sort_field, sort_dir = self._parse_sort()
        sorted_items = sorted(
            items,
            key=lambda item: str(getattr(item, sort_field, "") or "").lower(),
            reverse=sort_dir == "desc",
        )
        return sorted_items, sort_field, sort_dir

    def _render_refetch(self) -> str:
        """Return a loading snippet that triggers a fresh GET for the table.

        After mutations, a fresh GET through a new handler instance
        guarantees up-to-date data from the API.
        """
        editable = request.args.get("editable", "true")
        base = request.base_url
        # After POST/DELETE to .../notes/<item_id>, strip the item_id segment
        # to get the table list URL (.../notes) for the refetch GET
        if request.view_args and request.view_args.get("item_id"):
            base = base.rsplit("/", 1)[0]
        return render_template(
            "partials/crud_refetch.html",
            table_url=f"{base}?editable={editable}",
            table_target_id=self.table_id,
        )

    def _get_parent_id(self) -> str:
        """Resolve the parent_id from URL path params or query string."""
        return (request.view_args or {}).get("parent_id", request.args.get("parent_id", ""))

    def _render_table(
        self,
        items: list,
        sort_field: str = "",
        sort_dir: str = "asc",
        *,
        editable: bool = True,
    ) -> str:
        """Render the table display fragment."""
        base_url = request.base_url
        editable_param = "true" if editable else "false"
        return catalog.render(
            "shared.crud.CrudTable",
            table_type_name=self.table_name,
            table_type_item_name=self.item_name,
            columns=self.headers,
            fields=self.fields,
            markdown_fields=self.markdown_fields,
            sortable_fields=self.sortable_fields,
            items=items,
            parent_id=self._get_parent_id(),
            table_base_url=base_url,
            form_base_url=f"{base_url}/form",
            table_target_id=self.table_id,
            sort_field=sort_field,
            sort_dir=sort_dir,
            editable=editable,
            extra_params=f"&editable={editable_param}",
        )

    def _render_form(
        self,
        item: Any | None = None,
        errors: list | None = None,
        form_data: dict | None = None,
    ) -> str:
        """Render the add/edit form fragment."""
        is_edit = item is not None
        base_url = request.base_url
        table_base = base_url.split("/form")[0] if "/form" in base_url else base_url

        editable = request.args.get("editable", "true")
        if item is not None:
            post_url = f"{table_base}/{item.id}?editable={editable}"
        else:
            post_url = f"{table_base}?editable={editable}"

        form_fields_html = catalog.render(
            self.form_component,
            item=item,
            form_data=form_data,
        )

        return catalog.render(
            "shared.crud.CrudForm",
            table_type_name=self.table_name,
            table_type_item_name=self.item_name,
            post_url=post_url,
            table_url=f"{table_base}?editable={editable}",
            table_target_id=self.table_id,
            errors=errors or [],
            is_edit=is_edit,
            _content=form_fields_html,
        )

    def get(self, item_id: str | None = None, **kwargs: str) -> str:  # noqa: ARG002
        """Handle GET: return table display, add form, or edit form."""
        handler = self._build_handler()
        is_form = request.path.rstrip("/").endswith("/form") or (
            item_id is not None and "/form/" in request.path
        )

        if is_form:
            item = handler.get_item(item_id) if item_id else None
            return self._render_form(item=item)

        editable = request.args.get("editable", "true").lower() == "true"
        items = handler.list_items()
        sorted_items, sort_field, sort_dir = self._sort_items(items)
        return self._render_table(sorted_items, sort_field, sort_dir, editable=editable)

    def post(self, item_id: str | None = None, **kwargs: str) -> str:  # noqa: ARG002
        """Handle POST: create or update an item."""
        handler = self._build_handler()
        form_data = dict(request.form)

        errors = handler.validate(form_data)
        if errors:
            item = handler.get_item(item_id) if item_id else None
            return self._render_form(item=item, errors=errors, form_data=form_data)

        try:
            if item_id:
                handler.update_item(item_id, form_data)
            else:
                handler.create_item(form_data)
        except APIError:
            logger.exception("CRUD operation failed")
            item = handler.get_item(item_id) if item_id else None
            return self._render_form(
                item=item,
                errors=["An error occurred. Please try again."],
                form_data=form_data,
            )

        clear_global_context_cache()
        return self._render_refetch()

    def delete(self, item_id: str | None = None, **kwargs: str) -> str:  # noqa: ARG002
        """Handle DELETE: remove an item and trigger a table refresh."""
        handler = self._build_handler()

        if not item_id:
            abort(400)

        try:
            handler.delete_item(item_id)
        except APIError:
            logger.exception("Delete operation failed")

        clear_global_context_cache()
        return self._render_refetch()
