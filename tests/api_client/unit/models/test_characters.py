"""Unit tests for character models."""

from __future__ import annotations

from datetime import date
from typing import get_args

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models import (
    Character,
    CharacterCreate,
    CharacterDetail,
    CharacterUpdate,
    Health,
    HealthLevel,
    HealthStateSet,
    HunterAttributes,
    MageAttributes,
    VampireAttributes,
    WerewolfAttributes,
)
from vweb.api_client.models.character_trait import CharacterCreateTraitAssign, TrackerStateSet


class TestCharacter:
    """Tests for Character response model."""

    def test_character_minimal_fields(self) -> None:
        """Verify Character model with minimal required fields."""
        # When: Creating a character with required fields only
        character = Character(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            user_creator_id="user123",
            user_player_id="user456",
            company_id="company123",
            campaign_id="campaign123",
        )

        # Then: Character is created with defaults
        assert character.character_class == "VAMPIRE"
        assert character.game_version == "V5"
        assert character.name_first == "John"
        assert character.name_last == "Doe"
        assert character.type == "PLAYER"
        assert character.status == "ALIVE"
        assert character.starting_points == 0
        assert character.is_temporary is False
        assert character.date_of_birth is None
        assert character.asset_ids == []
        assert character.character_trait_ids == []
        assert character.chapter_ids == []
        assert character.specialties == []

    def test_character_null_user_ids(self) -> None:
        """Verify Character model accepts null user_creator_id and user_player_id."""
        # When: Creating a character without creator or player IDs
        character = Character(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            company_id="company123",
            campaign_id="campaign123",
        )

        # Then: The user ID fields default to None
        assert character.user_creator_id is None
        assert character.user_player_id is None

    def test_character_all_fields(self) -> None:
        """Verify Character model with all fields populated."""
        # Given: Complete character data
        data = {
            "id": "char123",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "date_killed": None,
            "character_class": "WEREWOLF",
            "type": "NPC",
            "game_version": "V4",
            "status": "ALIVE",
            "starting_points": 15,
            "name_first": "Jane",
            "name_last": "Smith",
            "name_nick": "Wolf",
            "name": "Wolf",
            "name_full": "Jane Smith",
            "age": 28,
            "date_of_birth": "1888-06-15",
            "biography": "A fierce warrior of the pack.",
            "demeanor": "Aggressive",
            "nature": "Protector",
            "concept_id": "concept456",
            "user_creator_id": "user123",
            "user_player_id": "user789",
            "company_id": "company123",
            "campaign_id": "campaign123",
            "asset_ids": ["asset1", "asset2"],
            "character_trait_ids": ["trait1"],
            "specialties": [
                {
                    "id": "spec1",
                    "name": "Brawl: Claws",
                    "type": "ACTION",
                    "description": "Skilled with claws",
                }
            ],
            "is_temporary": True,
            "vampire_attributes": None,
            "werewolf_attributes": {
                "tribe_id": "tribe123",
                "tribe_name": "Glass Walkers",
                "auspice_id": "auspice123",
                "auspice_name": "Ahroun",
                "pack_name": "Urban Hunters",
            },
            "mage_attributes": None,
            "hunter_attributes": None,
        }

        # When: Creating a character from data
        character = Character.model_validate(data)

        # Then: All fields are correctly parsed
        assert character.id == "char123"
        assert character.character_class == "WEREWOLF"
        assert character.type == "NPC"
        assert character.game_version == "V4"
        assert character.name_first == "Jane"
        assert character.age == 28
        assert character.date_of_birth == date(1888, 6, 15)
        assert character.is_temporary is True
        assert character.werewolf_attributes is not None
        assert character.werewolf_attributes.tribe_name == "Glass Walkers"
        assert len(character.specialties) == 1
        assert character.specialties[0].name == "Brawl: Claws"

    def test_character_class_validation(self) -> None:
        """Verify character_class only accepts valid values."""
        # When/Then: Invalid character class is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            Character(
                character_class="INVALID",  # type: ignore[arg-type]
                game_version="V5",
                name_first="John",
                name_last="Doe",
                name="Johnny",
                name_full="John Doe",
                user_creator_id="user123",
                user_player_id="user456",
                company_id="company123",
                campaign_id="campaign123",
            )

        assert "character_class" in str(exc_info.value)

    def test_character_type_validation(self) -> None:
        """Verify type only accepts valid values."""
        # When/Then: Invalid type is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            Character(
                character_class="VAMPIRE",
                type="INVALID",  # type: ignore[arg-type]
                game_version="V5",
                name_first="John",
                name_last="Doe",
                name="Johnny",
                name_full="John Doe",
                user_creator_id="user123",
                user_player_id="user456",
                company_id="company123",
                campaign_id="campaign123",
            )

        assert "type" in str(exc_info.value)

    def test_character_game_version_validation(self) -> None:
        """Verify game_version only accepts V4 or V5."""
        # When/Then: Invalid game version is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            Character(
                character_class="VAMPIRE",
                game_version="V3",  # type: ignore[arg-type]
                name_first="John",
                name_last="Doe",
                name="Johnny",
                name_full="John Doe",
                user_creator_id="user123",
                user_player_id="user456",
                company_id="company123",
                campaign_id="campaign123",
            )

        assert "game_version" in str(exc_info.value)

    def test_character_status_validation(self) -> None:
        """Verify status only accepts ALIVE or DEAD."""
        # When/Then: Invalid status is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            Character(
                character_class="VAMPIRE",
                game_version="V5",
                status="UNDEAD",  # type: ignore[arg-type]
                name_first="John",
                name_last="Doe",
                name="Johnny",
                name_full="John Doe",
                user_creator_id="user123",
                user_player_id="user456",
                company_id="company123",
                campaign_id="campaign123",
            )

        assert "status" in str(exc_info.value)

    def test_child_resource_counts(self) -> None:
        """Verify child-resource count fields default to 0 and accept values."""
        # Given: Minimal valid Character kwargs
        base_kwargs = {
            "id": "char123",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "character_class": "VAMPIRE",
            "game_version": "V5",
            "name_first": "John",
            "name_last": "Doe",
            "name": "Johnny",
            "name_full": "John Doe",
            "company_id": "company123",
            "campaign_id": "campaign123",
        }

        # When: Creating a character with no count values
        defaults = Character(**base_kwargs)

        # Then: Count fields default to 0
        assert defaults.num_inventory_items == 0
        assert defaults.num_notes == 0
        assert defaults.num_assets == 0

        # When: Creating a character with explicit count values
        populated = Character(**base_kwargs, num_inventory_items=3, num_notes=2, num_assets=4)

        # Then: Count fields reflect the provided values
        assert populated.num_inventory_items == 3
        assert populated.num_notes == 2
        assert populated.num_assets == 4

    def test_chapter_ids_defaults_to_empty_list(self) -> None:
        """Verify chapter_ids defaults to an empty list when not provided."""
        # When: Creating a character without chapter_ids
        character = Character(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            company_id="company123",
            campaign_id="campaign123",
        )

        # Then: chapter_ids defaults to an empty list
        assert character.chapter_ids == []

    def test_chapter_ids_round_trip(self) -> None:
        """Verify chapter_ids round-trips correctly when provided."""
        # Given: A list of chapter IDs
        chapter_ids = ["chap1", "chap2"]

        # When: Creating a character with chapter_ids
        character = Character(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            company_id="company123",
            campaign_id="campaign123",
            chapter_ids=chapter_ids,
        )

        # Then: chapter_ids is preserved
        assert character.chapter_ids == ["chap1", "chap2"]

    def test_chapter_ids_not_accepted_on_create(self) -> None:
        """Verify chapter_ids is not a field on CharacterCreate."""
        # When/Then: chapter_ids is absent from CharacterCreate.model_fields
        assert "chapter_ids" not in CharacterCreate.model_fields

    def test_chapter_ids_not_accepted_on_update(self) -> None:
        """Verify chapter_ids is not a field on CharacterUpdate."""
        # When/Then: chapter_ids is absent from CharacterUpdate.model_fields
        assert "chapter_ids" not in CharacterUpdate.model_fields


