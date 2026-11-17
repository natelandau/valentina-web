"""Unit tests for character trait models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models import (
    BulkAssignTraitFailure,
    BulkAssignTraitResponse,
    BulkAssignTraitSuccess,
)
from vweb.api_client.models.character_trait import (
    _TRACKER_ADAPTER,
    CharacterTrait,
    CharacterTraitAdd,
    CharacterTraitSpecialtyCreate,
    CharacterTraitSpecialtyUpdate,
    CounterTracker,
    StainsTracker,
    TrackerStateSet,
    TraitCreate,
    _TrackerAction,
)
from vweb.api_client.models.shared import Trait


class TestCharacterTrait:
    """Tests for CharacterTrait response model."""

    def test_character_trait_minimal_fields(self) -> None:
        """Verify CharacterTrait model with required fields."""
        # Given: A trait object
        trait = Trait(
            id="trait123",
            name="Strength",
            date_created=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            date_modified=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            category_id="cat123",
            sheet_section_id="section123",
        )

        # When: Creating a character trait
        character_trait = CharacterTrait(
            id="ct123",
            character_id="char123",
            value=3,
            trait=trait,
        )

        # Then: All fields are set correctly
        assert character_trait.id == "ct123"
        assert character_trait.character_id == "char123"
        assert character_trait.value == 3
        assert character_trait.trait.name == "Strength"

    def test_character_trait_is_rollable_default(self) -> None:
        """Verify Trait.is_rollable defaults to True."""
        # Given: A trait with minimal fields
        trait = Trait(
            id="trait123",
            name="Strength",
            date_created=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            date_modified=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            category_id="cat123",
            sheet_section_id="section123",
        )

        # Then: is_rollable defaults to True
        assert trait.is_rollable is True

    def test_character_trait_is_rollable_false(self) -> None:
        """Verify Trait.is_rollable can be set to False."""
        # Given: A trait with is_rollable=False
        trait = Trait(
            id="trait123",
            name="Humanity",
            date_created=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            date_modified=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            category_id="cat123",
            sheet_section_id="section123",
            is_rollable=False,
        )

        # Then: is_rollable is False
        assert trait.is_rollable is False

    def test_character_trait_from_api_response(self) -> None:
        """Verify CharacterTrait model validates from API response format."""
        # Given: API response data
        data = {
            "id": "ct456",
            "character_id": "char789",
            "value": 5,
            "trait": {
                "id": "trait456",
                "name": "Dexterity",
                "description": "Physical agility and coordination",
                "date_created": "2024-01-15T10:30:00Z",
                "date_modified": "2024-01-15T10:30:00Z",
                "category_id": "cat456",
                "show_when_zero": True,
                "sheet_section_id": "section123",
                "max_value": 5,
                "min_value": 0,
                "initial_cost": 1,
                "upgrade_cost": 2,
            },
        }

        # When: Validating the response
        character_trait = CharacterTrait.model_validate(data)

        # Then: All fields are correctly parsed
        assert character_trait.id == "ct456"
        assert character_trait.character_id == "char789"
        assert character_trait.value == 5
        assert character_trait.trait.id == "trait456"
        assert character_trait.trait.name == "Dexterity"
        assert character_trait.trait.description == "Physical agility and coordination"
        assert character_trait.trait.max_value == 5
        assert character_trait.specialties == []

    def test_character_trait_with_specialties(self) -> None:
        """Verify CharacterTrait parses specialties in server order."""
        # Given: API response data with two specialties
        data = {
            "id": "ct456",
            "character_id": "char789",
            "value": 2,
            "trait": {
                "id": "trait456",
                "name": "Melee",
                "date_created": "2024-01-15T10:30:00Z",
                "date_modified": "2024-01-15T10:30:00Z",
                "category_id": "cat456",
                "sheet_section_id": "section123",
            },
            "specialties": [
                {
                    "id": "spec1",
                    "name": "Knives",
                    "date_created": "2024-01-15T10:30:00Z",
                    "date_modified": "2024-01-15T10:30:00Z",
                },
                {
                    "id": "spec2",
                    "name": "Swords",
                    "date_created": "2024-01-16T10:30:00Z",
                    "date_modified": "2024-01-16T10:30:00Z",
                },
            ],
        }

        # When: Validating the response
        character_trait = CharacterTrait.model_validate(data)

        # Then: Specialties are parsed with datetimes, oldest first
        assert [s.name for s in character_trait.specialties] == ["Knives", "Swords"]
        assert character_trait.specialties[0].date_created == datetime(
            2024, 1, 15, 10, 30, 0, tzinfo=UTC
        )

    def test_character_trait_with_full_trait_data(self) -> None:
        """Verify CharacterTrait with complete trait information."""
        # Given: Complete API response data
        data = {
            "id": "ct789",
            "character_id": "char111",
            "value": 2,
            "trait": {
                "id": "trait789",
                "name": "Firearms",
                "description": "Skill with ranged weapons",
                "date_created": "2024-01-15T10:30:00Z",
                "date_modified": "2024-01-15T10:30:00Z",
                "link": "https://wiki.example.com/firearms",
                "show_when_zero": False,
                "max_value": 5,
                "min_value": 0,
                "initial_cost": 3,
                "upgrade_cost": 3,
                "sheet_section_name": "Skills",
                "sheet_section_id": "section123",
                "category_name": "Physical Skills",
                "category_id": "cat789",
                "character_classes": ["VAMPIRE", "HUNTER"],
                "game_versions": ["V5"],
            },
        }

        # When: Validating the response
        character_trait = CharacterTrait.model_validate(data)

        # Then: All trait details are accessible
        assert character_trait.trait.link == "https://wiki.example.com/firearms"
        assert character_trait.trait.sheet_section_name == "Skills"
        assert character_trait.trait.category_name == "Physical Skills"
        assert character_trait.trait.character_classes == ["VAMPIRE", "HUNTER"]
        assert character_trait.trait.game_versions == ["V5"]


class TestTraitAssign:
    """Tests for CharacterTraitAdd model."""

    def test_assign_request_required_fields(self) -> None:
        """Verify CharacterTraitAdd with required fields."""
        # When: Creating a request
        request = CharacterTraitAdd(
            trait_id="trait123",
            value=3,
            currency="XP",
        )

        # Then: Fields are set correctly
        assert request.trait_id == "trait123"
        assert request.value == 3

    def test_assign_request_model_dump(self) -> None:
        """Verify model_dump produces correct JSON payload."""
        # Given: An assign request
        request = CharacterTraitAdd(
            trait_id="trait456",
            value=5,
            currency="XP",
        )

        # When: Dumping to JSON
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Correct JSON structure is produced
        assert data == {
            "trait_id": "trait456",
            "value": 5,
            "currency": "XP",
        }

    def test_assign_request_zero_value(self) -> None:
        """Verify CharacterTraitAdd accepts zero value."""
        # When: Creating a request with value 0
        request = CharacterTraitAdd(
            trait_id="trait789",
            value=0,
            currency="XP",
        )

        # Then: Value is set correctly
        assert request.value == 0


class TestTraitCreate:
    """Tests for TraitCreate model."""

    def test_create_request_required_fields(self) -> None:
        """Verify TraitCreate with required fields only."""
        # When: Creating a request with required fields
        request = TraitCreate(
            name="Custom Skill",
            category_id="cat123",
            currency="XP",
        )

        # Then: Required fields are set, defaults applied
        assert request.name == "Custom Skill"
        assert request.category_id == "cat123"
        assert request.currency == "XP"
        assert request.max_value == 5
        assert request.min_value == 0
        assert request.show_when_zero is True
        assert request.is_rollable is True
        assert request.description is None
        assert request.initial_cost is None
        assert request.upgrade_cost is None

    def test_create_request_missing_currency(self) -> None:
        """Verify TraitCreate raises when currency is omitted."""
        # When/Then: Omitting the required currency field raises
        with pytest.raises(PydanticValidationError):
            TraitCreate(name="Custom Skill", category_id="cat123")  # type: ignore[call-arg]

    def test_create_request_all_fields(self) -> None:
        """Verify TraitCreate with all fields."""
        # When: Creating a request with all fields
        request = TraitCreate(
            name="Custom Background",
            category_id="backgrounds_cat",
            currency="STARTING_POINTS",
            description="A custom background trait",
            max_value=10,
            min_value=1,
            show_when_zero=False,
            is_rollable=False,
            initial_cost=3,
            upgrade_cost=2,
        )

        # Then: All fields are set correctly
        assert request.name == "Custom Background"
        assert request.category_id == "backgrounds_cat"
        assert request.currency == "STARTING_POINTS"
        assert request.description == "A custom background trait"
        assert request.max_value == 10
        assert request.min_value == 1
        assert request.show_when_zero is False
        assert request.is_rollable is False
        assert request.initial_cost == 3
        assert request.upgrade_cost == 2

    def test_create_request_model_dump(self) -> None:
        """Verify model_dump produces correct JSON payload."""
        # Given: A create request with required fields only
        request = TraitCreate(
            name="Stealth",
            category_id="skills_cat",
            currency="NO_COST",
        )

        # When: Dumping to JSON with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Required fields and unset fields without defaults are in the output
        assert data["name"] == "Stealth"
        assert data["category_id"] == "skills_cat"
        assert data["currency"] == "NO_COST"
        assert "description" not in data
        assert "initial_cost" not in data
        assert "upgrade_cost" not in data

    def test_create_request_model_dump_with_optionals(self) -> None:
        """Verify model_dump includes optional fields when set."""
        # Given: A create request with optional fields
        request = TraitCreate(
            name="Lore",
            category_id="knowledge_cat",
            currency="XP",
            description="Knowledge of ancient texts",
            initial_cost=2,
        )

        # When: Dumping to JSON
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Optional fields are included
        assert data["name"] == "Lore"
        assert data["currency"] == "XP"
        assert data["description"] == "Knowledge of ancient texts"
        assert data["initial_cost"] == 2

    def test_create_request_is_rollable_omitted_when_default(self) -> None:
        """Verify is_rollable is not sent when left at its default."""
        # Given: A create request that does not set is_rollable
        request = TraitCreate(name="Stealth", category_id="skills_cat", currency="NO_COST")

        # When: Dumping to JSON with exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: is_rollable is omitted so the server default (rollable) applies
        assert "is_rollable" not in data

    def test_create_request_is_rollable_sent_when_false(self) -> None:
        """Verify is_rollable=False is transmitted to create a non-rollable trait."""
        # Given: A create request that opts out of rollability
        request = TraitCreate(
            name="Stealth", category_id="skills_cat", currency="NO_COST", is_rollable=False
        )

        # When: Dumping to JSON
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: is_rollable is included with the explicit value
        assert data["is_rollable"] is False

    def test_create_request_max_value_validation(self) -> None:
        """Verify max_value has valid range constraint."""
        # When: Creating a request with valid max_value
        request = TraitCreate(
            name="Test Trait",
            category_id="cat123",
            currency="XP",
            max_value=100,
        )

        # Then: Value is accepted
        assert request.max_value == 100

    def test_create_request_min_value_validation(self) -> None:
        """Verify min_value has valid range constraint."""
        # When: Creating a request with valid min_value
        request = TraitCreate(
            name="Test Trait",
            category_id="cat123",
            currency="XP",
            min_value=0,
        )

        # Then: Value is accepted
        assert request.min_value == 0


class TestBulkAssignTraitModels:
    """Tests for bulk assign trait response models."""

    def test_bulk_assign_trait_success_parses(self, character_trait_response_data: dict) -> None:
        """Verify BulkAssignTraitSuccess parses valid data."""
        data = {"trait_id": "abc123", "character_trait": character_trait_response_data}
        result = BulkAssignTraitSuccess.model_validate(data)
        assert result.trait_id == "abc123"
        assert result.character_trait.id == character_trait_response_data["id"]

    def test_bulk_assign_trait_failure_parses(self) -> None:
        """Verify BulkAssignTraitFailure parses valid data."""
        data = {"trait_id": "abc123", "error": "Trait not found"}
        result = BulkAssignTraitFailure.model_validate(data)
        assert result.trait_id == "abc123"
        assert result.error == "Trait not found"

    def test_bulk_assign_trait_response_parses(self, character_trait_response_data: dict) -> None:
        """Verify BulkAssignTraitResponse parses mixed succeeded/failed."""
        data = {
            "succeeded": [{"trait_id": "t1", "character_trait": character_trait_response_data}],
            "failed": [{"trait_id": "t2", "error": "Not enough XP"}],
        }
        result = BulkAssignTraitResponse.model_validate(data)
        assert len(result.succeeded) == 1
        assert len(result.failed) == 1

    def test_bulk_assign_trait_response_empty(self) -> None:
        """Verify BulkAssignTraitResponse handles empty lists."""
        data = {"succeeded": [], "failed": []}
        result = BulkAssignTraitResponse.model_validate(data)
        assert result.succeeded == []
        assert result.failed == []


class TestCharacterTraitSpecialtyCreate:
    """Tests for CharacterTraitSpecialtyCreate request model."""

    def test_currency_defaults_to_no_cost(self) -> None:
        """Verify currency defaults to NO_COST."""
        # When: Constructing with only a name
        request = CharacterTraitSpecialtyCreate(name="Knives")

        # Then: Currency is NO_COST
        assert request.currency == "NO_COST"

    @pytest.mark.parametrize("name", ["ab", "x" * 51])
    def test_name_length_enforced(self, name: str) -> None:
        """Verify names outside 3-50 characters are rejected."""
        # When/Then: Constructing raises
        with pytest.raises(PydanticValidationError):
            CharacterTraitSpecialtyCreate(name=name)

    def test_invalid_currency_rejected(self) -> None:
        """Verify an unknown currency is rejected."""
        # When/Then: Constructing raises
        with pytest.raises(PydanticValidationError):
            CharacterTraitSpecialtyCreate(name="Knives", currency="GOLD")


class TestCharacterTraitSpecialtyUpdate:
    """Tests for CharacterTraitSpecialtyUpdate request model."""

    @pytest.mark.parametrize("name", ["ab", "x" * 51])
    def test_name_length_enforced(self, name: str) -> None:
        """Verify names outside 3-50 characters are rejected."""
        # When/Then: Constructing raises
        with pytest.raises(PydanticValidationError):
            CharacterTraitSpecialtyUpdate(name=name)


def _character_trait_data(**overrides: object) -> dict:
    """Return a minimal valid CharacterTrait payload, without tracker fields."""
    data: dict = {
        "id": "ct123",
        "character_id": "char123",
        "value": 3,
        "trait": {
            "id": "trait123",
            "name": "Willpower",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "category_id": "cat123",
            "sheet_section_id": "section123",
        },
    }
    data.update(overrides)
    return data


class TestTrackerModels:
    """Tests for trait tracker response and request models."""

    def test_counter_tracker_dispatch(self) -> None:
        """Verify a COUNTER tracker parses as CounterTracker."""
        # When: Parsing a trait with a counter tracker
        ct = CharacterTrait.model_validate(
            _character_trait_data(tracker={"type": "COUNTER", "size": 5, "current": 3})
        )

        # Then: The counter variant is chosen
        assert isinstance(ct.tracker, CounterTracker)
        assert ct.tracker.current == 3

    def test_damage_tracker_type_rejected(self) -> None:
        """Verify a trait tracker no longer accepts the DAMAGE type."""
        # When/Then: Parsing a trait with a DAMAGE tracker raises
        with pytest.raises(PydanticValidationError):
            CharacterTrait.model_validate(
                _character_trait_data(
                    tracker={
                        "type": "DAMAGE",
                        "size": 5,
                        "superficial": 1,
                        "aggravated": 0,
                        "boxes": ["SUPERFICIAL", None, None, None, None],
                        "is_impaired": False,
                    }
                )
            )

    def test_stains_tracker_dispatch(self) -> None:
        """Verify a STAINS tracker parses as StainsTracker with only its stain fields."""
        # When: Parsing a trait with a stains tracker
        ct = CharacterTrait.model_validate(
            _character_trait_data(
                tracker={"type": "STAINS", "humanity": 7, "stain_capacity": 3, "stains": 4}
            )
        )

        # Then: The stains variant is chosen without impairment or overflow fields
        assert isinstance(ct.tracker, StainsTracker)
        assert ct.tracker.stains == 4
        assert set(StainsTracker.model_fields) == {"type", "humanity", "stain_capacity", "stains"}

    def test_unknown_tracker_type_rejected(self) -> None:
        """Verify an unknown tracker type fails validation."""
        # When/Then: Parsing an unknown tracker type raises
        with pytest.raises(PydanticValidationError):
            CharacterTrait.model_validate(
                _character_trait_data(tracker={"type": "BOGUS", "size": 1, "current": 1})
            )

    def test_tracker_absent_defaults_none(self) -> None:
        """Verify payloads from an API without trackers still parse."""
        # When: Parsing a trait with no tracker fields
        ct = CharacterTrait.model_validate(_character_trait_data())

        # Then: Tracker fields default to None
        assert ct.tracker is None
        assert ct.trait.tracker_type_v4 is None
        assert ct.trait.tracker_type_v5 is None

    def test_tracker_adapter_validates(self) -> None:
        """Verify the shared adapter dispatches on type."""
        # When: Validating a raw counter payload
        tracker = _TRACKER_ADAPTER.validate_python({"type": "COUNTER", "size": 2, "current": 2})

        # Then: A CounterTracker is returned
        assert isinstance(tracker, CounterTracker)

    def test_tracker_state_set_rejects_negative(self) -> None:
        """Verify negative tracker values fail client-side."""
        # When/Then: A negative value raises
        with pytest.raises(PydanticValidationError):
            TrackerStateSet(current=-1)

    def test_tracker_state_set_dump_keeps_zero(self) -> None:
        """Verify a zero value is sent and unset fields are not."""
        # When: Dumping a state with current=0
        body = TrackerStateSet(current=0).model_dump(exclude_none=True)

        # Then: Only current is present, with its zero kept
        assert body == {"current": 0}

    def test_tracker_action_rejects_zero_amount(self) -> None:
        """Verify an amount below 1 fails client-side."""
        # When/Then: amount=0 raises
        with pytest.raises(PydanticValidationError):
            _TrackerAction(action="spend", amount=0)

    def test_tracker_action_dump_sends_action_and_amount(self) -> None:
        """Verify an action sends only its action and amount."""
        # When: Dumping a damage action
        body = _TrackerAction(action="damage", amount=2).model_dump(exclude_none=True)

        # Then: Only action and amount are sent
        assert body == {"action": "damage", "amount": 2}

    @pytest.mark.parametrize("field", ["superficial", "aggravated", "bogus"])
    def test_tracker_state_set_rejects_unknown_field(self, field: str) -> None:
        """Verify a field other than current or stains fails client-side."""
        # When/Then: Passing a removed or unknown field raises
        with pytest.raises(PydanticValidationError):
            TrackerStateSet(**{field: 1})
