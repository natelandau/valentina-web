"""Book notes CRUD handler."""

from __future__ import annotations

from vweb.lib import api_services
from vweb.lib.base_notes import BaseNotesHandler


class BookNotesHandler(BaseNotesHandler):
    """CRUD operations for book notes.

    Wrap vclient book note API calls with sync interface.
    Usable standalone from any route or via the CRUD table framework.
    """

    def __init__(self, parent_id: str, campaign_id: str = "") -> None:
        self._parent_id = parent_id

        if not campaign_id:
            msg = "campaign_id is required for BookNotesHandler"
            raise ValueError(msg)

        self._svc = api_services.books(campaign_id)
