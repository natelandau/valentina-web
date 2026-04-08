"""Quickrolls CRUD table view."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import abort, request

from vweb.lib.crud_view import Column, CrudTableView
from vweb.lib.guards import is_self
from vweb.routes.profile.handlers import QuickrollHandler

if TYPE_CHECKING:
    from vweb.lib.crud_handler import CrudHandler


class QuickrollsTableView(CrudTableView):
    """Inline CRUD table for user quickrolls.

    Only the owner of the profile may add, edit, or delete quickrolls —
    storytellers and admins cannot modify another player's quickrolls. Read
    access (the table list) is open because the profile page itself is
    viewable by everyone.
    """

    handler_class = QuickrollHandler
    table_name = "Quickrolls"
    item_name = "Quickroll"
    table_id = "crud-quickrolls"
    columns = (
        Column("name", "Name"),
        Column("description", "Description"),
        Column("trait_one_name", "Trait 1"),
        Column("trait_two_name", "Trait 2"),
    )
    form_component = "profile.partials.crud_forms.QuickrollForm"

    def _build_handler(self) -> CrudHandler[Any]:
        """Instantiate handler with user_id from URL path."""
        user_id = (request.view_args or {}).get("user_id", "")
        try:
            return self.handler_class(user_id)
        except ValueError:
            abort(404)

    def _require_owner(self) -> None:
        """Abort 403 unless the requesting user owns the profile being edited."""
        user_id = (request.view_args or {}).get("user_id", "")
        if not is_self(user_id):
            abort(403)

    def get(self, item_id: str | None = None, **kwargs: str) -> str:
        """Render the quickrolls table or a form fragment.

        The list display is open to anyone who can view the profile; form
        endpoints (``/form`` and ``/form/<id>``) are gated because reaching
        them implies intent to write.
        """
        if "/form" in request.path:
            self._require_owner()
        return super().get(item_id=item_id, **kwargs)

    def post(self, item_id: str | None = None, **kwargs: str) -> str:
        """Create or update a quickroll, owner only."""
        self._require_owner()
        return super().post(item_id=item_id, **kwargs)

    def delete(self, item_id: str | None = None, **kwargs: str) -> str:
        """Delete a quickroll, owner only."""
        self._require_owner()
        return super().delete(item_id=item_id, **kwargs)
