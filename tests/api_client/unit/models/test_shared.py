"""Tests for vweb.api_client.models.shared."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models.shared import (
    Asset,
    GiftAttributes,
    Note,
    NoteCreate,
    NoteUpdate,
    RollStatistics,
    Trait,
    TraitPower,
)


class TestAsset:
    """Tests for Asset model."""

    def test_valid_asset(self):
        """Verify valid asset creation."""
        asset = Asset(
            id="asset123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            asset_type="image",
            mime_type="image/png",
            original_filename="avatar.png",
            public_url="https://example.com/avatar.png",
            uploaded_by_id="user123",
            company_id="company123",
            user_parent_id="user123",
        )

        assert asset.id == "asset123"
        assert asset.asset_type == "image"
        assert asset.mime_type == "image/png"
        assert asset.original_filename == "avatar.png"
        assert asset.public_url == "https://example.com/avatar.png"
        assert asset.uploaded_by_id == "user123"
        assert asset.company_id == "company123"
        assert asset.user_parent_id == "user123"

    def test_parent_fk_fields_default_to_none(self):
        """Verify parent FK fields default to None."""
        asset = Asset(
            id="asset123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            asset_type="document",
            mime_type="application/pdf",
            original_filename="doc.pdf",
            public_url="https://example.com/doc.pdf",
            uploaded_by_id="user123",
            company_id="company123",
        )

        assert asset.character_id is None
        assert asset.campaign_id is None
        assert asset.book_id is None
        assert asset.chapter_id is None
        assert asset.user_parent_id is None

    def test_all_asset_types(self):
        """Verify all asset types are valid."""
        asset_types = ["image", "text", "audio", "video", "document", "archive", "other"]

        for asset_type in asset_types:
            asset = Asset(
                id="asset123",
                date_created="2024-01-15T10:30:00Z",
                date_modified="2024-01-15T10:30:00Z",
                asset_type=asset_type,
                mime_type="application/octet-stream",
                original_filename="file.bin",
                public_url="https://example.com/file.bin",
                uploaded_by_id="user123",
                company_id="company123",
            )
            assert asset.asset_type == asset_type


class TestNote:
    """Tests for Note model."""

    def test_valid_note(self):
        """Verify valid note creation."""
        note = Note(
            id="note123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            title="Test Note",
            content="This is a test note.",
        )

        assert note.id == "note123"
        assert note.title == "Test Note"
        assert note.content == "This is a test note."


class TestNoteCreate:
    """Tests for NoteCreate model."""

    def test_valid_request(self):
        """Verify valid request creation."""
        request = NoteCreate(
            title="Test Note",
            content="This is a test note.",
        )

        assert request.title == "Test Note"
        assert request.content == "This is a test note."

    def test_title_min_length(self):
        """Verify title minimum length validation."""
        with pytest.raises(PydanticValidationError):
            NoteCreate(title="ab", content="Valid content")

    def test_title_max_length(self):
        """Verify title maximum length validation."""
        with pytest.raises(PydanticValidationError):
            NoteCreate(title="a" * 51, content="Valid content")

    def test_content_min_length(self):
        """Verify content minimum length validation."""
        with pytest.raises(PydanticValidationError):
            NoteCreate(title="Valid title", content="ab")


class TestNoteUpdate:
    """Tests for NoteUpdate model."""

    def test_all_fields_optional(self):
        """Verify all fields default to None."""
        request = NoteUpdate()

        assert request.title is None
        assert request.content is None

    def test_partial_update(self):
        """Verify partial update works."""
        request = NoteUpdate(title="New Title")

        assert request.title == "New Title"
        assert request.content is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        request = NoteUpdate(title="New Title")

        data = request.model_dump(exclude_none=True)

        assert data == {"title": "New Title"}

    def test_update_explicit_none_for_constrained_fields(self):
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for constrained fields
        request = NoteUpdate(title=None, content=None)

        # Then: Fields are None without validation errors
        assert request.title is None
        assert request.content is None

    def test_update_constrained_fields_still_validate_non_none(self):
        """Verify constraints still apply when a non-None value is provided."""
        with pytest.raises(PydanticValidationError):
            NoteUpdate(title="ab")

        with pytest.raises(PydanticValidationError):
            NoteUpdate(content="ab")


class TestRollStatistics:
    """Tests for RollStatistics model."""

    def test_valid_statistics(self):
        """Verify valid statistics creation."""
        stats = RollStatistics(
            botches=5,
            successes=50,
            failures=30,
            criticals=15,
            total_rolls=100,
            average_difficulty=6.5,
            average_pool=4.2,
            top_traits=[{"name": "Strength", "count": 20}],
            criticals_percentage=15.0,
            success_percentage=50.0,
            failure_percentage=30.0,
            botch_percentage=5.0,
        )

        assert stats.botches == 5
        assert stats.successes == 50
        assert stats.failures == 30
        assert stats.criticals == 15
        assert stats.total_rolls == 100
        assert stats.average_difficulty == 6.5
        assert stats.average_pool == 4.2
        assert len(stats.top_traits) == 1
        assert stats.criticals_percentage == 15.0

    def test_optional_fields_default_to_none(self):
        """Verify optional fields default correctly."""
        stats = RollStatistics(
            botches=5,
            successes=50,
            failures=30,
            criticals=15,
            total_rolls=100,
            criticals_percentage=15.0,
            success_percentage=50.0,
            failure_percentage=30.0,
            botch_percentage=5.0,
        )

        assert stats.average_difficulty is None
        assert stats.average_pool is None
        assert stats.top_traits == []


class TestGiftAttributes:
    """Tests for GiftAttributes model."""

    def test_valid_gift_attributes(self):
        """Verify valid GiftAttributes creation with all fields."""
        attrs = GiftAttributes(
            renown="HONOR",
            cost="1 Rage",
            duration="1 scene",
            minimum_renown=2,
            is_native_gift=True,
            tribe_id="tribe123",
            auspice_id="auspice123",
        )

        assert attrs.renown == "HONOR"
        assert attrs.cost == "1 Rage"
        assert attrs.duration == "1 scene"
        assert attrs.minimum_renown == 2
        assert attrs.is_native_gift is True
        assert attrs.tribe_id == "tribe123"
        assert attrs.auspice_id == "auspice123"

    def test_gift_attributes_defaults(self):
        """Verify GiftAttributes optional fields default correctly."""
        attrs = GiftAttributes(renown="GLORY")

        assert attrs.renown == "GLORY"
        assert attrs.cost is None
        assert attrs.duration is None
        assert attrs.minimum_renown is None
        assert attrs.is_native_gift is False
        assert attrs.tribe_id is None
        assert attrs.auspice_id is None


class TestTraitPower:
    """Tests for TraitPower model."""

    def test_valid_named_power(self):
        """Verify TraitPower creation with all fields."""
        power = TraitPower(
            id="power123",
            level=2,
            name="Feral Whispers",
            description="Communicate with animals.",
            system="Roll Manipulation + Animal Ken.",
            link="https://example.com/feral-whispers",
        )

        assert power.id == "power123"
        assert power.level == 2
        assert power.name == "Feral Whispers"
        assert power.description == "Communicate with animals."
        assert power.system == "Roll Manipulation + Animal Ken."
        assert power.link == "https://example.com/feral-whispers"

    def test_nameless_dot_descriptor(self):
        """Verify TraitPower optional fields default to None for nameless dot descriptors."""
        power = TraitPower(id="power123", level=3)

        assert power.level == 3
        assert power.name is None
        assert power.description is None
        assert power.system is None
        assert power.link is None


class TestTraitPowers:
    """Tests for Trait.powers field."""

    def test_trait_powers_empty_by_default(self):
        """Verify Trait.powers defaults to an empty list."""
        trait = Trait(
            id="trait123",
            name="Strength",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            sheet_section_id="section123",
            category_id="category123",
        )
        assert trait.powers == []

    def test_trait_with_multiple_powers_at_same_level(self):
        """Verify Trait accepts several powers sharing a level."""
        trait = Trait(
            id="trait123",
            name="Thaumaturgy",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            sheet_section_id="section123",
            category_id="category123",
            powers=[
                {"id": "power1", "level": 1, "name": "A Taste for Blood"},
                {"id": "power2", "level": 1, "name": "Rebel's Spark"},
            ],
        )

        assert len(trait.powers) == 2
        assert [p.name for p in trait.powers] == ["A Taste for Blood", "Rebel's Spark"]
        assert all(p.level == 1 for p in trait.powers)


class TestTraitGiftAttributes:
    """Tests for Trait.gift_attributes field."""

    def test_trait_gift_attributes_none_by_default(self):
        """Verify Trait.gift_attributes defaults to None."""
        trait = Trait(
            id="trait123",
            name="Strength",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            sheet_section_id="section123",
            category_id="category123",
        )
        assert trait.gift_attributes is None

    def test_trait_with_gift_attributes(self):
        """Verify Trait accepts GiftAttributes."""
        attrs = GiftAttributes(renown="WISDOM")
        trait = Trait(
            id="trait123",
            name="Spirit Sight",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            sheet_section_id="section123",
            category_id="category123",
            gift_attributes=attrs,
        )
        assert trait.gift_attributes is not None
        assert trait.gift_attributes.renown == "WISDOM"
