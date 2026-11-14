"""Shared helpers for reading and editing a character's profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g

from vweb.lib import cache
from vweb.lib.api_errors import USER_FACING_API_ERRORS
from vweb.lib.trait_rules import accepts_specialties, specialty_threshold

if TYPE_CHECKING:
    from collections.abc import Iterator

    from vweb.api_client.constants import SpecialtyRules
    from vweb.api_client.models import Character, CharacterFullSheet, CharacterTrait

TRAIT_API_ERRORS = USER_FACING_API_ERRORS


def iter_character_traits(full_sheet: CharacterFullSheet) -> Iterator[CharacterTrait]:
    """Yield every character trait on a sheet in display order.

    Category traits come before their subcategory traits, so callers that
    keep the first match see the same trait the sheet shows first.
    """
    for section in full_sheet.sections:
        for category in section.categories:
            yield from category.character_traits
            for subcategory in category.subcategories:
                yield from subcategory.character_traits


def find_character_trait(
    full_sheet: CharacterFullSheet, character_trait_id: str
) -> CharacterTrait | None:
    """Find a character trait by id in a full sheet's categories and subcategories."""
    return next(
        (
            character_trait
            for character_trait in iter_character_traits(full_sheet)
            if character_trait.id == character_trait_id
        ),
        None,
    )


def specialty_rules_for(character: Character) -> tuple[SpecialtyRules, list[str]]:
    """Return the company's specialty rules and the character's concept-favored abilities.

    The concept is only looked up under THRESHOLD rules, the only rules that use it.

    Args:
        character: The character whose specialties are being judged.

    Returns:
        tuple[SpecialtyRules, list[str]]: The rules and the favored ability names.
    """
    rules = g.global_context.company.settings.specialty_rules
    if rules != "THRESHOLD":
        return rules, []
    concept = cache.blueprint.concept(character.concept_id)
    return rules, list(concept.favored_ability_names) if concept else []


def character_trait_accepts_specialties(
    character_trait: CharacterTrait, character: Character
) -> bool:
    """Report whether a character's trait can carry specialties under the company's rules."""
    rules, favored = specialty_rules_for(character)
    return accepts_specialties(character_trait, rules=rules, favored_ability_names=favored)


def character_trait_specialty_threshold(
    character_trait: CharacterTrait, character: Character
) -> int:
    """Return the rating a character's trait needs before it can take a specialty."""
    rules, favored = specialty_rules_for(character)
    return specialty_threshold(character_trait, rules=rules, favored_ability_names=favored)
