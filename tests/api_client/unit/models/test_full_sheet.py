"""Unit tests for full sheet models."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models.full_sheet import (
    CharacterFullSheet,
    FullSheetTraitCategory,
    FullSheetTraitSection,
    FullSheetTraitSubcategory,
)


class TestFullSheetTraitSubcategory:
    """Tests for FullSheetTraitSubcategory model."""

    def test_minimal_fields(self) -> None:
        """Verify model with minimal required fields."""
        # When: Creating with required fields only
        sub = FullSheetTraitSubcategory(
            id="sub123",
            name="Celerity",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            requires_parent=False,
            character_traits=[],
        )

        # Then: Model is created with correct defaults
        assert sub.name == "Celerity"
        assert sub.description is None
        assert sub.pool is None
        assert sub.system is None
        assert sub.hunter_edge_type is None
        assert sub.character_traits == []

    def test_all_fields(self) -> None:
        """Verify model with all fields populated."""
        # Given: A trait for the subcategory
        trait_data = {
            "id": "ct1",
            "character_id": "char1",
            "value": 3,
            "date_created": "2024-01-01T00:00:00Z",
            "date_modified": "2024-01-01T00:00:00Z",
            "trait": {
                "id": "t1",
                "name": "Celerity",
                "date_created": "2024-01-01T00:00:00Z",
                "date_modified": "2024-01-01T00:00:00Z",
                "sheet_section_id": "sec1",
                "category_id": "cat1",
            },
        }

        # When: Creating with all fields
        sub = FullSheetTraitSubcategory(
            id="sub123",
            name="Celerity",
            description="Speed disciplines",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=False,
            requires_parent=True,
            pool="Dexterity + Athletics",
            system="Adds dots to speed",
            hunter_edge_type="ASSETS",
            character_traits=[trait_data],
        )

        # Then: All fields are set
        assert sub.description == "Speed disciplines"
        assert sub.pool == "Dexterity + Athletics"
        assert sub.hunter_edge_type == "ASSETS"
        assert len(sub.character_traits) == 1
        assert sub.character_traits[0].value == 3

    def test_invalid_hunter_edge_type(self) -> None:
        """Verify hunter_edge_type rejects invalid values."""
        # When/Then: Invalid hunter edge type is rejected
        with pytest.raises(PydanticValidationError):
            FullSheetTraitSubcategory(
                id="sub123",
                name="Test",
                initial_cost=1,
                upgrade_cost=2,
                show_when_empty=True,
                requires_parent=False,
                hunter_edge_type="INVALID",
                character_traits=[],
            )

    def test_available_traits_defaults_to_empty(self) -> None:
        """Verify available_traits defaults to empty list."""
        # When: Creating with required fields only
        sub = FullSheetTraitSubcategory(
            id="sub123",
            name="Celerity",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            requires_parent=False,
            character_traits=[],
        )

        # Then: available_traits is an empty list
        assert sub.available_traits == []

    def test_available_traits_with_traits(self) -> None:
        """Verify available_traits accepts a list of Trait objects."""
        # Given: A trait dict matching the Trait model
        trait_data = {
            "id": "t1",
            "name": "Celerity",
            "date_created": "2024-01-01T00:00:00Z",
            "date_modified": "2024-01-01T00:00:00Z",
            "sheet_section_id": "sec1",
            "category_id": "cat1",
        }

        # When: Creating with available_traits populated
        sub = FullSheetTraitSubcategory(
            id="sub123",
            name="Celerity",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            requires_parent=False,
            character_traits=[],
            available_traits=[trait_data],
        )

        # Then: The trait is parsed correctly
        assert len(sub.available_traits) == 1
        assert sub.available_traits[0].name == "Celerity"


class TestFullSheetTraitCategory:
    """Tests for FullSheetTraitCategory model."""

    def test_minimal_fields(self) -> None:
        """Verify model with minimal required fields."""
        # When: Creating with required fields only
        cat = FullSheetTraitCategory(
            id="cat123",
            name="Disciplines",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            order=1,
            subcategories=[],
            character_traits=[],
        )

        # Then: Model is created correctly
        assert cat.name == "Disciplines"
        assert cat.description is None
        assert cat.subcategories == []
        assert cat.character_traits == []

    def test_available_traits_defaults_to_empty(self) -> None:
        """Verify available_traits defaults to empty list."""
        # When: Creating with required fields only
        cat = FullSheetTraitCategory(
            id="cat123",
            name="Disciplines",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            order=1,
            subcategories=[],
            character_traits=[],
        )

        # Then: available_traits is an empty list
        assert cat.available_traits == []

    def test_available_traits_with_traits(self) -> None:
        """Verify available_traits accepts a list of Trait objects."""
        # Given: A trait dict matching the Trait model
        trait_data = {
            "id": "t1",
            "name": "Potence",
            "date_created": "2024-01-01T00:00:00Z",
            "date_modified": "2024-01-01T00:00:00Z",
            "sheet_section_id": "sec1",
            "category_id": "cat123",
        }

        # When: Creating with available_traits populated
        cat = FullSheetTraitCategory(
            id="cat123",
            name="Disciplines",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            order=1,
            subcategories=[],
            character_traits=[],
            available_traits=[trait_data],
        )

        # Then: The trait is parsed correctly
        assert len(cat.available_traits) == 1
        assert cat.available_traits[0].name == "Potence"

    def test_with_nested_subcategories(self) -> None:
        """Verify model with nested subcategories and traits."""
        # Given: A subcategory with a trait
        sub_data = {
            "id": "sub1",
            "name": "Celerity",
            "initial_cost": 1,
            "upgrade_cost": 2,
            "show_when_empty": True,
            "requires_parent": False,
            "character_traits": [
                {
                    "id": "ct1",
                    "character_id": "char1",
                    "value": 3,
                    "date_created": "2024-01-01T00:00:00Z",
                    "date_modified": "2024-01-01T00:00:00Z",
                    "trait": {
                        "id": "t1",
                        "name": "Celerity",
                        "date_created": "2024-01-01T00:00:00Z",
                        "date_modified": "2024-01-01T00:00:00Z",
                        "sheet_section_id": "sec1",
                        "category_id": "cat1",
                    },
                }
            ],
        }

        # When: Creating a category with a subcategory
        cat = FullSheetTraitCategory(
            id="cat123",
            name="Disciplines",
            initial_cost=1,
            upgrade_cost=2,
            show_when_empty=True,
            order=1,
            subcategories=[sub_data],
            character_traits=[],
        )

        # Then: Nested structure is correct
        assert len(cat.subcategories) == 1
        assert cat.subcategories[0].name == "Celerity"
        assert cat.subcategories[0].character_traits[0].value == 3


class TestFullSheetTraitSection:
    """Tests for FullSheetTraitSection model."""

    def test_minimal_fields(self) -> None:
        """Verify model with minimal required fields."""
        # When: Creating with required fields only
        section = FullSheetTraitSection(
            id="sec123",
            name="Physical",
            order=1,
            show_when_empty=True,
            categories=[],
        )

        # Then: Model is created correctly
        assert section.name == "Physical"
        assert section.description is None
        assert section.categories == []


class TestCharacterFullSheet:
    """Tests for CharacterFullSheet model."""

    def test_full_hierarchy(self) -> None:
        """Verify full nested hierarchy parses from JSON-like data."""
        # Given: A complete full sheet structure
        data = {
            "character": {
                "id": "char1",
                "date_created": "2024-01-15T10:30:00Z",
                "date_modified": "2024-01-15T10:30:00Z",
                "character_class": "VAMPIRE",
                "game_version": "V5",
                "name_first": "Marcus",
                "name_last": "Blackwood",
                "name": "Marcus",
                "name_full": "Marcus Blackwood",
                "user_creator_id": "user1",
                "user_player_id": "user1",
                "company_id": "co1",
                "campaign_id": "camp1",
            },
            "sections": [
                {
                    "id": "sec1",
                    "name": "Physical",
                    "order": 1,
                    "show_when_empty": True,
                    "categories": [
                        {
                            "id": "cat1",
                            "name": "Attributes",
                            "initial_cost": 1,
                            "upgrade_cost": 2,
                            "show_when_empty": True,
                            "order": 1,
                            "subcategories": [],
                            "character_traits": [
                                {
                                    "id": "ct1",
                                    "character_id": "char1",
                                    "value": 3,
                                    "date_created": "2024-01-01T00:00:00Z",
                                    "date_modified": "2024-01-01T00:00:00Z",
                                    "trait": {
                                        "id": "t1",
                                        "name": "Strength",
                                        "date_created": "2024-01-01T00:00:00Z",
                                        "date_modified": "2024-01-01T00:00:00Z",
                                        "sheet_section_id": "sec1",
                                        "category_id": "cat1",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        # When: Parsing the full sheet
        sheet = CharacterFullSheet.model_validate(data)

        # Then: Full hierarchy is correctly parsed
        assert sheet.character.name_first == "Marcus"
        assert len(sheet.sections) == 1
        assert sheet.sections[0].name == "Physical"
        assert len(sheet.sections[0].categories) == 1
        assert sheet.sections[0].categories[0].name == "Attributes"
        assert sheet.sections[0].categories[0].character_traits[0].value == 3
        assert sheet.sections[0].categories[0].character_traits[0].trait.name == "Strength"
