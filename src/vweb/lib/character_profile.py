"""Shared helpers for reading and editing a character's profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from flask import g

from vweb.lib import cache
from vweb.lib.api_errors import USER_FACING_API_ERRORS
from vweb.lib.trait_rules import (
    accepts_specialties,
    specialty_keep_rating,
    specialty_min_rating,
)

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


class SpecialtyRuleContext(NamedTuple):
    """The company's specialty rules and the abilities a character's concept favors."""

    rules: SpecialtyRules
    favored_ability_names: frozenset[str]


def specialty_rule_context(character: Character) -> SpecialtyRuleContext:
    """Return the specialty rules that judge a character's traits, resolved once per request.

    A sheet asks once per trait, so the result is memoized on `g` to avoid a concept cache
    read for every row. The concept is only looked up under RATING_BASED rules, the only rules
    that use it.

    Args:
        character: The character whose traits are judged.

    Returns:
        SpecialtyRuleContext: The rules and the concept's favored ability names.
    """
    memo: dict[str, SpecialtyRuleContext] = g.setdefault("_specialty_rule_context", {})
    if character.id not in memo:
        rules = g.global_context.company.settings.specialty_rules
        concept = cache.blueprint.concept(character.concept_id) if rules == "RATING_BASED" else None
        favored = frozenset(concept.favored_ability_names) if concept else frozenset()
        memo[character.id] = SpecialtyRuleContext(rules=rules, favored_ability_names=favored)
    return memo[character.id]


def character_trait_specialty_min_rating(
    character_trait: CharacterTrait, character: Character
) -> int | None:
    """Return the rating a character's trait needs for specialties under the company's rules.

    Returns:
        int | None: The minimum rating, or None when the trait's section never takes specialties.
    """
    context = specialty_rule_context(character)
    return specialty_min_rating(
        character_trait,
        rules=context.rules,
        favored_ability_names=context.favored_ability_names,
    )


def character_trait_accepts_specialties(
    character_trait: CharacterTrait, character: Character
) -> bool:
    """Report whether a character's trait can take a specialty under the company's rules."""
    context = specialty_rule_context(character)
    return accepts_specialties(
        character_trait,
        rules=context.rules,
        favored_ability_names=context.favored_ability_names,
    )


def character_trait_specialty_keep_rating(
    character_trait: CharacterTrait, character: Character
) -> int:
    """Return the lowest rating at which a character's trait keeps its specialties.

    Returns:
        int: The rating, 0 when the trait has no specialties to lose.
    """
    context = specialty_rule_context(character)
    return specialty_keep_rating(
        character_trait,
        rules=context.rules,
        favored_ability_names=context.favored_ability_names,
    )
