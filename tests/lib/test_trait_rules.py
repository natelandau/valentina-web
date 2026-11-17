"""Tests for derived-trait rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client.models import CharacterTraitSpecialty
from vweb.api_client.testing import CharacterTraitFactory, TraitFactory
from vweb.lib.trait_rules import (
    accepts_specialties,
    is_derived_trait,
    next_specialty_cost,
    specialty_keep_rating,
    specialty_min_rating,
    specialty_sections_text,
)

if TYPE_CHECKING:
    from vweb.api_client.constants import SpecialtyRules
    from vweb.api_client.models import CharacterTrait


def _character_trait(name: str, custom_for_character_id: str | None = None) -> CharacterTrait:
    trait = TraitFactory.build(name=name, custom_for_character_id=custom_for_character_id)
    return CharacterTraitFactory.build(trait=trait)


@pytest.mark.parametrize("name", ["Willpower", "willpower"])
def test_v5_willpower_is_derived(name: str) -> None:
    """Verify V5 Willpower is derived regardless of name casing."""
    assert is_derived_trait(_character_trait(name), "V5") is True


def test_v4_willpower_is_not_derived() -> None:
    """Verify V4 Willpower is editable."""
    assert is_derived_trait(_character_trait("Willpower"), "V4") is False


def test_custom_willpower_is_not_derived() -> None:
    """Verify a character-owned custom trait named Willpower is editable."""
    assert is_derived_trait(_character_trait("Willpower", "char-1"), "V5") is False


def test_other_trait_is_not_derived() -> None:
    """Verify non-Willpower traits are editable."""
    assert is_derived_trait(_character_trait("Composure"), "V5") is False


def _trait(
    section_name: str | None,
    value: int,
    name: str = "Firearms",
    custom_for_character_id: str | None = None,
) -> CharacterTrait:
    trait = TraitFactory.build(
        sheet_section_name=section_name,
        name=name,
        custom_for_character_id=custom_for_character_id,
    )
    return CharacterTraitFactory.build(trait=trait, value=value)


@pytest.mark.parametrize(
    ("section", "value", "expected"),
    [
        ("Abilities", 1, True),
        ("Abilities", 0, False),
        ("ABILITIES", 2, True),
        ("Attributes", 5, False),
        (None, 3, False),
    ],
)
def test_fixed_cost_accepts_specialties(section: str | None, value: int, *, expected: bool) -> None:
    """Verify FIXED_COST rules accept abilities with at least one dot, matching section case-free."""
    assert accepts_specialties(_trait(section, value), rules="FIXED_COST") is expected


@pytest.mark.parametrize(
    ("section", "name", "value", "favored", "expected"),
    [
        ("Abilities", "Firearms", 3, [], False),
        ("Abilities", "Firearms", 4, [], True),
        ("Abilities", "Medicine", 3, ["Medicine"], True),
        ("Abilities", "medicine", 3, ["MEDICINE"], True),
        ("Attributes", "Strength", 4, [], True),
        ("Attributes", "Strength", 3, ["Strength"], False),
        ("Other", "Courage", 5, [], False),
    ],
)
def test_rating_based_accepts_specialties(
    section: str, name: str, value: int, favored: list[str], *, expected: bool
) -> None:
    """Verify RATING_BASED rules: 4 dots, 3 for favored abilities, attributes and abilities only."""
    trait = _trait(section, value, name=name)
    assert (
        accepts_specialties(trait, rules="RATING_BASED", favored_ability_names=favored) is expected
    )


@pytest.mark.parametrize(
    ("rules", "section", "name", "favored", "expected"),
    [
        ("RATING_BASED", "Abilities", "Medicine", ["Medicine"], 3),
        ("RATING_BASED", "Abilities", "Firearms", ["Medicine"], 4),
        ("RATING_BASED", "Attributes", "Strength", ["Strength"], 4),
        ("RATING_BASED", "Disciplines", "Auspex", [], None),
        ("FIXED_COST", "Abilities", "Medicine", ["Medicine"], 1),
        ("FIXED_COST", "Attributes", "Strength", [], None),
    ],
)
def test_specialty_min_rating(
    rules: SpecialtyRules, section: str, name: str, favored: list[str], expected: int | None
) -> None:
    """Verify the minimum rating per rules, or None for sections that never take specialties."""
    trait = _trait(section, 1, name=name)
    assert specialty_min_rating(trait, rules=rules, favored_ability_names=favored) == expected


def test_custom_trait_is_never_favored() -> None:
    """Verify a custom ability named like a favored one still needs 4 dots, as the API requires."""
    trait = _trait("Abilities", 3, name="Medicine", custom_for_character_id="char-1")
    assert (
        specialty_min_rating(trait, rules="RATING_BASED", favored_ability_names=["Medicine"]) == 4
    )


def _with_specialties(trait: CharacterTrait, count: int) -> CharacterTrait:
    trait.specialties = [
        CharacterTraitSpecialty(
            id=f"sp-{index}",
            name=f"Specialty {index}",
            date_created="2026-01-01T00:00:00Z",
            date_modified="2026-01-01T00:00:00Z",
        )
        for index in range(count)
    ]
    return trait


@pytest.mark.parametrize(
    ("rules", "section", "value", "count", "expected"),
    [
        ("FIXED_COST", "Abilities", 3, 1, 1),
        ("RATING_BASED", "Abilities", 5, 1, 4),
        ("RATING_BASED", "Abilities", 5, 0, 0),
        ("FIXED_COST", "Attributes", 3, 1, 3),
    ],
)
def test_specialty_keep_rating(
    rules: SpecialtyRules, section: str, value: int, count: int, expected: int
) -> None:
    """Verify the rating that keeps specialties: the minimum, 0 without any, the current value when disallowed."""
    trait = _with_specialties(_trait(section, value), count)
    assert specialty_keep_rating(trait, rules=rules) == expected


@pytest.mark.parametrize(
    ("rules", "value", "count", "expected"),
    [
        ("FIXED_COST", 2, 0, 3),
        ("FIXED_COST", 5, 2, 3),
        ("RATING_BASED", 4, 0, 0),
        ("RATING_BASED", 5, 1, 5),
    ],
)
def test_next_specialty_cost(rules: SpecialtyRules, value: int, count: int, expected: int) -> None:
    """Verify FIXED_COST charges 3 and RATING_BASED makes the first free, then charges the rating."""
    trait = _with_specialties(_trait("Abilities", value), count)
    assert next_specialty_cost(trait, rules=rules) == expected


def test_specialty_sections_text() -> None:
    """Verify the message names the sections each rule set allows."""
    assert specialty_sections_text("FIXED_COST") == "abilities"
    assert specialty_sections_text("RATING_BASED") == "attributes and abilities"
