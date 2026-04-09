"""Character autogeneration service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flask import session
from vclient import sync_character_autogen_service, sync_character_blueprint_service

from vweb.constants import CACHE_BLUEPRINT_TTL
from vweb.extensions import cache
from vweb.lib.options_cache import get_options

if TYPE_CHECKING:
    from vclient.constants import (
        AbilityFocus,
        AutoGenExperienceLevel,
        CharacterClass,
        CharacterType,
    )
    from vclient.models import Character, ChargenSessionResponse


def generate_single(  # noqa: PLR0913
    *,
    user_id: str,
    campaign_id: str,
    character_type: str,
    character_class: str | None = None,
    experience_level: str | None = None,
    skill_focus: str | None = None,
    concept_id: str | None = None,
    vampire_clan_id: str | None = None,
    werewolf_tribe_id: str | None = None,
    werewolf_auspice_id: str | None = None,
) -> Character:
    """Generate a single character via the autogen API.

    Args:
        user_id: The requesting user's ID.
        campaign_id: The campaign to create the character in.
        character_type: Required character type (PLAYER, NPC, STORYTELLER, DEVELOPER).
        character_class: Optional class (VAMPIRE, WEREWOLF, etc.).
        experience_level: Optional experience tier.
        skill_focus: Optional ability distribution focus.
        concept_id: Optional concept ID from the blueprint service.
        vampire_clan_id: Optional vampire clan (only relevant for VAMPIRE class).
        werewolf_tribe_id: Optional werewolf tribe (only relevant for WEREWOLF class).
        werewolf_auspice_id: Optional werewolf auspice (only relevant for WEREWOLF class).

    Returns:
        The newly generated Character.
    """
    svc = sync_character_autogen_service(
        user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
    )
    return svc.generate_character(
        character_type=cast("CharacterType", character_type),
        character_class=cast("CharacterClass", character_class) if character_class else None,
        experience_level=cast("AutoGenExperienceLevel", experience_level)
        if experience_level
        else None,
        skill_focus=cast("AbilityFocus", skill_focus) if skill_focus else None,
        concept_id=concept_id,
        vampire_clan_id=vampire_clan_id,
        werewolf_tribe_id=werewolf_tribe_id,
        werewolf_auspice_id=werewolf_auspice_id,
    )


def start_session(*, user_id: str, campaign_id: str) -> ChargenSessionResponse:
    """Start a multi-autogen chargen session.

    Args:
        user_id: The requesting user's ID.
        campaign_id: The campaign to generate characters for.

    Returns:
        A ChargenSessionResponse with session_id and 3 generated characters.
    """
    svc = sync_character_autogen_service(
        user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
    )
    return svc.start_chargen_session()


def finalize_session(
    *,
    user_id: str,
    campaign_id: str,
    session_id: str,
    selected_character_id: str,
) -> Character:
    """Finalize a chargen session by selecting one character.

    Args:
        user_id: The requesting user's ID.
        campaign_id: The campaign the session belongs to.
        session_id: The chargen session ID.
        selected_character_id: The ID of the chosen character.

    Returns:
        The finalized Character.
    """
    svc = sync_character_autogen_service(
        user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
    )
    return svc.finalize_chargen_session(
        session_id=session_id,
        selected_character_id=selected_character_id,
    )


def list_sessions(*, user_id: str, campaign_id: str) -> list[ChargenSessionResponse]:
    """List all active chargen sessions for a user in a campaign.

    Args:
        user_id: The requesting user's ID.
        campaign_id: The campaign to list sessions for.

    Returns:
        All active chargen sessions for the user/campaign.
    """
    svc = sync_character_autogen_service(
        user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
    )
    return svc.list_all()


def get_session(*, user_id: str, campaign_id: str, session_id: str) -> ChargenSessionResponse:
    """Retrieve a single chargen session by ID.

    Args:
        user_id: The requesting user's ID.
        campaign_id: The campaign the session belongs to.
        session_id: The session to retrieve.

    Returns:
        The chargen session matching the given session_id.
    """
    svc = sync_character_autogen_service(
        user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
    )
    return svc.get(session_id)


def fetch_form_options() -> dict:
    """Fetch all dropdown data for the single autogen form.

    Returns:
        Dict with enum lists and blueprint data for form selects.
    """
    cache_key = "form_options:character_create"
    cached: dict | None = cache.get(cache_key)
    if cached is not None:
        return cached

    bp_svc = sync_character_blueprint_service()
    opts = get_options().characters
    result = {
        "character_classes": opts.character_class,
        "experience_levels": opts.autogen_experience_level,
        "skill_focuses": opts.ability_focus,
        "concepts": bp_svc.list_all_concepts(),
        "vampire_clans": bp_svc.list_all_vampire_clans(),
        "werewolf_tribes": bp_svc.list_all_werewolf_tribes(),
        "werewolf_auspices": bp_svc.list_all_werewolf_auspices(),
    }
    cache.set(cache_key, result, timeout=CACHE_BLUEPRINT_TTL)
    return result
