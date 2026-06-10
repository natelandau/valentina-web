"""Character creation picker service layer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flask import session
from vclient.exceptions import APIError

from vweb.lib import cache
from vweb.lib.api import get_user_campaign_experience
from vweb.routes.character_create.autogen_services import list_sessions

if TYPE_CHECKING:
    from vclient.models import ChargenSessionResponse, User

logger = logging.getLogger(__name__)


def build_characters_data(session_response: ChargenSessionResponse, user: User) -> list[dict]:
    """Build the character sheet data list for the comparison template.

    Args:
        session_response: The chargen session containing characters.
        user: The requesting user (needed for sheet rendering permissions).

    Returns:
        List of dicts with character, sheet_top, and sheet_sections keys.
    """
    characters_data = []
    for char in session_response.characters:
        full_sheet = cache.character_sheet.get(char.id, user.id)
        characters_data.append(
            {
                "character": char,
                "full_sheet": full_sheet,
            }
        )
    return characters_data


def selection_card_context(campaign_id: str) -> dict:
    """Build the shared template context for the selection card grid.

    Args:
        campaign_id: The campaign to look up XP info for.

    Returns:
        Dict with user_xp, and pending_sessions keys.
    """
    campaign_experience = get_user_campaign_experience(session["user_id"], campaign_id)
    user_xp = campaign_experience.xp_current if campaign_experience else 0

    now = datetime.now(tz=UTC)
    try:
        all_sessions = list_sessions(user_id=session["user_id"], campaign_id=campaign_id)
        pending_sessions = [s for s in all_sessions if s.expires_at > now]
    except APIError:
        logger.exception("Failed to list chargen sessions")
        pending_sessions = []

    return {
        "user_xp": user_xp,
        "pending_sessions": pending_sessions,
    }
