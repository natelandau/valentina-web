"""Manual character creation service layer."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, cast

from flask import session
from pydantic import ValidationError as PydanticValidationError
from vclient import sync_character_traits_service, sync_characters_service
from vclient.exceptions import APIError, ValidationError
from vclient.models import CharacterCreate, CharacterTraitAdd, CharacterUpdate

from vweb.lib.guards import can_manage_npcs, is_storyteller
from vweb.routes.character_create.profile_form import build_class_attrs, character_to_form_data

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vclient.constants import CharacterClass, CharacterType, GameVersion
    from vclient.models import Character

logger = logging.getLogger(__name__)


_TRAIT_PREFIX: str = "trait:"
_SESSION_TTL_SECONDS: int = 30 * 60  # 30 minutes


def _map_pydantic_errors(exc: PydanticValidationError) -> dict[str, str]:
    """Convert a PydanticValidationError into a template-friendly error dict.

    Profile fields are already checked by validate_profile before the payload is
    built, so a pydantic error here means a value the form cannot surface inline
    (e.g. a crafted "type"). Collect all messages under "_general" so the user
    always receives visible feedback.

    Args:
        exc: The validation error raised by a CharacterCreate or CharacterUpdate call.

    Returns:
        Dict with a single "_general" key mapping to the combined error messages.
    """
    messages = [err["msg"] for err in exc.errors()]
    return {"_general": "; ".join(messages)}


def character_type_permission_error(char_type: str) -> str | None:
    """Return an authorization error if the user may not assign ``char_type``.

    NPCs require NPC-management permission; STORYTELLER characters are always
    storyteller/admin-only. Returns None when the type is permitted, so callers
    can use it as a single gate for both the create and edit flows.
    """
    if char_type == "NPC" and not can_manage_npcs():
        return "You are not authorized to assign the NPC character type."
    if char_type == "STORYTELLER" and not is_storyteller():
        return "You are not authorized to assign the storyteller character type."
    return None


def clear_temp_session() -> None:
    """Remove temporary character creation data from the session."""
    session.pop("temp_character_id", None)
    session.pop("temp_character_created_at", None)


def _is_temp_session_expired() -> bool:
    """Check whether the temporary character session data has exceeded its TTL."""
    created_at = session.get("temp_character_created_at")
    if created_at is None:
        return False
    return (time.monotonic() - created_at) > _SESSION_TTL_SECONDS


def fetch_character(character_id: str) -> Character:
    """Fetch a character via the API on behalf of the session user.

    Args:
        character_id: The character to retrieve.

    Returns:
        The requested Character.
    """
    svc = sync_characters_service(
        on_behalf_of=session["user_id"],
        company_id=session["company_id"],
    )
    return svc.get(character_id)


def load_temp_character_form_data(*, is_resuming: bool, fallback: dict[str, str]) -> dict[str, str]:
    """Resolve profile-form pre-fill data from the temporary character session.

    Clears stale or expired temp sessions first, then prefers the temp
    character's saved profile so a resuming user sees their in-progress work.

    Args:
        is_resuming: Whether the request explicitly resumes an in-progress creation.
        fallback: Form data to use when no temp character is available.

    Returns:
        Form field dict for template pre-fill.
    """
    if not is_resuming or _is_temp_session_expired():
        clear_temp_session()

    temp_char_id = session.get("temp_character_id")
    if not temp_char_id:
        return fallback

    try:
        character = fetch_character(temp_char_id)
    except APIError:
        logger.warning("Failed to fetch temp character %s", temp_char_id)
        clear_temp_session()
        return fallback

    return character_to_form_data(character)


def _build_update_payload(form_data: dict[str, str]) -> CharacterUpdate:
    """Build a CharacterUpdate payload from validated profile form data.

    Args:
        form_data: Stripped, validated profile form data.

    Returns:
        The CharacterUpdate payload for the characters service.
    """
    character_class = cast("CharacterClass", form_data["character_class"])
    game_version = cast("GameVersion", form_data["game_version"])
    age_str = form_data.get("age", "").strip()
    _create_attrs, update_attrs = build_class_attrs(character_class, form_data)
    vampire_u, werewolf_u, hunter_u, mage_attrs = update_attrs

    return CharacterUpdate(
        character_class=character_class,
        game_version=game_version,
        name_first=form_data["name_first"],
        name_last=form_data["name_last"],
        type=cast("CharacterType", form_data.get("character_type") or "PLAYER"),
        name_nick=form_data.get("name_nick") or None,
        age=int(age_str) if age_str else None,
        biography=form_data.get("biography") or None,
        demeanor=form_data.get("demeanor") or None,
        nature=form_data.get("nature") or None,
        concept_id=form_data.get("concept_id") or None,
        vampire_attributes=vampire_u,
        werewolf_attributes=werewolf_u,
        hunter_attributes=hunter_u,
        mage_attributes=mage_attrs,
    )


def _build_create_payload(campaign_id: str, form_data: dict[str, str]) -> CharacterCreate:
    """Build a temporary-character CharacterCreate payload from validated form data.

    Args:
        campaign_id: The campaign the character belongs to.
        form_data: Stripped, validated profile form data.

    Returns:
        The CharacterCreate payload for the characters service.
    """
    character_class = cast("CharacterClass", form_data["character_class"])
    game_version = cast("GameVersion", form_data["game_version"])
    age_str = form_data.get("age", "").strip()
    create_attrs, _update_attrs = build_class_attrs(character_class, form_data)
    vampire_c, werewolf_c, hunter_c, mage_attrs = create_attrs

    return CharacterCreate(
        campaign_id=campaign_id,
        character_class=character_class,
        game_version=game_version,
        name_first=form_data["name_first"],
        name_last=form_data["name_last"],
        type=cast("CharacterType", form_data.get("character_type") or "PLAYER"),
        name_nick=form_data.get("name_nick") or None,
        age=int(age_str) if age_str else None,
        biography=form_data.get("biography") or None,
        demeanor=form_data.get("demeanor") or None,
        nature=form_data.get("nature") or None,
        concept_id=form_data.get("concept_id") or None,
        is_temporary=True,
        user_player_id=session["user_id"],
        vampire_attributes=vampire_c,
        werewolf_attributes=werewolf_c,
        hunter_attributes=hunter_c,
        mage_attributes=mage_attrs,
    )


def update_character_profile(character_id: str, form_data: dict[str, str]) -> dict[str, str]:
    """Update an existing character's profile from validated form data.

    Args:
        character_id: The character being edited.
        form_data: Stripped, validated profile form data.

    Returns:
        Errors keyed by field name (empty when the update succeeds).
    """
    svc = sync_characters_service(
        on_behalf_of=session["user_id"],
        company_id=session["company_id"],
    )
    try:
        svc.update(character_id, _build_update_payload(form_data))
    except PydanticValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            field_name = str(err["loc"][0]) if err["loc"] else "unknown"
            errors[field_name] = err["msg"]
        return errors
    except ValidationError as exc:
        errors = {p["field"]: p["message"] for p in exc.invalid_parameters}
        if exc.detail:
            errors["_general"] = exc.detail
        return errors
    except APIError as exc:
        return {"_general": exc.detail or exc.message or "Failed to update profile"}
    return {}


def save_temp_character(campaign_id: str, form_data: dict[str, str]) -> dict[str, str]:
    """Create or update the in-progress temporary character from validated form data.

    Updates the existing temp character when one is tracked in the session,
    otherwise creates a new temporary character and records it in the session.

    Args:
        campaign_id: The campaign the character belongs to.
        form_data: Stripped, validated profile form data.

    Returns:
        Errors keyed by field name (empty when the save succeeds).
    """
    svc = sync_characters_service(
        on_behalf_of=session["user_id"],
        company_id=session["company_id"],
    )
    temp_char_id = session.get("temp_character_id")

    try:
        if temp_char_id:
            svc.update(temp_char_id, _build_update_payload(form_data))
        else:
            new_char = svc.create(_build_create_payload(campaign_id, form_data))
            session["temp_character_id"] = new_char.id
            session["temp_character_created_at"] = time.monotonic()
    except PydanticValidationError as exc:
        return _map_pydantic_errors(exc)
    except ValidationError as exc:
        errors = {p["field"]: p["message"] for p in exc.invalid_parameters}
        if exc.detail:
            errors["_general"] = exc.detail
        return errors
    except APIError as exc:
        logger.exception("Failed to save temporary character")
        return {"_general": exc.detail or exc.message or "Failed to save profile"}
    return {}


def build_trait_items(form_data: Mapping[str, str]) -> list[CharacterTraitAdd]:
    """Extract positive trait values from the traits form into bulk-assign payloads.

    Args:
        form_data: Submitted form fields, with trait values keyed as "trait:<id>".

    Returns:
        CharacterTraitAdd payloads for every trait with a positive integer value.
    """
    trait_items: list[CharacterTraitAdd] = []
    for key, value in form_data.items():
        if not key.startswith(_TRAIT_PREFIX):
            continue
        trait_id = key[len(_TRAIT_PREFIX) :]
        try:
            int_val = int(value)
        except ValueError:
            continue
        if int_val > 0:
            trait_items.append(
                CharacterTraitAdd(trait_id=trait_id, value=int_val, currency="NO_COST")
            )
    return trait_items


def bulk_assign_traits(character_id: str, trait_items: list[CharacterTraitAdd]) -> list[str]:
    """Bulk-assign traits to a character, skipping the API call when nothing is selected.

    Args:
        character_id: The character receiving the traits.
        trait_items: Trait payloads to assign.

    Returns:
        Trait IDs that failed to assign (empty when all succeed).
    """
    if not trait_items:
        return []

    traits_svc = sync_character_traits_service(
        on_behalf_of=session["user_id"],
        character_id=character_id,
        company_id=session["company_id"],
    )
    result = traits_svc.bulk_assign(trait_items)
    return [f.trait_id for f in result.failed]


def mark_character_permanent(character_id: str) -> None:
    """Flip a temporary character to permanent once creation is finalized.

    Args:
        character_id: The temporary character to finalize.
    """
    svc = sync_characters_service(
        on_behalf_of=session["user_id"],
        company_id=session["company_id"],
    )
    svc.update(character_id, CharacterUpdate(is_temporary=False))
