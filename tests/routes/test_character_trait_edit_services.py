"""Tests for character trait edit service helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import (
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CompanyFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
)

from vweb.routes.character_trait_edit.services import (
    find_character_trait,
    specialty_add_label,
    specialty_cost,
)

if TYPE_CHECKING:
    from vclient.constants import TraitModifyCurrency
    from vclient.models import CompanySettings


def _settings(*, enabled: bool) -> CompanySettings:
    settings = CompanyFactory.build().settings
    settings.specialty_xp_cost_enabled = enabled
    return settings


@pytest.mark.parametrize(
    ("spend_type", "enabled", "expected"),
    [
        ("XP", True, 3),
        ("STARTING_POINTS", True, 3),
        ("NO_COST", True, 0),
        ("XP", False, 0),
    ],
)
def test_specialty_cost(spend_type: TraitModifyCurrency, *, enabled: bool, expected: int) -> None:
    """Verify the cost applies only to paid currencies with the setting on."""
    assert specialty_cost(spend_type, _settings(enabled=enabled)) == expected


@pytest.mark.parametrize(
    ("spend_type", "enabled", "expected"),
    [
        ("XP", True, "Add · 3 XP"),
        ("STARTING_POINTS", True, "Add · 3 starting points"),
        ("NO_COST", True, "Add"),
        ("XP", False, "Add"),
    ],
)
def test_specialty_add_label(
    spend_type: TraitModifyCurrency, *, enabled: bool, expected: str
) -> None:
    """Verify the add label carries the cost only when one is charged."""
    assert specialty_add_label(spend_type, _settings(enabled=enabled)) == expected


def test_find_character_trait() -> None:
    """Verify lookup reaches subcategory traits and misses unknown ids."""
    top = CharacterTraitFactory.build(id="ct-top")
    nested = CharacterTraitFactory.build(id="ct-nested")
    sub = FullSheetTraitSubcategoryFactory.build(character_traits=[nested])
    category = FullSheetTraitCategoryFactory.build(character_traits=[top], subcategories=[sub])
    section = FullSheetTraitSectionFactory.build(categories=[category])
    sheet = CharacterFullSheetFactory.build(sections=[section])

    assert find_character_trait(sheet, "ct-nested") is nested
    assert find_character_trait(sheet, "ct-top") is top
    assert find_character_trait(sheet, "nope") is None
