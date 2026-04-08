"""Character profile helpers for validation, form data conversion, and class attributes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient.models.characters import (
    HunterAttributesCreate,
    HunterAttributesUpdate,
    MageAttributes,
    VampireAttributesCreate,
    VampireAttributesUpdate,
    WerewolfAttributesCreate,
    WerewolfAttributesUpdate,
)

from vweb.lib.options_cache import get_options

if TYPE_CHECKING:
    from vclient.models import Character

_NAME_MIN_LENGTH: int = 3

ClassCreateAttrs = tuple[
    VampireAttributesCreate | None,
    WerewolfAttributesCreate | None,
    HunterAttributesCreate | None,
    MageAttributes | None,
]

ClassUpdateAttrs = tuple[
    VampireAttributesUpdate | None,
    WerewolfAttributesUpdate | None,
    HunterAttributesUpdate | None,
    MageAttributes | None,
]


def validate_profile(form_data: dict[str, str]) -> dict[str, str]:
    """Validate character profile form data.

    Args:
        form_data: The form data dict.

    Returns:
        Dict mapping field names to error messages (empty if valid).
    """
    errors: dict[str, str] = {}
    opts = get_options()

    name_first = form_data.get("name_first", "").strip()
    name_last = form_data.get("name_last", "").strip()
    game_version = form_data.get("game_version", "")
    character_class = form_data.get("character_class", "")

    if not name_first or len(name_first) < _NAME_MIN_LENGTH:
        errors["name_first"] = "First name is required (min 3 characters)."
    if not name_last or len(name_last) < _NAME_MIN_LENGTH:
        errors["name_last"] = "Last name is required (min 3 characters)."
    if game_version not in opts.characters.game_version:
        errors["game_version"] = "A valid game version is required."
    if character_class not in opts.characters.character_class:
        errors["character_class"] = "A valid character class is required."

    if character_class in ("VAMPIRE", "GHOUL") and not form_data.get("vampire_clan_id"):
        errors["vampire_clan_id"] = "Vampire clan is required."
    if character_class == "WEREWOLF" and not form_data.get("werewolf_tribe_id"):
        errors["werewolf_tribe_id"] = "Werewolf tribe is required."
    if character_class == "HUNTER" and not form_data.get("creed"):
        errors["creed"] = "Hunter creed is required."

    return errors


def character_to_form_data(character: Character) -> dict[str, str]:
    """Convert a Character object to a form_data dict for template pre-fill.

    Args:
        character: The character to extract profile fields from.

    Returns:
        Dict of form field names to string values.
    """
    data: dict[str, str] = {
        "name_first": character.name_first,
        "name_last": character.name_last,
        "game_version": character.game_version,
        "character_class": character.character_class,
        "character_type": character.type,
    }

    optional: dict[str, str | None] = {
        "name_nick": character.name_nick,
        "age": str(character.age) if character.age is not None else None,
        "biography": character.biography,
        "demeanor": character.demeanor,
        "nature": character.nature,
        "concept_id": character.concept_id,
    }
    data.update({k: v for k, v in optional.items() if v is not None})

    va = character.vampire_attributes
    if va and va.clan_id:
        data["vampire_clan_id"] = va.clan_id

    wa = character.werewolf_attributes
    if wa:
        if wa.tribe_id:
            data["werewolf_tribe_id"] = wa.tribe_id
        if wa.auspice_id:
            data["werewolf_auspice_id"] = wa.auspice_id

    if character.hunter_attributes and character.hunter_attributes.creed:
        data["creed"] = character.hunter_attributes.creed

    ma = character.mage_attributes
    if ma:
        if ma.sphere:
            data["sphere"] = ma.sphere
        if ma.tradition:
            data["tradition"] = ma.tradition

    return data


def build_class_attrs(
    character_class: str, form_data: dict[str, str]
) -> tuple[ClassCreateAttrs, ClassUpdateAttrs]:
    """Build class-specific attribute models for both create and update paths.

    Args:
        character_class: The character class string (e.g. "VAMPIRE", "WEREWOLF").
        form_data: The parsed profile fields from the form submission.

    Returns:
        Tuple of (create_attrs, update_attrs) where each is a 4-tuple of
        (vampire, werewolf, hunter, mage) attribute models.
    """
    vampire_c: VampireAttributesCreate | None = None
    vampire_u: VampireAttributesUpdate | None = None
    werewolf_c: WerewolfAttributesCreate | None = None
    werewolf_u: WerewolfAttributesUpdate | None = None
    hunter_c: HunterAttributesCreate | None = None
    hunter_u: HunterAttributesUpdate | None = None
    mage: MageAttributes | None = None

    match character_class:
        case "VAMPIRE" | "GHOUL":
            clan_id = form_data["vampire_clan_id"]
            vampire_c = VampireAttributesCreate(clan_id=clan_id)
            vampire_u = VampireAttributesUpdate(clan_id=clan_id)
        case "WEREWOLF":
            tribe_id = form_data["werewolf_tribe_id"]
            auspice_id = form_data.get("werewolf_auspice_id") or None
            werewolf_c = WerewolfAttributesCreate(tribe_id=tribe_id, auspice_id=auspice_id)
            werewolf_u = WerewolfAttributesUpdate(tribe_id=tribe_id, auspice_id=auspice_id)
        case "HUNTER":
            creed = form_data.get("creed") or None
            hunter_c = HunterAttributesCreate(creed=creed)
            hunter_u = HunterAttributesUpdate(creed=creed)
        case "MAGE":
            mage = MageAttributes(
                sphere=form_data.get("sphere") or None,
                tradition=form_data.get("tradition") or None,
            )

    return (vampire_c, werewolf_c, hunter_c, mage), (vampire_u, werewolf_u, hunter_u, mage)
