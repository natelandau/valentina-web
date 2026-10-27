"""Rules that classify traits by how the API treats them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from vclient.constants import GameVersion
    from vclient.models import CharacterTrait

DERIVED_V5_TRAIT_NAME: Final = "willpower"
ABILITIES_SECTION_NAME: Final = "abilities"


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


def accepts_specialties(character_trait: CharacterTrait) -> bool:
    """Report whether the trait can carry specialties.

    Only ability traits with at least one dot qualify.

    Args:
        character_trait: The character trait to classify.

    Returns:
        bool: True when specialties can be managed on this trait.
    """
    section_name = character_trait.trait.sheet_section_name
    return (
        section_name is not None
        and section_name.strip().lower() == ABILITIES_SECTION_NAME
        and character_trait.value >= 1
    )