class TestCharacterCreate:
    """Tests for CharacterCreate model."""

    def test_create_request_minimal(self) -> None:
        """Verify CharacterCreate with required fields only."""
        # When: Creating a request with required fields
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
        )

        # Then: Request is created with correct values
        assert request.campaign_id == "campaign123"
        assert request.character_class == "VAMPIRE"
        assert request.game_version == "V5"
        assert request.name_first == "John"
        assert request.name_last == "Doe"
        assert request.is_temporary is False
        assert request.type is None
        assert request.age is None

    def test_create_request_all_fields(self) -> None:
        """Verify CharacterCreate with all fields."""
        # Given: Traits to assign
        from vweb.api_client.models.character_trait import CharacterCreateTraitAssign

        traits = [CharacterCreateTraitAssign(trait_id="trait123", value=3)]

        # When: Creating a request with all fields
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="WEREWOLF",
            game_version="V4",
            name_first="Jane",
            name_last="Smith",
            type="NPC",
            name_nick="Wolf",
            age=28,
            date_of_birth=date(1888, 6, 15),
            biography="A fierce warrior.",
            demeanor="Aggressive",
            nature="Protector",
            concept_id="concept123",
            user_player_id="user456",
            is_temporary=True,
            traits=traits,
        )

        # Then: All fields are set correctly
        assert request.character_class == "WEREWOLF"
        assert request.is_temporary is True
        assert request.type == "NPC"
        assert request.name_nick == "Wolf"
        assert request.age == 28
        assert request.date_of_birth == date(1888, 6, 15)
        assert request.traits == traits

    def test_create_request_name_first_min_length(self) -> None:
        """Verify name_first requires minimum 3 characters."""
        # When/Then: Short first name is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            CharacterCreate(
                campaign_id="campaign123",
                character_class="VAMPIRE",
                game_version="V5",
                name_first="Jo",  # Too short
                name_last="Doe",
            )

        assert "name_first" in str(exc_info.value)

    def test_create_request_name_last_min_length(self) -> None:
        """Verify name_last requires minimum 3 characters."""
        # When/Then: Short last name is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            CharacterCreate(
                campaign_id="campaign123",
                character_class="VAMPIRE",
                game_version="V5",
                name_first="John",
                name_last="Do",  # Too short
            )

        assert "name_last" in str(exc_info.value)

    def test_create_request_model_dump_excludes_none(self) -> None:
        """Verify model_dump with exclude_none excludes unset optional fields."""
        # Given: A request with only required fields
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
        )

        # When: Dumping with exclude_none
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only required fields are in the output
        assert data == {
            "campaign_id": "campaign123",
            "character_class": "VAMPIRE",
            "game_version": "V5",
            "name_first": "John",
            "name_last": "Doe",
        }

    def test_create_date_of_birth_accepts_iso_string(self) -> None:
        """Verify date_of_birth parses an ISO 8601 calendar date string."""
        # When: Creating a request with an ISO date string
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            date_of_birth="1888-06-15",  # type: ignore[arg-type]
        )

        # Then: The value is parsed as a date
        assert request.date_of_birth == date(1888, 6, 15)

    def test_create_date_of_birth_rejects_non_date(self) -> None:
        """Verify date_of_birth rejects a value that is not a calendar date."""
        # When/Then: A non-date value is rejected
        with pytest.raises(PydanticValidationError):
            CharacterCreate(
                campaign_id="campaign123",
                character_class="VAMPIRE",
                game_version="V5",
                name_first="John",
                name_last="Doe",
                date_of_birth="not-a-date",  # type: ignore[arg-type]
            )


