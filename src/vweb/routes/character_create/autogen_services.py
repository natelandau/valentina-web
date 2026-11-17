"""Character autogeneration service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flask import session

from vweb.api_client.exceptions import NotFoundError
from vweb.constants import CACHE_BLUEPRINT_TTL
from vweb.lib import api_services, cache

_FORM_OPTIONS_STRATEGY = cache.base.PureTTL(ttl=CACHE_BLUEPRINT_TTL)

if TYPE_CHECKING:
    from vweb.api_client.constants import (
        AbilityFocus,
        AutoGenExperienceLevel,
        CharacterClass,
        CharacterType,
    )
    from vweb.api_client.models import Character, ChargenSessionResponse


def generate_single(  # noqa: PLR0913
    *,
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
        campaign_id: The campaign to create the character in.
        character_type: Required character type (PLAYER, NPC, STORYTELLER).
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
    svc = api_services.character_autogen()
    return svc.generate_character(
        campaign_id=campaign_id,
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


def start_session(*, campaign_id: str) -> ChargenSessionResponse:
    """Start a multi-autogen chargen session.

    Args:
        campaign_id: The campaign to generate characters for.

    Returns:
        A ChargenSessionResponse with session_id and 3 generated characters.
    """
    svc = api_services.character_autogen()
    return svc.start_chargen_session(campaign_id=campaign_id)


def finalize_session(
    *,
    campaign_id: str,  # noqa: ARG001
    session_id: str,
    selected_character_id: str,
) -> Character:
    """Finalize a chargen session by selecting one character.

    Args:
        campaign_id: The campaign the session belongs to.
        session_id: The chargen session ID.
        selected_character_id: The ID of the chosen character.

    Returns:
        The finalized Character.
    """
    svc = api_services.character_autogen()
    return svc.finalize_chargen_session(
        session_id=session_id,
        selected_character_id=selected_character_id,
    )


def list_sessions(*, campaign_id: str) -> list[ChargenSessionResponse]:
    """List the user's chargen sessions in a campaign.

    The API lists the user's sessions across every campaign, so keep only this campaign's.

    Args:
        campaign_id: The campaign to list sessions for.

    Returns:
        The user's chargen sessions in the campaign.
    """
    svc = api_services.character_autogen()
    return [s for s in svc.list_all() if s.campaign_id == campaign_id]


def get_session(*, campaign_id: str, session_id: str) -> ChargenSessionResponse:
    """Retrieve a single chargen session by ID.

    Args:
        campaign_id: The campaign the session must belong to.
        session_id: The session to retrieve.

    Returns:
        The chargen session matching the given session_id.

    Raises:
        NotFoundError: If the session belongs to another campaign.
    """
    svc = api_services.character_autogen()
    chargen_session = svc.get(session_id)
    if chargen_session.campaign_id != campaign_id:
        msg = f"Chargen session {session_id} is not in campaign {campaign_id}"
        raise NotFoundError(msg, 404)
    return chargen_session


def fetch_form_options() -> dict:
    """Fetch all dropdown data for the single autogen form.

    Returns:
        Dict with enum lists and blueprint data for form selects.
    """

    def _build() -> dict:
        bp_svc = api_services.character_blueprint()
        opts = cache.options.get().characters
        return {
            "character_classes": opts.character_class,
            "experience_levels": opts.autogen_experience_level,
            "skill_focuses": opts.ability_focus,
            "concepts": bp_svc.list_all_concepts(),
            "vampire_clans": bp_svc.list_all_vampire_clans(),
            "werewolf_tribes": bp_svc.list_all_werewolf_tribes(),
            "werewolf_auspices": bp_svc.list_all_werewolf_auspices(),
        }

    # Company-scoped: concepts/clans/tribes/auspices come from the company's blueprint.
    key = f"form_options:character_create:{session['company_id']}"
    return cache.base.cached_fetch(key, _build, _FORM_OPTIONS_STRATEGY)
