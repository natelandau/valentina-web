"""Tests for vweb.api_client.models.chapters."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models import CampaignChapter, CampaignChapterDetail
from vweb.api_client.models.chapters import (
    ChapterCreate,
    ChapterUpdate,
    _ChapterRenumber,
)


def _chapter_payload() -> dict:
    return {
        "id": "chap_1",
        "date_created": datetime.now(UTC).isoformat(),
        "date_modified": datetime.now(UTC).isoformat(),
        "name": "Chapter 1",
        "description": None,
        "asset_ids": [],
        "character_ids": [],
        "number": 1,
        "book_id": "book_1",
    }


def test_campaign_chapter_detail_defaults_embeds_to_none() -> None:
    """Verify embed fields default to None and subclass relationship holds."""
    detail = CampaignChapterDetail.model_validate(_chapter_payload())
    assert detail.notes is None
    assert detail.assets is None
    assert isinstance(detail, CampaignChapter)


def test_campaign_chapter_detail_accepts_embedded_lists() -> None:
    """Verify embedded lists are accepted and parsed correctly."""
    payload = _chapter_payload() | {"notes": [], "assets": []}
    detail = CampaignChapterDetail.model_validate(payload)
    assert detail.notes == []
    assert detail.assets == []


def test_campaign_chapter_detail_rejects_wrong_embed_type() -> None:
    """Verify a non-list value for an embed field raises ValidationError."""
    payload = _chapter_payload() | {"notes": "not-a-list"}
    with pytest.raises(ValidationError):
        CampaignChapterDetail.model_validate(payload)


class TestCampaignChapter:
    """Tests for CampaignChapter model."""

    def test_valid_chapter(self):
        """Verify valid chapter creation."""
        chapter = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            description="A test chapter",
            asset_ids=["asset1", "asset2"],
            character_ids=["char1", "char2"],
            number=1,
            book_id="book123",
        )

        assert chapter.id == "chapter123"
        assert chapter.name == "Test Chapter"
        assert chapter.description == "A test chapter"
        assert chapter.asset_ids == ["asset1", "asset2"]
        assert chapter.character_ids == ["char1", "char2"]
        assert chapter.number == 1
        assert chapter.book_id == "book123"

    def test_defaults(self):
        """Verify default values."""
        chapter = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            number=1,
            book_id="book123",
        )

        assert chapter.description is None
        assert chapter.asset_ids == []
        assert chapter.character_ids == []

    def test_required_fields(self):
        """Verify required fields raise error when missing."""
        with pytest.raises(PydanticValidationError):
            CampaignChapter(
                date_created="2024-01-15T10:30:00Z",
                date_modified="2024-01-15T10:30:00Z",
                name="Test Chapter",
                number=1,
                # Missing book_id
            )

    def test_child_resource_counts(self):
        """Verify child-resource count fields default to 0 and accept values."""
        defaults = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            number=1,
            book_id="book123",
        )
        assert defaults.num_notes == 0
        assert defaults.num_assets == 0

        populated = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            number=1,
            book_id="book123",
            num_notes=3,
            num_assets=5,
        )
        assert populated.num_notes == 3
        assert populated.num_assets == 5

    def test_character_ids_default_empty(self):
        """Verify character_ids defaults to an empty list."""
        # Given/When: a chapter built without character_ids
        chapter = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            number=1,
            book_id="book123",
        )
        # Then: character_ids is an empty list
        assert chapter.character_ids == []

    def test_character_ids_parsed(self):
        """Verify character_ids is parsed from the payload."""
        # Given/When: a chapter built with character_ids
        chapter = CampaignChapter(
            id="chapter123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Chapter",
            number=1,
            book_id="book123",
            character_ids=["char1", "char2"],
        )
        # Then: the list round-trips
        assert chapter.character_ids == ["char1", "char2"]


class TestChapterCreate:
    """Tests for ChapterCreate model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = ChapterCreate(
            name="Test Chapter",
            description="A test chapter",
        )

        assert request.name == "Test Chapter"
        assert request.description == "A test chapter"

    def test_minimal_request(self):
        """Verify minimal valid request with defaults."""
        request = ChapterCreate(name="Test")

        assert request.name == "Test"
        assert request.description is None

    def test_name_required(self):
        """Verify name is required."""
        with pytest.raises(PydanticValidationError):
            ChapterCreate()

    def test_character_ids_serialized_when_set(self):
        """Verify character_ids is included in the request body when provided."""
        # Given: a create request with character_ids
        request = ChapterCreate(name="Test", character_ids=["char1"])
        # When: serialized the way the service serializes it
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # Then: character_ids is present
        assert data == {"name": "Test", "character_ids": ["char1"]}

    def test_character_ids_omitted_when_unset(self):
        """Verify character_ids is omitted from the body when not provided."""
        # Given: a create request without character_ids
        request = ChapterCreate(name="Test")
        # When: serialized
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # Then: character_ids key is absent
        assert "character_ids" not in data


class TestChapterUpdate:
    """Tests for ChapterUpdate model."""

    def test_all_fields_optional(self):
        """Verify all fields default to None."""
        request = ChapterUpdate()

        assert request.name is None
        assert request.description is None

    def test_partial_update(self):
        """Verify partial update works."""
        request = ChapterUpdate(name="New Name")

        assert request.name == "New Name"
        assert request.description is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        request = ChapterUpdate(name="New Name")

        data = request.model_dump(exclude_none=True)

        assert data == {"name": "New Name"}

    def test_full_update(self):
        """Verify full update with all fields."""
        request = ChapterUpdate(name="New Name", description="New Description")

        assert request.name == "New Name"
        assert request.description == "New Description"

    def test_character_ids_empty_list_clears(self):
        """Verify an explicit empty list is sent (clears the association)."""
        # Given: an update with character_ids=[]
        request = ChapterUpdate(character_ids=[])
        # When: serialized the way the service serializes it
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # Then: an empty list is sent
        assert data == {"character_ids": []}

    def test_character_ids_unset_omitted(self):
        """Verify an unset character_ids leaves the field out (unchanged)."""
        # Given: an update that does not touch character_ids
        request = ChapterUpdate(name="New Name")
        # When: serialized
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # Then: character_ids is absent
        assert "character_ids" not in data


class TestChapterRenumber:
    """Tests for _ChapterRenumber model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = _ChapterRenumber(number=5)

        assert request.number == 5

    def test_number_min_value(self):
        """Verify number minimum value validation."""
        with pytest.raises(PydanticValidationError):
            _ChapterRenumber(number=0)

    def test_number_negative_value(self):
        """Verify negative number validation."""
        with pytest.raises(PydanticValidationError):
            _ChapterRenumber(number=-1)

    def test_number_required(self):
        """Verify number is required."""
        with pytest.raises(PydanticValidationError):
            _ChapterRenumber()
