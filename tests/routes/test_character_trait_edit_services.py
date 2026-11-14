"""Tests for character trait edit service helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from vweb.api_client.models import CharacterTraitSpecialty
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
    from vweb.api_client.constants import TraitModifyCurrency
    from vweb.api_client.models import Character, CharacterTrait, CompanySettings, Trait


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


def _threshold_settings(*, enabled: bool = True) -> CompanySettings:
    settings = _settings(enabled=enabled)
    settings.specialty_rules = "THRESHOLD"
    return settings


def _medicine(value: int, specialty_count: int) -> CharacterTrait:
    return CharacterTraitFactory.build(
        trait=TraitFactory.build(name="Medicine", sheet_section_name="Abilities"),
        value=value,
        specialties=[
            CharacterTraitSpecialty(
                id=f"spec-{index}",
                name=f"Specialty {index}",
                date_created=datetime.now(UTC),
                date_modified=datetime.now(UTC),
            )
            for index in range(specialty_count)
        ],
    )


@pytest.mark.parametrize(
    ("value", "specialty_count", "spend_type", "expected"),
    [
        (4, 0, "XP", 0),
        (4, 1, "XP", 4),
        (5, 2, "STARTING_POINTS", 5),
        (4, 1, "NO_COST", 0),
    ],
)
def test_threshold_specialty_cost(
    value: int, specialty_count: int, spend_type: TraitModifyCurrency, expected: int
) -> None:
    """Verify THRESHOLD pricing: first free, then the trait's current rating."""
    trait = _medicine(value, specialty_count)
    assert specialty_cost(spend_type, _threshold_settings(), trait) == expected


def test_threshold_specialty_add_label_shows_rating_cost() -> None:
    """Verify the add label shows the rating-based cost."""
    trait = _medicine(4, 1)
    assert specialty_add_label("XP", _threshold_settings(), trait) == "Add · 4 XP"


def test_specialty_rules_text_threshold() -> None:
    """Verify the explanation names the bonus, the threshold, and the pricing."""
    text = specialty_rules_text(_medicine(3, 0), _threshold_settings(), 3)
    assert "adds one die to Medicine" in text
    assert "at 3 dots" in text
    assert "first specialty is free" in text


def test_specialty_rules_text_flat_omits_threshold() -> None:
    """Verify FLAT rules only explain the bonus."""
    text = specialty_rules_text(_medicine(1, 0), _settings(enabled=True), 1)
    assert "adds one die to Medicine" in text
    assert "dots" not in text


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
