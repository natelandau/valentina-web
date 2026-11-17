"""Chapter notes CRUD handler."""

from __future__ import annotations

from vweb.lib import api_services
from vweb.lib.base_notes import BaseNotesHandler


class ChapterNotesHandler(BaseNotesHandler):
    """CRUD operations for chapter notes.

    Wrap vclient chapter note API calls with sync interface.
    Requires campaign_id and book_id as extra kwargs since chapters
    are not stored in the global context.
    """

    def __init__(self, parent_id: str, campaign_id: str = "", book_id: str = "") -> None:
        self._parent_id = parent_id

        if not campaign_id or not book_id:
            msg = "campaign_id and book_id are required for ChapterNotesHandler"
            raise ValueError(msg)

        self._svc = api_services.chapters(campaign_id, book_id)
