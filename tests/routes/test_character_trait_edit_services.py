"""Tests for character trait edit service helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import build_specialty
from vweb.api_client.testing import (
    CharacterFactory,
    CharacterTraitFactory,
    CompanyFactory,
    TraitFactory,
)
from vweb.routes.character_trait_edit.services import (
    find_standard_trait_by_name,
    specialty_add_label,
    specialty_cost,
    specialty_rules_text,
)

if TYPE_CHECKING:
    from vweb.api_client.constants import SpecialtyRules, TraitModifyCurrency
    from vweb.api_client.models import Character, CharacterTrait, CompanySettings, Trait


def _settings(*, enabled: bool) -> CompanySettings:
    settings = CompanyFactory.build().settings
    settings.specialty_xp_cost_enabled = enabled
    return settings


def _rating_based_settings(*, enabled: bool = True) -> CompanySettings:
    settings = _settings(enabled=enabled)
    settings.specialty_rules = "RATING_BASED"
    return settings


def _medicine(value: int, specialty_count: int) -> CharacterTrait:
    return CharacterTraitFactory.build(
        trait=TraitFactory.build(name="Medicine", sheet_section_name="Abilities"),
        value=value,
        specialties=[
            build_specialty(f"spec-{index}", f"Specialty {index}")
            for index in range(specialty_count)
        ],
    )


@pytest.mark.parametrize(
    ("rules", "value", "specialty_count", "spend_type", "enabled", "expected"),
    [
        ("FIXED_COST", 2, 1, "XP", True, 3),
        ("FIXED_COST", 2, 1, "STARTING_POINTS", True, 3),
        ("FIXED_COST", 2, 1, "NO_COST", True, 0),
        ("FIXED_COST", 2, 1, "XP", False, 0),
        ("RATING_BASED", 4, 0, "XP", True, 0),
        ("RATING_BASED", 4, 1, "XP", True, 4),
        ("RATING_BASED", 5, 2, "STARTING_POINTS", True, 5),
        ("RATING_BASED", 4, 1, "NO_COST", True, 0),
        ("RATING_BASED", 4, 1, "XP", False, 0),
    ],
)
def test_specialty_cost(
    rules: SpecialtyRules,
    value: int,
    specialty_count: int,
    spend_type: TraitModifyCurrency,
    *,
    enabled: bool,
    expected: int,
) -> None:
    """Verify FIXED_COST charges 3 and RATING_BASED charges the rating after the first free one.

    Neither charges for NO_COST or with the setting off.
    """
    settings = _settings(enabled=enabled)
    settings.specialty_rules = rules
    assert specialty_cost(spend_type, settings, _medicine(value, specialty_count)) == expected


@pytest.mark.parametrize(
    ("settings", "spend_type", "expected"),
    [
        (_settings(enabled=True), "XP", "Add · 3 XP"),
        (_settings(enabled=True), "STARTING_POINTS", "Add · 3 starting points"),
        (_settings(enabled=True), "NO_COST", "Add"),
        (_settings(enabled=False), "XP", "Add"),
        (_rating_based_settings(), "XP", "Add · 4 XP"),
    ],
    ids=["xp", "starting-points", "no-cost", "cost-disabled", "rating-based"],
)
def test_specialty_add_label(
    settings: CompanySettings, spend_type: TraitModifyCurrency, expected: str
) -> None:
    """Verify the add label carries the cost and currency only when one is charged."""
    assert specialty_add_label(spend_type, settings, _medicine(4, 1)) == expected


@pytest.mark.parametrize(
    ("settings", "included", "excluded"),
    [
        (_rating_based_settings(), ["Medicine", "3 dots", "free"], []),
        (_rating_based_settings(enabled=False), ["Medicine", "3 dots"], ["free"]),
        (_settings(enabled=True), ["Medicine"], ["dots"]),
    ],
    ids=["rating-based-with-cost", "rating-based-free", "fixed-cost"],
)
def test_specialty_rules_text(
    settings: CompanySettings, included: list[str], excluded: list[str]
) -> None:
    """Verify the explanation covers the minimum rating and pricing only when they apply."""
    text = specialty_rules_text(_medicine(3, 0), settings, 3)
    assert all(part in text for part in included)
    assert not any(part in text for part in excluded)


class TestFindStandardTraitByName:
    """Match a typed name to a standard trait, preferring the typed category."""

    def _trait(self, **kwargs: object) -> Trait:
        defaults = {
            "name": "Linguistics",
            "category_id": "mental",
            "sheet_section_id": "abilities",
            "custom_for_character_id": None,
            "game_versions": ["V5"],
            "character_classes": ["VAMPIRE"],
        }
        return TraitFactory.build(**(defaults | kwargs))

    def _character(self) -> Character:
        return CharacterFactory.build(game_version="V5", character_class="VAMPIRE")

    def test_find_standard_trait_by_name_ignores_case_and_whitespace(self) -> None:
        """Verify a name typed in another case with padding still matches."""
        # Given a standard trait for another game version
        trait = self._trait(game_versions=["V4"])

        # When searching with a differently cased name
        found = find_standard_trait_by_name(
            [trait], name="  LINGUISTICS ", category_id="mental", character=self._character()
        )

        # Then the trait is found despite the version mismatch
        assert found is trait

    @pytest.mark.parametrize(
        "overrides",
        [
            {"custom_for_character_id": "other-char"},
            {"name": "Lingo"},
        ],
    )
    def test_find_standard_trait_by_name_no_match(self, overrides: dict[str, str]) -> None:
        """Verify custom traits and other names never match."""
        # Given a trait that differs from the request in one way
        trait = self._trait(**overrides)

        # When searching
        found = find_standard_trait_by_name(
            [trait], name="Linguistics", category_id="mental", character=self._character()
        )

        # Then nothing matches
        assert found is None

    def test_find_standard_trait_by_name_matches_other_category(self) -> None:
        """Verify a trait in another category matches when the typed category has none."""
        # Given a same-named trait only in another category
        merit = self._trait(category_id="merits")

        # When searching from the mental category
        found = find_standard_trait_by_name(
            [merit], name="Linguistics", category_id="mental", character=self._character()
        )

        # Then the trait in the other category is found
        assert found is merit

    def test_find_standard_trait_by_name_prefers_typed_section(self) -> None:
        """Verify a trait in the typed category's section wins over a better fit elsewhere."""
        # Given an off-version ability in Mental, a V5 merit in another section, and a
        # Physical trait that places the typed category in the abilities section
        ability = self._trait(game_versions=["V4"])
        merit = self._trait(category_id="merits", sheet_section_id="advantages")
        physical = self._trait(name="Athletics", category_id="physical")

        # When typing the name into the physical category
        found = find_standard_trait_by_name(
            [merit, ability, physical],
            name="Linguistics",
            category_id="physical",
            character=self._character(),
        )

        # Then the ability in the same section is chosen over the merit
        assert found is ability

    def test_find_standard_trait_by_name_prefers_typed_category(self) -> None:
        """Verify a trait in the typed category wins even when another fits the character better."""
        # Given an exact-fit trait elsewhere and an off-version trait in the typed category
        merit = self._trait(category_id="merits")
        ability = self._trait(game_versions=["V4"])

        # When searching from the mental category
        found = find_standard_trait_by_name(
            [merit, ability], name="Linguistics", category_id="mental", character=self._character()
        )

        # Then the trait in the typed category is chosen
        assert found is ability

    def test_find_standard_trait_by_name_prefers_character_version_and_class(self) -> None:
        """Verify a trait for the character's version and class wins over others."""
        # Given same-named traits for other versions and classes, plus an exact fit
        other_version = self._trait(game_versions=["V4"])
        other_class = self._trait(character_classes=["WEREWOLF"])
        exact = self._trait()

        # When searching
        found = find_standard_trait_by_name(
            [other_version, other_class, exact],
            name="Linguistics",
            category_id="mental",
            character=self._character(),
        )

        # Then the exact fit is chosen
        assert found is exact
