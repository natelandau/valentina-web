"""Tests for vweb.api_client.models.campaigns."""

from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models.campaigns import (
    Campaign,
    CampaignCreate,
    CampaignUpdate,
)


class TestCampaign:
    """Tests for Campaign model."""

    def test_valid_campaign(self):
        """Verify valid campaign creation."""
        campaign = Campaign(
            id="campaign123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Campaign",
            description="A test campaign",
            asset_ids=["asset1", "asset2"],
            desperation=2,
            danger=3,
            company_id="company123",
        )

        assert campaign.id == "campaign123"
        assert campaign.name == "Test Campaign"
        assert campaign.description == "A test campaign"
        assert campaign.asset_ids == ["asset1", "asset2"]
        assert campaign.desperation == 2
        assert campaign.danger == 3
        assert campaign.company_id == "company123"

    def test_defaults(self):
        """Verify default values."""
        campaign = Campaign(
            id="campaign123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Campaign",
            company_id="company123",
        )

        assert campaign.description is None
        assert campaign.in_game_date is None
        assert campaign.asset_ids == []
        assert campaign.desperation == 0
        assert campaign.danger == 0

    def test_in_game_date_field(self):
        """Verify the in_game_date field parses an ISO 8601 calendar date."""
        campaign = Campaign(
            id="campaign123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Campaign",
            company_id="company123",
            in_game_date="1924-03-15",
        )

        assert campaign.in_game_date == date(1924, 3, 15)

    def test_child_resource_counts(self):
        """Verify child-resource count fields default to 0 and accept values."""
        defaults = Campaign(
            id="campaign123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Campaign",
            company_id="company123",
        )
        assert defaults.num_books == 0
        assert defaults.num_chapters == 0
        assert defaults.num_notes == 0
        assert defaults.num_player_characters == 0
        assert defaults.num_storyteller_characters == 0
        assert defaults.num_npc_characters == 0

        populated = Campaign(
            id="campaign123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Campaign",
            company_id="company123",
            num_books=2,
            num_chapters=5,
            num_notes=3,
            num_player_characters=4,
            num_storyteller_characters=1,
            num_npc_characters=7,
        )
        assert populated.num_books == 2
        assert populated.num_chapters == 5
        assert populated.num_notes == 3
        assert populated.num_player_characters == 4
        assert populated.num_storyteller_characters == 1
        assert populated.num_npc_characters == 7


class TestCampaignCreate:
    """Tests for CampaignCreate model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = CampaignCreate(
            name="Test Campaign",
            description="A test campaign",
            desperation=2,
            danger=3,
        )

        assert request.name == "Test Campaign"
        assert request.description == "A test campaign"
        assert request.desperation == 2
        assert request.danger == 3

    def test_minimal_request(self):
        """Verify minimal valid request with defaults."""
        request = CampaignCreate(name="Test")

        assert request.name == "Test"
        assert request.description is None
        assert request.in_game_date is None
        assert request.desperation == 0
        assert request.danger == 0

    def test_in_game_date_accepts_iso_string(self):
        """Verify in_game_date parses an ISO 8601 calendar date string."""
        request = CampaignCreate(name="Valid", in_game_date="1924-03-15")

        assert request.in_game_date == date(1924, 3, 15)

    def test_in_game_date_rejects_non_date(self):
        """Verify in_game_date rejects a value that is not a calendar date."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="Valid", in_game_date="not-a-date")

    def test_name_min_length(self):
        """Verify name minimum length validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="ab")

    def test_name_max_length(self):
        """Verify name maximum length validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="a" * 51)

    def test_short_description_allowed(self):
        """Verify a short description is accepted, as the API sets no minimum."""
        assert CampaignCreate(name="Valid", description="ab").description == "ab"

    def test_desperation_max_value(self):
        """Verify desperation maximum value validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="Valid", desperation=6)

    def test_desperation_min_value(self):
        """Verify desperation minimum value validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="Valid", desperation=-1)

    def test_danger_max_value(self):
        """Verify danger maximum value validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="Valid", danger=6)

    def test_danger_min_value(self):
        """Verify danger minimum value validation."""
        with pytest.raises(PydanticValidationError):
            CampaignCreate(name="Valid", danger=-1)


class TestCampaignUpdate:
    """Tests for CampaignUpdate model."""

    def test_all_fields_optional(self):
        """Verify all fields default to None."""
        request = CampaignUpdate()

        assert request.name is None
        assert request.description is None
        assert request.desperation is None
        assert request.danger is None

    def test_partial_update(self):
        """Verify partial update works."""
        request = CampaignUpdate(name="New Name", desperation=3)

        assert request.name == "New Name"
        assert request.description is None
        assert request.desperation == 3
        assert request.danger is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        request = CampaignUpdate(name="New Name", danger=4)

        data = request.model_dump(exclude_none=True)

        assert data == {"name": "New Name", "danger": 4}

    def test_in_game_date_serializes_to_iso_string(self):
        """Verify in_game_date serializes to an ISO 8601 date string in JSON mode."""
        request = CampaignUpdate(in_game_date=date(1924, 3, 15))

        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        assert data == {"in_game_date": "1924-03-15"}

    def test_in_game_date_none_tracked_as_set(self):
        """Verify an explicit None in_game_date is recorded so the service can clear it."""
        # exclude_none drops the None, but model_fields_set lets the service re-add an explicit
        # null to the payload to clear the field. See CampaignsService.update.
        request = CampaignUpdate(in_game_date=None)

        assert "in_game_date" in request.model_fields_set
        assert request.in_game_date is None

    def test_in_game_date_rejects_non_date_when_provided(self):
        """Verify in_game_date validation still applies on update."""
        with pytest.raises(PydanticValidationError):
            CampaignUpdate(in_game_date="not-a-date")

    def test_name_validation_when_provided(self):
        """Verify name validation still applies when value is provided."""
        with pytest.raises(PydanticValidationError):
            CampaignUpdate(name="ab")

    def test_desperation_validation_when_provided(self):
        """Verify desperation validation still applies when value is provided."""
        with pytest.raises(PydanticValidationError):
            CampaignUpdate(desperation=6)

    def test_danger_validation_when_provided(self):
        """Verify danger validation still applies when value is provided."""
        with pytest.raises(PydanticValidationError):
            CampaignUpdate(danger=6)

    def test_update_explicit_none_for_constrained_fields(self):
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for all constrained fields
        request = CampaignUpdate(
            name=None,
            description=None,
            desperation=None,
            danger=None,
        )

        # Then: All fields are None without validation errors
        assert request.name is None
        assert request.description is None
        assert request.desperation is None
        assert request.danger is None


class TestCampaignCreateConstraints:
    """Tests for CampaignCreate optional field constraint handling."""

    def test_create_explicit_none_for_optional_constrained_fields(self):
        """Verify explicitly passing None for optional constrained fields does not raise."""
        # When: Creating a request with None for optional description
        request = CampaignCreate(name="Test", description=None)

        # Then: Description is None without validation errors
        assert request.description is None
