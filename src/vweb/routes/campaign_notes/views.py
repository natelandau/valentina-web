"""Campaign notes page + inline CRUD table.

- ``/campaign/<campaign_id>/notes`` — full page. Lazy-loads the CRUD table via
  HTMX on load (same pattern as book notes).
- ``/campaign/<campaign_id>/notes/items[/<item_id>]`` — CRUD table + item
  endpoints handled by ``CampaignNotesTableView`` (CrudTableView subclass).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import Blueprint, abort, request, session
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.crud.view import Column, CrudTableView
from vweb.routes.campaign_notes.handlers import CampaignNotesHandler

if TYPE_CHECKING:
    from vweb.lib.crud.handler import CrudHandler

bp = Blueprint("campaign_notes", __name__)


class NotesIndexView(MethodView):
    """Full page shell: CampaignChrome + HTMX lazy-loaded CRUD table."""

    def get(self, campaign_id: str) -> str:
        """Render the notes page for the campaign."""
        campaign = fetch_campaign_or_404(campaign_id)
        session["last_campaign_id"] = campaign_id
        return catalog.render("campaign_notes.Index", campaign=campaign)


class CampaignNotesTableView(CrudTableView):
    """Inline CRUD table for campaign notes, client-side paginated at 10/page."""

    handler_class = CampaignNotesHandler
    table_name = "Notes"
    item_name = "Note"
    table_id = "crud-campaign_notes"
    columns = (
        Column("title", "Title"),
        Column("content", "Content", markdown=True, sortable=False),
    )
    form_component = "shared.crud.NoteForm"
    pagination = 10

    def _build_handler(self) -> CrudHandler[Any]:
        """Instantiate handler using campaign_id from the URL path."""
        campaign_id = (request.view_args or {}).get("campaign_id", "")
        if not campaign_id:
            abort(400)
        try:
            return self.handler_class(campaign_id)
        except ValueError:
            abort(404)


bp.add_url_rule(
    "/campaign/<string:campaign_id>/notes",
    view_func=NotesIndexView.as_view("index"),
    methods=["GET"],
)

_campaign_notes_view = CampaignNotesTableView.as_view("notes_table")
bp.add_url_rule(
    "/campaign/<string:campaign_id>/notes/items",
    defaults={"item_id": None},
    view_func=_campaign_notes_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/notes/items/<string:item_id>",
    view_func=_campaign_notes_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/notes/items/form",
    defaults={"item_id": None},
    view_func=CampaignNotesTableView.as_view("notes_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/notes/items/form/<string:item_id>",
    view_func=CampaignNotesTableView.as_view("notes_form_edit"),
    methods=["GET"],
)
