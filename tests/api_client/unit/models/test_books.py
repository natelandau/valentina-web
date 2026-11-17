"""Tests for vweb.api_client.models.books."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models import (
    CampaignBook,
    CampaignBookDetail,
    CampaignChapter,
)
from vweb.api_client.models.books import (
    BookCreate,
    BookUpdate,
    _BookRenumber,
)


class TestCampaignBook:
    """Tests for CampaignBook model."""

    def test_valid_book(self):
        """Verify valid book creation."""
        book = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            description="A test book",
            number=1,
            campaign_id="campaign123",
        )

        assert book.id == "book123"
        assert book.name == "Test Book"
        assert book.description == "A test book"
        assert book.number == 1
        assert book.campaign_id == "campaign123"

    def test_defaults(self):
        """Verify default values."""
        book = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            number=1,
            campaign_id="campaign123",
        )

        assert book.description is None
        assert book.character_ids == []

    def test_character_ids_default_empty(self):
        """Verify character_ids defaults to an empty list."""
        # Given/When: a book built without character_ids
        book = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            number=1,
            campaign_id="campaign123",
        )
        # Then: character_ids is an empty list
        assert book.character_ids == []

    def test_character_ids_parsed(self):
        """Verify character_ids is parsed from the payload."""
        # Given/When: a book built with character_ids
        book = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            number=1,
            campaign_id="campaign123",
            character_ids=["char1", "char2"],
        )
        # Then: the list round-trips
        assert book.character_ids == ["char1", "char2"]

    def test_child_resource_counts(self):
        """Verify child-resource count fields default to 0 and accept values."""
        defaults = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            number=1,
            campaign_id="campaign123",
        )
        assert defaults.num_chapters == 0
        assert defaults.num_notes == 0
        assert defaults.num_assets == 0

        populated = CampaignBook(
            id="book123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test Book",
            number=1,
            campaign_id="campaign123",
            num_chapters=4,
            num_notes=2,
            num_assets=6,
        )
        assert populated.num_chapters == 4
        assert populated.num_notes == 2
        assert populated.num_assets == 6


class TestBookCreate:
    """Tests for BookCreate model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = BookCreate(
            name="Test Book",
            description="A test book",
        )

        assert request.name == "Test Book"
        assert request.description == "A test book"

    def test_minimal_request(self):
        """Verify minimal valid request with defaults."""
        request = BookCreate(name="Test")

        assert request.name == "Test"
        assert request.description is None

    def test_short_name_allowed(self):
        """Verify a short name is accepted, as the API sets no minimum."""
        assert BookCreate(name="ab").name == "ab"

    def test_name_max_length(self):
        """Verify name maximum length validation."""
        with pytest.raises(PydanticValidationError):
            BookCreate(name="a" * 51)

    def test_short_description_allowed(self):
        """Verify a short description is accepted, as the API sets no minimum."""
        assert BookCreate(name="Valid", description="ab").description == "ab"


class TestBookUpdate:
    """Tests for BookUpdate model."""

    def test_all_fields_optional(self):
        """Verify all fields default to None."""
        request = BookUpdate()

        assert request.name is None
        assert request.description is None

    def test_partial_update(self):
        """Verify partial update works."""
        request = BookUpdate(name="New Name")

        assert request.name == "New Name"
        assert request.description is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        request = BookUpdate(name="New Name")

        data = request.model_dump(exclude_none=True)

        assert data == {"name": "New Name"}

    def test_name_validation_when_provided(self):
        """Verify the name length limit still applies when a value is provided."""
        with pytest.raises(PydanticValidationError):
            BookUpdate(name="a" * 51)

    def test_empty_description_is_sent_to_clear_it(self):
        """Verify an empty description survives the dump, so the API clears it."""
        data = BookUpdate(description="").model_dump(exclude_none=True, exclude_unset=True)

        assert data == {"description": ""}


def _book_payload() -> dict:
    return {
        "id": "book_1",
        "date_created": datetime.now(UTC).isoformat(),
        "date_modified": datetime.now(UTC).isoformat(),
        "name": "Book One",
        "description": "A book.",
        "character_ids": [],
        "number": 1,
        "campaign_id": "camp_1",
    }


def test_campaign_book_detail_defaults_embeds_to_none() -> None:
    """Verify embed fields default to None when not provided."""
    detail = CampaignBookDetail.model_validate(_book_payload())
    assert detail.chapters is None
    assert detail.notes is None
    assert detail.assets is None
    # Subclass relationship preserved
    assert isinstance(detail, CampaignBook)


def test_campaign_book_detail_accepts_embedded_lists() -> None:
    """Verify embedded lists are parsed into the correct model types."""
    chapter = {
        "id": "chap_1",
        "date_created": datetime.now(UTC).isoformat(),
        "date_modified": datetime.now(UTC).isoformat(),
        "name": "Chapter 1",
        "description": None,
        "character_ids": [],
        "number": 1,
        "book_id": "book_1",
    }
    payload = _book_payload() | {"chapters": [chapter], "notes": [], "assets": []}
    detail = CampaignBookDetail.model_validate(payload)
    assert detail.chapters is not None
    assert len(detail.chapters) == 1
    assert isinstance(detail.chapters[0], CampaignChapter)
    assert detail.notes == []
    assert detail.assets == []


def test_campaign_book_detail_rejects_wrong_embed_type() -> None:
    """Verify validation error is raised when chapters is not a list."""
    payload = _book_payload() | {"chapters": "not-a-list"}
    with pytest.raises(ValidationError):
        CampaignBookDetail.model_validate(payload)


class TestBookRenumber:
    """Tests for _BookRenumber model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = _BookRenumber(number=5)

        assert request.number == 5

    def test_number_min_value(self):
        """Verify number minimum value validation."""
        with pytest.raises(PydanticValidationError):
            _BookRenumber(number=0)

    def test_number_negative_value(self):
        """Verify negative number validation."""
        with pytest.raises(PydanticValidationError):
            _BookRenumber(number=-1)

    def test_number_required(self):
        """Verify number is required."""
        with pytest.raises(PydanticValidationError):
            _BookRenumber()