class TestCharacterUpdate:
    """Tests for CharacterUpdate model."""

    def test_update_request_empty(self) -> None:
        """Verify CharacterUpdate with no fields."""
        # When: Creating an empty update request
        request = CharacterUpdate()

        # Then: All fields are None
        assert request.character_class is None
        assert request.is_temporary is None
        assert request.name_first is None
        assert request.status is None

    def test_update_request_partial(self) -> None:
        """Verify CharacterUpdate with partial fields."""
        # When: Creating an update request with some fields
        request = CharacterUpdate(
            name_first="Jane",
            status="DEAD",
            is_temporary=True,
        )

        # Then: Only specified fields are set
        assert request.name_first == "Jane"
        assert request.status == "DEAD"
        assert request.is_temporary is True
        assert request.name_last is None
        assert request.character_class is None

    def test_update_request_model_dump_excludes_unset(self) -> None:
        """Verify model_dump with exclude_unset only includes set fields."""
        # Given: An update request with partial fields
        request = CharacterUpdate(
            name_first="Jane",
        )

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only the set field is in the output
        assert data == {"name_first": "Jane"}

    def test_update_request_name_first_min_length(self) -> None:
        """Verify name_first requires minimum 3 characters when provided."""
        # When/Then: Short first name is rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            CharacterUpdate(name_first="Jo")  # Too short

        assert "name_first" in str(exc_info.value)

    def test_update_explicit_none_for_constrained_fields(self) -> None:
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for all constrained string fields
        request = CharacterUpdate(
            name_first=None,
            name_last=None,
            name_nick=None,
            biography=None,
            demeanor=None,
            nature=None,
        )

        # Then: All fields are None without validation errors
        assert request.name_first is None
        assert request.name_last is None
        assert request.name_nick is None
        assert request.biography is None
        assert request.demeanor is None
        assert request.nature is None

    def test_update_constrained_fields_still_validate_non_none(self) -> None:
        """Verify constraints still apply when a non-None value is provided."""
        # When/Then: Short values are rejected for each constrained field
        with pytest.raises(PydanticValidationError):
            CharacterUpdate(name_last="ab")

        with pytest.raises(PydanticValidationError):
            CharacterUpdate(name_nick="ab")

        with pytest.raises(PydanticValidationError):
            CharacterUpdate(biography="ab")

        with pytest.raises(PydanticValidationError):
            CharacterUpdate(demeanor="ab")

        with pytest.raises(PydanticValidationError):
            CharacterUpdate(nature="ab")

    def test_update_date_of_birth_serializes_to_iso_string(self) -> None:
        """Verify date_of_birth serializes to an ISO 8601 date string in JSON mode."""
        # Given: An update request setting date_of_birth
        request = CharacterUpdate(date_of_birth=date(1888, 6, 15))

        # When: Dumping in JSON mode
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: The date is serialized as an ISO string
        assert data == {"date_of_birth": "1888-06-15"}

    def test_update_date_of_birth_none_tracked_as_set(self) -> None:
        """Verify an explicit None date_of_birth is recorded so the service can clear it."""
        # Given: An update request explicitly clearing date_of_birth
        # exclude_none drops the None, but model_fields_set lets the service re-add an explicit
        # null to the payload to clear the field. See CharactersService.update.
        request = CharacterUpdate(date_of_birth=None)

        # Then: The field is tracked as set even though its value is None
        assert "date_of_birth" in request.model_fields_set
        assert request.date_of_birth is None

    def test_update_date_of_birth_rejects_non_date_when_provided(self) -> None:
        """Verify date_of_birth validation still applies on update."""
        # When/Then: A non-date value is rejected
        with pytest.raises(PydanticValidationError):
            CharacterUpdate(date_of_birth="not-a-date")  # type: ignore[arg-type]


