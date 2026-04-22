"""Campaign notes CRUD handler."""

from __future__ import annotations

from flask import session
from vclient import sync_campaigns_service

from vweb.lib.base_notes import BaseNotesHandler


class CampaignNotesHandler(BaseNotesHandler):
    """CRUD operations for campaign-level notes.

    Wrap vclient campaign note API calls via the sync service. The parent is
    the campaign itself — ``parent_id`` is the campaign id.
    """

    def __init__(self, parent_id: str) -> None:
        self._parent_id = parent_id
        self._svc = sync_campaigns_service(
            on_behalf_of=session.get("user_id", ""),
            company_id=session["company_id"],
        )
