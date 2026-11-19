"""Tests for shared character profile helpers."""

from __future__ import annotations

import pytest

from vweb.api_client.testing import (
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
)
from vweb.lib.character_profile import find_character_trait, iter_character_traits

_TOP = CharacterTraitFactory.build(id="ct-top")
_NESTED = CharacterTraitFactory.build(id="ct-nested")


@pytest.fixture
def sheet():
    """Build a sheet with one category trait and one subcategory trait."""
    sub = FullSheetTraitSubcategoryFactory.build(character_traits=[_NESTED])
    category = FullSheetTraitCategoryFactory.build(character_traits=[_TOP], subcategories=[sub])
    section = FullSheetTraitSectionFactory.build(categories=[category])
    return CharacterFullSheetFactory.build(sections=[section])


def test_iter_character_traits_includes_subcategories(sheet) -> None:
    """Verify iteration yields category traits first, then subcategory traits."""
    assert list(iter_character_traits(sheet)) == [_TOP, _NESTED]


@pytest.mark.parametrize(
    ("trait_id", "expected"),
    [("ct-top", _TOP), ("ct-nested", _NESTED), ("nope", None)],
)
def test_find_character_trait(sheet, trait_id, expected) -> None:
    """Verify lookup reaches category and subcategory traits and returns None when missing."""
    assert find_character_trait(sheet, trait_id) is expected
