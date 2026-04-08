"""Character notes CRUD table view."""

from __future__ import annotations

from vweb.lib.crud_view import Column, CrudTableView
from vweb.routes.character_view.handlers_notes import CharacterNotesHandler


class CharacterNotesTableView(CrudTableView):
    """Inline CRUD table for character notes."""

    handler_class = CharacterNotesHandler
    table_name = "Notes"
    item_name = "Note"
    table_id = "crud-notes"
    columns = (
        Column("title", "Title"),
        Column("content", "Content", markdown=True, sortable=False),
    )
    form_component = "shared.crud.NoteForm"
