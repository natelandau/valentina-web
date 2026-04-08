"""Book notes CRUD table view."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import abort, request

from vweb.lib.crud_view import Column, CrudTableView
from vweb.routes.book.handlers import BookNotesHandler

if TYPE_CHECKING:
    from vweb.lib.crud_handler import CrudHandler


class BookNotesTableView(CrudTableView):
    """Inline CRUD table for book notes."""

    handler_class = BookNotesHandler
    table_name = "Notes"
    item_name = "Note"
    table_id = "crud-book_notes"
    columns = (
        Column("title", "Title"),
        Column("content", "Content", markdown=True, sortable=False),
    )
    form_component = "shared.crud.NoteForm"

    def _build_handler(self) -> CrudHandler[Any]:
        """Instantiate handler with book_id and campaign_id from URL path."""
        book_id = (request.view_args or {}).get("book_id", "")
        campaign_id = (request.view_args or {}).get("campaign_id", "")
        try:
            return self.handler_class(parent_id=book_id, campaign_id=campaign_id)
        except ValueError:
            abort(404)
