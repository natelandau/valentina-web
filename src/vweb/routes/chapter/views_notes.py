"""Chapter notes CRUD table view."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import abort, request

from vweb.lib.crud_view import Column, CrudTableView
from vweb.routes.chapter.handlers import ChapterNotesHandler

if TYPE_CHECKING:
    from vweb.lib.crud_handler import CrudHandler


class ChapterNotesTableView(CrudTableView):
    """Inline CRUD table for chapter notes."""

    handler_class = ChapterNotesHandler
    table_name = "Notes"
    item_name = "Note"
    table_id = "crud-chapter_notes"
    columns = (
        Column("title", "Title"),
        Column("content", "Content", markdown=True, sortable=False),
    )
    form_component = "shared.crud.NoteForm"

    def _build_handler(self) -> CrudHandler[Any]:
        """Instantiate handler with chapter_id, campaign_id, and book_id from URL path."""
        chapter_id = (request.view_args or {}).get("chapter_id", "")
        campaign_id = (request.view_args or {}).get("campaign_id", "")
        book_id = (request.view_args or {}).get("book_id", "")
        try:
            return self.handler_class(
                parent_id=chapter_id,
                campaign_id=campaign_id,
                book_id=book_id,
            )
        except ValueError:
            abort(404)
