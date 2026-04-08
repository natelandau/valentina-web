"""Character notes CRUD handler."""

from __future__ import annotations

from flask import g, session
from vclient import sync_characters_service

from vweb.lib.base_notes import BaseNotesHandler


class CharacterNotesHandler(BaseNotesHandler):
    """CRUD operations for character notes.

    Wrap vclient character note API calls with sync interface.
    Usable standalone from any route or via the CRUD table framework.
    """

    def __init__(self, parent_id: str) -> None:
        self._parent_id = parent_id
        character = next((c for c in g.global_context.characters if c.id == parent_id), None)
        if character is None:
            msg = f"Character not found: {parent_id}"
            raise ValueError(msg)

        self._svc = sync_characters_service(
            user_id=session.get("user_id", ""),
            campaign_id=character.campaign_id,
        )