class TestCharacterCreateConstraints:
    """Tests for CharacterCreate optional field constraint handling."""

    def test_create_explicit_none_for_optional_constrained_fields(self) -> None:
        """Verify explicitly passing None for optional constrained fields does not raise."""
        # When: Creating a request with None for optional constrained fields
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name_nick=None,
            biography=None,
            demeanor=None,
            nature=None,
        )

        # Then: Optional fields are None without validation errors
        assert request.name_nick is None
        assert request.biography is None
        assert request.demeanor is None
        assert request.nature is None


class TestVampireAttributes:
    """Tests for VampireAttributes model."""

    def test_vampire_attributes_empty(self) -> None:
        """Verify VampireAttributes with no fields."""
        # When: Creating empty vampire attributes
        attrs = VampireAttributes()

        # Then: All fields are None
        assert attrs.clan_id is None
        assert attrs.clan_name is None
        assert attrs.generation is None
        assert attrs.sire is None

    def test_vampire_attributes_full(self) -> None:
        """Verify VampireAttributes with all fields."""
        # When: Creating full vampire attributes
        attrs = VampireAttributes(
            clan_id="clan123",
            clan_name="Ventrue",
            generation=10,
            sire="Ancient One",
            bane_name="Rarefied Tastes",
            bane_description="Feeds only on specific blood",
            compulsion_name="Domineering",
            compulsion_description="Must be in control",
        )

        # Then: All fields are set
        assert attrs.clan_name == "Ventrue"
        assert attrs.generation == 10
        assert attrs.bane_name == "Rarefied Tastes"


