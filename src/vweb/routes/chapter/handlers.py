"""Chapter notes CRUD handler."""

from __future__ import annotations

from flask import session
from vclient import sync_chapters_service

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

        self._svc = sync_chapters_service(
            user_id=session.get("user_id", ""),
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
