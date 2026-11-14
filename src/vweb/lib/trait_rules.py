"""Rules that classify traits by how the API treats them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vweb.api_client.constants import GameVersion, SpecialtyRules
    from vweb.api_client.models import CharacterTrait

DERIVED_V5_TRAIT_NAME: Final = "willpower"
ABILITIES_SECTION_NAME: Final = "abilities"
ATTRIBUTES_SECTION_NAME: Final = "attributes"
FLAT_SPECIALTY_THRESHOLD: Final = 1
SPECIALTY_THRESHOLD: Final = 4
SPECIALTY_CONCEPT_THRESHOLD: Final = 3


def is_derived_trait(character_trait: CharacterTrait, game_version: GameVersion) -> bool:
    """Report whether the API computes this trait's value, so it must not be edited.

    V5 Willpower is derived from Composure and Resolve. A custom trait that happens to share
    the name is character-owned and stays editable.

    Args:
        character_trait: The character trait to classify.
        game_version: The game version of the owning character.

    Returns:
        bool: True when the trait is read-only.
    """
    trait = character_trait.trait
    return (
        game_version == "V5"
        and trait.custom_for_character_id is None
        and trait.name.strip().lower() == DERIVED_V5_TRAIT_NAME
    )


def _section_name(character_trait: CharacterTrait) -> str:
    section_name = character_trait.trait.sheet_section_name
    return section_name.strip().lower() if section_name else ""


def specialty_sections(rules: SpecialtyRules = "FLAT") -> frozenset[str]:
    """Return the sheet sections whose traits can carry specialties under the rules."""
    if rules == "THRESHOLD":
        return frozenset({ATTRIBUTES_SECTION_NAME, ABILITIES_SECTION_NAME})
    return frozenset({ABILITIES_SECTION_NAME})


def specialty_threshold(
    character_trait: CharacterTrait,
    *,
    rules: SpecialtyRules = "FLAT",
    favored_ability_names: Iterable[str] = (),
) -> int:
    """Return the rating a trait needs before it can take a specialty.

    Under THRESHOLD rules, attributes and abilities need 4 dots, and abilities favored by the
    character's concept need 3. Under FLAT rules any rated ability qualifies.

    Args:
        character_trait: The character trait to classify.
        rules: The company's specialty rules.
        favored_ability_names: Ability names favored by the character's concept.

    Returns:
        int: The minimum value that permits a specialty.
    """
    if rules != "THRESHOLD":
        return FLAT_SPECIALTY_THRESHOLD
    if _section_name(character_trait) == ABILITIES_SECTION_NAME:
        favored = {name.strip().casefold() for name in favored_ability_names}
        if character_trait.trait.name.strip().casefold() in favored:
            return SPECIALTY_CONCEPT_THRESHOLD
    return SPECIALTY_THRESHOLD


def accepts_specialties(
    character_trait: CharacterTrait,
    *,
    rules: SpecialtyRules = "FLAT",
    favored_ability_names: Iterable[str] = (),
) -> bool:
    """Report whether the trait can carry specialties.

    Under FLAT rules, abilities with at least one dot qualify. Under THRESHOLD rules,
    attributes and abilities at their threshold qualify.

    Args:
        character_trait: The character trait to classify.
        rules: The company's specialty rules.
        favored_ability_names: Ability names favored by the character's concept.

    Returns:
        bool: True when specialties can be managed on this trait.
    """
    if _section_name(character_trait) not in specialty_sections(rules):
        return False
    return character_trait.value >= specialty_threshold(
        character_trait, rules=rules, favored_ability_names=favored_ability_names
    )