class TestWerewolfAttributes:
    """Tests for WerewolfAttributes model."""

    def test_werewolf_attributes_full(self) -> None:
        """Verify WerewolfAttributes with all fields."""
        # When: Creating full werewolf attributes
        attrs = WerewolfAttributes(
            tribe_id="tribe123",
            tribe_name="Glass Walkers",
            auspice_id="auspice123",
            auspice_name="Ahroun",
            pack_name="Urban Hunters",
        )

        # Then: All fields are set
        assert attrs.tribe_name == "Glass Walkers"
        assert attrs.auspice_name == "Ahroun"
        assert attrs.pack_name == "Urban Hunters"


class TestHunterAttributes:
    """Tests for HunterAttributes model."""

    def test_hunter_attributes_with_creed(self) -> None:
        """Verify HunterAttributes with creed."""
        # When: Creating hunter attributes with creed
        attrs = HunterAttributes(creed="Defender")

        # Then: Creed is set correctly
        assert attrs.creed == "Defender"


class TestMageAttributes:
    """Tests for MageAttributes model."""

    def test_mage_attributes(self) -> None:
        """Verify MageAttributes model."""
        # When: Creating mage attributes
        attrs = MageAttributes(sphere="Forces")

        # Then: Field is set
        assert attrs.sphere == "Forces"


