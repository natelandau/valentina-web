"""Tests for derived-trait rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client.testing import CharacterTraitFactory, TraitFactory
from vweb.lib.trait_rules import accepts_specialties, is_derived_trait, specialty_threshold

if TYPE_CHECKING:
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


def _ability(section_name: str | None, value: int) -> CharacterTrait:
    trait = TraitFactory.build(sheet_section_name=section_name)
    return CharacterTraitFactory.build(trait=trait, value=value)


def test_ability_at_one_accepts_specialties() -> None:
    """Verify an ability with one dot accepts specialties."""
    assert accepts_specialties(_ability("Abilities", 1)) is True


def test_ability_at_zero_does_not() -> None:
    """Verify an ability with no dots does not."""
    assert accepts_specialties(_ability("Abilities", 0)) is False


def test_section_name_case_insensitive() -> None:
    """Verify the section name match ignores case."""
    assert accepts_specialties(_ability("ABILITIES", 2)) is True


def test_attribute_does_not() -> None:
    """Verify attributes do not accept specialties."""
    assert accepts_specialties(_ability("Attributes", 3)) is False


def test_missing_section_name_does_not() -> None:
    """Verify a trait without a section name does not."""
    assert accepts_specialties(_ability(None, 3)) is False


def _named(section_name: str, name: str, value: int) -> CharacterTrait:
    trait = TraitFactory.build(sheet_section_name=section_name, name=name)
    return CharacterTraitFactory.build(trait=trait, value=value)


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
def test_threshold_rules_accept_specialties(
    section: str, name: str, value: int, favored: list[str], *, expected: bool
) -> None:
    """Verify THRESHOLD rules: 4 dots, 3 for favored abilities, attributes and abilities only."""
    trait = _named(section, name, value)
    assert accepts_specialties(trait, rules="THRESHOLD", favored_ability_names=favored) is expected


@pytest.mark.parametrize(
    ("section", "name", "favored", "expected"),
    [
        ("Abilities", "Medicine", ["Medicine"], 3),
        ("Abilities", "Firearms", ["Medicine"], 4),
        ("Attributes", "Strength", ["Strength"], 4),
    ],
)
def test_threshold_rules_specialty_threshold(
    section: str, name: str, favored: list[str], expected: int
) -> None:
    """Verify the threshold a trait needs under THRESHOLD rules."""
    trait = _named(section, name, 1)
    assert specialty_threshold(trait, rules="THRESHOLD", favored_ability_names=favored) == expected


def test_flat_rules_threshold_is_one() -> None:
    """Verify FLAT rules need only one dot, whatever the concept favors."""
    trait = _named("Abilities", "Medicine", 1)
    assert specialty_threshold(trait, favored_ability_names=["Medicine"]) == 1
