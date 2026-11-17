"""Campaign notes CRUD handler."""

from __future__ import annotations

from vweb.lib import api_services
from vweb.lib.base_notes import BaseNotesHandler


class CampaignNotesHandler(BaseNotesHandler):
    """CRUD operations for campaign-level notes.

    The campaign id is the note parent id.
    """

    def __init__(self, parent_id: str) -> None:
        self._parent_id = parent_id
        self._svc = api_services.campaigns()