class TestCharacterDetail:
    """Tests for CharacterDetail response model."""

    def test_character_detail_without_includes(self) -> None:
        """Verify CharacterDetail works identically to Character when no includes are present."""
        # Given: Standard character data with no embedded resources
        detail = CharacterDetail(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            user_creator_id="user123",
            user_player_id="user456",
            company_id="company123",
            campaign_id="campaign123",
        )

        # Then: Embedded fields default to None
        assert detail.traits is None
        assert detail.inventory is None
        assert detail.notes is None
        assert detail.assets is None

        # Then: It is a subclass of Character
        assert isinstance(detail, Character)

    def test_character_detail_with_all_includes(self) -> None:
        """Verify CharacterDetail accepts embedded child resources."""
        # Given: Character data with all embedded resources
        detail = CharacterDetail(
            id="char123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            name="Johnny",
            name_full="John Doe",
            user_creator_id="user123",
            user_player_id="user456",
            company_id="company123",
            campaign_id="campaign123",
            traits=[
                {
                    "id": "ct1",
                    "character_id": "char123",
                    "value": 3,
                    "trait": {
                        "id": "t1",
                        "name": "Strength",
                        "date_created": "2024-01-15T10:30:00Z",
                        "date_modified": "2024-01-15T10:30:00Z",
                        "max_value": 5,
                        "min_value": 0,
                        "show_when_zero": True,
                        "sheet_section_id": "sec1",
                        "category_id": "cat1",
                        "is_rollable": True,
                        "character_classes": ["VAMPIRE"],
                        "game_versions": ["V5"],
                    },
                }
            ],
            inventory=[
                {
                    "id": "item1",
                    "character_id": "char123",
                    "name": "Silver Knife",
                    "type": "WEAPON",
                    "date_created": "2024-01-15T10:30:00Z",
                    "date_modified": "2024-01-15T10:30:00Z",
                }
            ],
            notes=[
                {
                    "id": "note1",
                    "date_created": "2024-01-15T10:30:00Z",
                    "date_modified": "2024-01-15T10:30:00Z",
                    "title": "Session Log",
                    "content": "Met the prince.",
                }
            ],
            assets=[
                {
                    "id": "asset1",
                    "date_created": "2024-01-15T10:30:00Z",
                    "date_modified": "2024-01-15T10:30:00Z",
                    "asset_type": "image",
                    "mime_type": "image/png",
                    "original_filename": "portrait.png",
                    "public_url": "https://example.com/portrait.png",
                    "uploaded_by_id": "user123",
                    "company_id": "company123",
                }
            ],
        )

        # Then: Embedded resources are populated
        assert len(detail.traits) == 1
        assert detail.traits[0].trait.name == "Strength"
        assert len(detail.inventory) == 1
        assert detail.inventory[0].name == "Silver Knife"
        assert len(detail.notes) == 1
        assert detail.notes[0].title == "Session Log"
        assert len(detail.assets) == 1
        assert detail.assets[0].original_filename == "portrait.png"

    def test_character_detail_from_json_missing_keys(self) -> None:
        """Verify CharacterDetail handles absent embedded keys from JSON."""
        # Given: JSON response with no embedded resource keys
        data = {
            "id": "char123",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "character_class": "VAMPIRE",
            "game_version": "V5",
            "name_first": "John",
            "name_last": "Doe",
            "name": "Johnny",
            "name_full": "John Doe",
            "user_creator_id": "user123",
            "user_player_id": "user456",
            "company_id": "company123",
            "campaign_id": "campaign123",
        }

        # When: Validating from raw JSON
        detail = CharacterDetail.model_validate(data)

        # Then: Embedded fields are None
        assert detail.traits is None
        assert detail.inventory is None
        assert detail.notes is None
        assert detail.assets is None


class TestCharacterInclude:
    """Tests for CharacterInclude Literal type."""

    def test_character_include_valid_values(self) -> None:
        """Verify CharacterInclude contains the expected literal values."""
        # Given: The expected include values
        from vweb.api_client.constants import CharacterInclude

        expected = {"traits", "inventory", "notes", "assets"}

        # When: Extracting the Literal args
        actual = set(get_args(CharacterInclude))

        # Then: They match exactly
        assert actual == expected


def _character_data(**overrides: object) -> dict:
    """Return a minimal valid Character payload, without health."""
    data: dict = {
        "id": "char123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "character_class": "VAMPIRE",
        "game_version": "V5",
        "name_first": "John",
        "name_last": "Doe",
        "name": "Johnny",
        "name_full": "John Doe",
        "company_id": "company123",
        "campaign_id": "campaign123",
    }
    data.update(overrides)
    return data


