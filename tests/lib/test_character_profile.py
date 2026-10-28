"""Tests for shared character profile helpers."""

from __future__ import annotations

from vclient.testing import (
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
)

from vweb.lib.character_profile import find_character_trait, iter_character_traits


def test_iter_character_traits_includes_subcategories() -> None:
    """Verify iteration yields category traits first, then subcategory traits."""
    top = CharacterTraitFactory.build(id="ct-top")
    nested = CharacterTraitFactory.build(id="ct-nested")
    sub = FullSheetTraitSubcategoryFactory.build(character_traits=[nested])
    category = FullSheetTraitCategoryFactory.build(character_traits=[top], subcategories=[sub])
    section = FullSheetTraitSectionFactory.build(categories=[category])
    sheet = CharacterFullSheetFactory.build(sections=[section])

    assert list(iter_character_traits(sheet)) == [top, nested]


def test_find_character_trait_returns_none_when_missing() -> None:
    """Verify lookup returns None for an id that is not on the sheet."""
    top = CharacterTraitFactory.build(id="ct-top")
    category = FullSheetTraitCategoryFactory.build(character_traits=[top], subcategories=[])
    section = FullSheetTraitSectionFactory.build(categories=[category])
    sheet = CharacterFullSheetFactory.build(sections=[section])

    assert find_character_trait(sheet, "nope") is None
    assert find_character_trait(sheet, "ct-top") is top


def test_find_character_trait_reaches_subcategory_traits() -> None:
    """Verify lookup finds a trait nested in a subcategory as well as a category trait."""
    top = CharacterTraitFactory.build(id="ct-top")
    nested = CharacterTraitFactory.build(id="ct-nested")
    sub = FullSheetTraitSubcategoryFactory.build(character_traits=[nested])
    category = FullSheetTraitCategoryFactory.build(character_traits=[top], subcategories=[sub])
    section = FullSheetTraitSectionFactory.build(categories=[category])
    sheet = CharacterFullSheetFactory.build(sections=[section])

    assert find_character_trait(sheet, "ct-nested") is nested
    assert find_character_trait(sheet, "ct-top") is top
