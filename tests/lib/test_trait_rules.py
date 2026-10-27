"""Tests for derived-trait rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import CharacterTraitFactory, TraitFactory

from vweb.lib.trait_rules import accepts_specialties, is_derived_trait

if TYPE_CHECKING:
    from vclient.models import CharacterTrait


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