class TestCharacterHealth:
    """Tests for character health response and request models."""

    def test_v4_health_parses_levels(self) -> None:
        """Verify V4 health parses its damage and marked level names."""
        # When: Parsing a character with V4 health
        character = Character.model_validate(
            _character_data(
                game_version="V4",
                health={
                    "type": "DAMAGE",
                    "size": 7,
                    "damage": 1,
                    "extra_levels": 0,
                    "levels": [
                        {"name": "Bruised", "marked": True},
                        {"name": "Hurt", "marked": False},
                    ],
                },
            )
        )

        # Then: Health and its levels are typed
        assert isinstance(character.health, Health)
        assert character.health.damage == 1
        assert character.health.levels[0].marked is True
        assert character.health.levels[1].marked is False

    def test_v5_health_levels_none(self) -> None:
        """Verify V5 health has a damage count and no levels."""
        # When: Parsing a character with V5 health
        character = Character.model_validate(
            _character_data(health={"type": "DAMAGE", "size": 5, "damage": 2, "extra_levels": 0})
        )

        # Then: Damage is set and levels are None
        assert character.health.damage == 2
        assert character.health.levels is None
        assert character.health.extra_levels == 0

    def test_health_has_only_house_rule_fields(self) -> None:
        """Verify Health carries no typed marks, boxes, impairment, or penalties."""
        # When/Then: The model fields are exactly the simplified shape
        assert set(Health.model_fields) == {"type", "size", "damage", "extra_levels", "levels"}
        assert set(HealthLevel.model_fields) == {"name", "marked"}

    def test_health_without_damage_parses(self) -> None:
        """Verify a typed-marks health payload from an older API still parses."""
        # When: Parsing a health payload that has no damage field
        health = Health.model_validate(
            {
                "type": "DAMAGE",
                "size": 5,
                "superficial": 1,
                "aggravated": 0,
                "boxes": ["SUPERFICIAL", None, None, None, None],
                "is_impaired": False,
                "extra_levels": 0,
            }
        )

        # Then: Damage is None
        assert health.damage is None

    def test_v4_health_without_marked_parses(self) -> None:
        """Verify V4 levels from an older API without marked still parse."""
        # When: Parsing V4 levels that carry penalty and mark instead of marked
        health = Health.model_validate(
            {
                "type": "DAMAGE",
                "size": 7,
                "extra_levels": 0,
                "levels": [{"name": "Bruised", "penalty": 0, "mark": "LETHAL"}],
            }
        )

        # Then: The level parses with marked unset
        assert health.levels[0].name == "Bruised"
        assert health.levels[0].marked is None

    def test_character_without_health_parses(self) -> None:
        """Verify a payload from an API without health still parses."""
        # When: Parsing a character with no health field
        character = Character.model_validate(_character_data())

        # Then: Health is None
        assert character.health is None

    def test_health_state_set_defaults_zero(self) -> None:
        """Verify unset health fields dump as zero."""
        # When: Dumping a health state with only damage set
        body = HealthStateSet(damage=2).model_dump()

        # Then: Every field is present
        assert body == {"extra_levels": 0, "damage": 2}

    @pytest.mark.parametrize("field", ["superficial", "aggravated", "bashing", "lethal"])
    def test_health_state_set_rejects_typed_marks(self, field: str) -> None:
        """Verify a typed damage field fails client-side instead of resetting health."""
        # When/Then: Passing a removed field raises
        with pytest.raises(PydanticValidationError):
            HealthStateSet(**{field: 1})

    def test_character_create_accepts_health_and_tracker(self) -> None:
        """Verify CharacterCreate carries health and per-trait tracker state."""
        # When: Building a create request with health and a trait tracker
        request = CharacterCreate(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            health=HealthStateSet(damage=2),
            traits=[
                CharacterCreateTraitAssign(
                    trait_id="t1", value=3, tracker=TrackerStateSet(current=1)
                )
            ],
        )
        body = request.model_dump(exclude_none=True)

        # Then: Both are serialized
        assert body["health"]["damage"] == 2
        assert body["traits"][0]["tracker"] == {"current": 1}
