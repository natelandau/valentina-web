"""Book notes CRUD handler."""

from __future__ import annotations

from flask import session
from vclient import sync_books_service

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

        self._svc = sync_books_service(
            campaign_id=campaign_id,
            on_behalf_of=session.get("user_id", ""),
            company_id=session["company_id"],
        )
