"""Tests for vweb.api_client.api.models.users."""

import typing

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.constants import IdentityResolutionType
from vweb.api_client.models import (
    AppleProfile,
    Asset,
    CampaignExperience,
    DiscordProfile,
    GitHubProfile,
    GoogleProfile,
    IdentityResolution,
    Note,
    NoteCreate,
    NoteUpdate,
    Quickroll,
    QuickrollCreate,
    QuickrollUpdate,
    RollStatistics,
    User,
    UserApproveDTO,
    UserCreate,
    UserIdentifyDTO,
    UserIdentityLinkDTO,
    UserUpdate,
)


class TestDiscordProfile:
    """Tests for DiscordProfile model."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None."""
        # When: Creating profile with no arguments
        profile = DiscordProfile()

        # Then: All values are None
        assert profile.id is None
        assert profile.username is None
        assert profile.global_name is None
        assert profile.avatar_id is None
        assert profile.avatar_url is None
        assert profile.discriminator is None
        assert profile.email is None
        assert profile.verified is None

    def test_partial_profile(self):
        """Verify partial profile creation."""
        # When: Creating profile with some values
        profile = DiscordProfile(
            id="123456789",
            username="testuser",
            verified=True,
        )

        # Then: Specified values are set, others are None
        assert profile.id == "123456789"
        assert profile.username == "testuser"
        assert profile.verified is True
        assert profile.global_name is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        # Given: Profile with some values set
        profile = DiscordProfile(
            id="123456789",
            username="testuser",
        )

        # When: Dumping with exclude_none
        data = profile.model_dump(exclude_none=True)

        # Then: Only non-None values are included
        assert data == {
            "id": "123456789",
            "username": "testuser",
        }


class TestGoogleProfile:
    """Tests for GoogleProfile model."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None."""
        # When: Creating profile with no arguments
        profile = GoogleProfile()

        # Then: All values are None
        assert profile.id is None
        assert profile.email is None
        assert profile.verified_email is None
        assert profile.username is None
        assert profile.name_first is None
        assert profile.name_last is None
        assert profile.avatar_url is None
        assert profile.locale is None

    def test_partial_profile(self):
        """Verify partial profile creation."""
        # When: Creating profile with some values
        profile = GoogleProfile(
            id="google123",
            email="user@gmail.com",
            verified_email=True,
        )

        # Then: Specified values are set, others are None
        assert profile.id == "google123"
        assert profile.email == "user@gmail.com"
        assert profile.verified_email is True
        assert profile.username is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        # Given: Profile with some values set
        profile = GoogleProfile(
            id="google123",
            email="user@gmail.com",
        )

        # When: Dumping with exclude_none
        data = profile.model_dump(exclude_none=True)

        # Then: Only non-None values are included
        assert data == {
            "id": "google123",
            "email": "user@gmail.com",
        }


class TestGitHubProfile:
    """Tests for GitHubProfile model."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None."""
        # When: Creating profile with no arguments
        profile = GitHubProfile()

        # Then: All values are None
        assert profile.id is None
        assert profile.login is None
        assert profile.username is None
        assert profile.avatar_url is None
        assert profile.email is None
        assert profile.profile_url is None

    def test_partial_profile(self):
        """Verify partial profile creation."""
        # When: Creating profile with some values
        profile = GitHubProfile(
            id="github123",
            login="testuser",
            email="test@github.com",
        )

        # Then: Specified values are set, others are None
        assert profile.id == "github123"
        assert profile.login == "testuser"
        assert profile.email == "test@github.com"
        assert profile.username is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        # Given: Profile with some values set
        profile = GitHubProfile(
            id="github123",
            login="testuser",
        )

        # When: Dumping with exclude_none
        data = profile.model_dump(exclude_none=True)

        # Then: Only non-None values are included
        assert data == {
            "id": "github123",
            "login": "testuser",
        }


class TestAppleProfile:
    """Tests for AppleProfile model."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None."""
        # When: Creating profile with no arguments
        profile = AppleProfile()

        # Then: All values are None
        assert profile.id is None
        assert profile.email is None
        assert profile.fullname is None

    def test_partial_profile(self):
        """Verify partial profile creation."""
        # When: Creating profile with some values
        profile = AppleProfile(
            id="apple123",
            email="user@privaterelay.appleid.com",
        )

        # Then: Specified values are set, others are None
        assert profile.id == "apple123"
        assert profile.email == "user@privaterelay.appleid.com"
        assert profile.fullname is None

    def test_model_dump_excludes_none(self):
        """Verify model_dump with exclude_none works correctly."""
        # Given: Profile with some values set
        profile = AppleProfile(
            id="apple123",
            fullname="Test User",
        )

        # When: Dumping with exclude_none
        data = profile.model_dump(exclude_none=True)

        # Then: Only non-None values are included
        assert data == {
            "id": "apple123",
            "fullname": "Test User",
        }


class TestCampaignExperience:
    """Tests for CampaignExperience model."""

    def test_defaults(self):
        """Verify default values for experience fields."""
        # When: Creating experience with only the required fields
        exp = CampaignExperience(id="exp123", user_id="user123", campaign_id="campaign123")

        # Then: Defaults are set correctly
        assert exp.id == "exp123"
        assert exp.user_id == "user123"
        assert exp.campaign_id == "campaign123"
        assert exp.xp_current == 0
        assert exp.xp_total == 0
        assert exp.cool_points == 0

    def test_full_experience(self):
        """Verify creating experience with all fields."""
        # When: Creating experience with all fields
        exp = CampaignExperience(
            id="exp123",
            user_id="user123",
            campaign_id="campaign123",
            xp_current=50,
            xp_total=100,
            cool_points=5,
        )

        # Then: All fields are set correctly
        assert exp.campaign_id == "campaign123"
        assert exp.xp_current == 50
        assert exp.xp_total == 100
        assert exp.cool_points == 5


class TestUser:
    """Tests for User model."""

    def test_minimal_user(self):
        """Verify creating user with required fields only."""
        # When: Creating user with required fields
        user = User(
            id="user123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name_first="Test",
            name_last="User",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
            company_id="company123",
        )

        # Then: User is created correctly with defaults
        assert user.id == "user123"
        assert user.name_first == "Test"
        assert user.name_last == "User"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.company_id == "company123"
        assert user.role == "PLAYER"
        assert user.discord_profile is None
        assert user.google_profile is None
        assert user.github_profile is None
        assert user.apple_profile is None
        assert user.campaign_experience == []

    def test_full_user(self):
        """Verify creating user with all fields populated."""
        # Given: Nested objects
        discord = DiscordProfile(id="discord123", username="testuser")
        google = GoogleProfile(id="google123", email="user@gmail.com")
        github = GitHubProfile(id="github123", login="testuser")
        apple = AppleProfile(id="apple123", email="full@privaterelay.appleid.com")
        experience = CampaignExperience(
            id="exp1", user_id="user123", campaign_id="campaign1", xp_current=50
        )

        # When: Creating user with all fields
        user = User(
            id="user123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name_first="Full",
            name_last="User",
            username="fulluser",
            email="full@example.com",
            role="PLAYER",
            company_id="company123",
            discord_profile=discord,
            google_profile=google,
            github_profile=github,
            apple_profile=apple,
            campaign_experience=[experience],
        )

        # Then: All fields are set correctly
        assert user.role == "PLAYER"
        assert user.discord_profile.id == "discord123"
        assert user.google_profile.id == "google123"
        assert user.github_profile.id == "github123"
        assert user.apple_profile.id == "apple123"
        assert len(user.campaign_experience) == 1
        assert user.campaign_experience[0].xp_current == 50

    def test_user_from_api_response(self):
        """Verify creating user from API response dict."""
        # Given: API response data
        data = {
            "id": "507f1f77bcf86cd799439011",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "name_first": "API",
            "name_last": "User",
            "username": "apiuser",
            "email": "api@example.com",
            "role": "STORYTELLER",
            "company_id": "company123",
            "discord_profile": {
                "id": "discord123",
                "username": "apiuser",
            },
            "google_profile": {
                "id": "google123",
                "email": "apiuser@gmail.com",
                "verified_email": True,
            },
            "github_profile": {
                "id": "github123",
                "login": "apiuser",
            },
            "apple_profile": {
                "id": "apple123",
                "email": "apiuser@privaterelay.appleid.com",
                "fullname": "API User",
            },
            "campaign_experience": [
                {
                    "id": "exp1",
                    "user_id": "507f1f77bcf86cd799439011",
                    "campaign_id": "campaign1",
                    "xp_current": 100,
                    "xp_total": 200,
                    "cool_points": 10,
                }
            ],
        }

        # When: Creating user from dict
        user = User.model_validate(data)

        # Then: User is created correctly
        assert user.id == "507f1f77bcf86cd799439011"
        assert user.name_first == "API"
        assert user.name_last == "User"
        assert user.username == "apiuser"
        assert user.role == "STORYTELLER"
        assert user.discord_profile.username == "apiuser"
        assert user.google_profile.email == "apiuser@gmail.com"
        assert user.github_profile.login == "apiuser"
        assert user.apple_profile.fullname == "API User"
        assert user.campaign_experience[0].xp_current == 100

    def test_invalid_role_rejected(self):
        """Verify invalid role values are rejected by Pydantic."""
        # When/Then: Creating user with invalid role raises error
        with pytest.raises(PydanticValidationError):
            User(
                id="user123",
                date_created="2024-01-15T10:30:00Z",
                date_modified="2024-01-15T10:30:00Z",
                name_first="Test",
                name_last="User",
                username="testuser",
                email="test@example.com",
                role="INVALID",
                company_id="company123",
            )

    def test_child_resource_counts(self):
        """Verify child-resource count fields default to 0 and accept values."""
        # Given: base required fields for a User
        base_kwargs = {
            "id": "user123",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "username": "testuser",
            "email": "test@example.com",
            "role": "PLAYER",
            "company_id": "company123",
        }

        # When: creating a User without count fields
        defaults = User(**base_kwargs)

        # Then: all count fields default to 0
        assert defaults.num_quickrolls == 0
        assert defaults.num_notes == 0
        assert defaults.num_assets == 0
        assert defaults.num_characters == 0

        # When: creating a User with explicit count values
        populated = User(
            **base_kwargs,
            num_quickrolls=2,
            num_notes=3,
            num_assets=1,
            num_characters=5,
        )

        # Then: count fields reflect the provided values
        assert populated.num_quickrolls == 2
        assert populated.num_notes == 3
        assert populated.num_assets == 1
        assert populated.num_characters == 5

    def test_avatar_url_defaults_to_none(self):
        """Verify avatar_url is optional and defaults to None when absent."""
        # Given: base required fields for a User
        user = User(
            id="user123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
            company_id="company123",
        )

        # Then: avatar_url defaults to None
        assert user.avatar_url is None

    def test_avatar_url_accepts_string(self):
        """Verify avatar_url accepts a CloudFront-style URL string."""
        # When: Creating a user with an avatar_url
        user = User(
            id="user123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
            company_id="company123",
            avatar_url="https://cdn.example.com/a.webp",
        )

        # Then: avatar_url reflects the provided value
        assert user.avatar_url == "https://cdn.example.com/a.webp"


class TestUserCreate:
    """Tests for UserCreate model."""

    def test_minimal_request(self):
        """Verify creating request with required fields only."""
        # When: Creating request with required fields
        request = UserCreate(
            name_first="Test",
            name_last="User",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
        )

        # Then: Request is created correctly
        assert request.name_first == "Test"
        assert request.name_last == "User"
        assert request.username == "testuser"
        assert request.email == "test@example.com"
        assert request.role == "PLAYER"

    def test_name_validation_min_length(self):
        """Verify name minimum length validation."""
        # When/Then: Creating request with name too short raises error
        with pytest.raises(PydanticValidationError):
            UserCreate(
                name_first="AB",
                username="ab",
                email="test@example.com",
                role="PLAYER",
            )

    def test_name_validation_max_length(self):
        """Verify name maximum length validation."""
        # When/Then: Creating request with name too long raises error
        with pytest.raises(PydanticValidationError):
            UserCreate(
                name_first="A" * 51,
                username="a" * 51,
                email="test@example.com",
                role="PLAYER",
            )

    def test_model_dump_excludes_unset(self):
        """Verify model_dump with exclude_unset excludes unset fields."""
        # Given: Request with required fields only
        request = UserCreate(
            name_first="Test",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
        )

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only set fields are included
        assert data == {
            "name_first": "Test",
            "username": "testuser",
            "email": "test@example.com",
            "role": "PLAYER",
        }

    def test_deactivated_role_accepted(self):
        """Verify DEACTIVATED is accepted on UserCreate and UserUpdate and round-trips."""
        # When: Creating UserCreate and UserUpdate with role DEACTIVATED
        created = UserCreate(
            name_first="Test",
            username="testuser",
            email="test@example.com",
            role="DEACTIVATED",
        )
        updated = UserUpdate(role="DEACTIVATED")

        # Then: Models accept and round-trip the value (server-side hierarchy rules
        # are not enforced client-side — that's the server's job)
        assert created.role == "DEACTIVATED"
        assert updated.role == "DEACTIVATED"
        assert created.model_dump(exclude_none=True, mode="json")["role"] == "DEACTIVATED"
        assert updated.model_dump(exclude_none=True, mode="json")["role"] == "DEACTIVATED"


class TestUserUpdate:
    """Tests for UserUpdate model."""

    def test_empty_update_allowed(self):
        """Verify creating an empty update request is allowed."""
        # When: Creating an empty update request
        request = UserUpdate()

        # Then: All fields are None
        assert request.name_first is None
        assert request.name_last is None
        assert request.email is None
        assert request.role is None

    def test_partial_update(self):
        """Verify creating request with some fields."""
        # When: Creating request with name and role
        request = UserUpdate(
            name_first="Updated",
            name_last="Name",
            role="STORYTELLER",
        )

        # Then: Only specified fields are set
        assert request.name_first == "Updated"
        assert request.name_last == "Name"
        assert request.role == "STORYTELLER"
        assert request.email is None

    def test_model_dump_excludes_unset(self):
        """Verify model_dump with exclude_unset only includes set fields."""
        # Given: Request with only some fields set
        request = UserUpdate(
            name_first="Updated",
            name_last="Name",
        )

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only set fields are in the output
        assert data == {
            "name_first": "Updated",
            "name_last": "Name",
        }

    def test_update_explicit_none_for_constrained_fields(self):
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for constrained name field
        request = UserUpdate(name_first=None, name_last=None)

        # Then: Name is None without validation errors
        assert request.name_first is None
        assert request.name_last is None

    def test_update_constrained_fields_still_validate_non_none(self):
        """Verify constraints still apply when a non-None value is provided."""
        with pytest.raises(PydanticValidationError):
            UserUpdate(name_first="ab", name_last="ab")


class TestRollStatistics:
    """Tests for RollStatistics model."""

    def test_all_fields(self):
        """Verify creating statistics with all fields."""
        # When: Creating statistics
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

        # Then: All fields are set correctly
        assert stats.botches == 5
        assert stats.successes == 50
        assert stats.failures == 30
        assert stats.criticals == 15
        assert stats.total_rolls == 100
        assert stats.average_difficulty == 6.5
        assert stats.average_pool == 4.2
        assert len(stats.top_traits) == 1
        assert stats.criticals_percentage == 15.0
        assert stats.success_percentage == 50.0
        assert stats.failure_percentage == 30.0
        assert stats.botch_percentage == 5.0

    def test_statistics_from_api_response(self):
        """Verify creating statistics from API response dict."""
        # Given: API response data
        data = {
            "botches": 2,
            "successes": 80,
            "failures": 15,
            "criticals": 3,
            "total_rolls": 100,
            "average_difficulty": 6.0,
            "average_pool": 5.0,
            "top_traits": [{"name": "Dexterity", "count": 30}, {"name": "Wits", "count": 25}],
            "criticals_percentage": 3.0,
            "success_percentage": 80.0,
            "failure_percentage": 15.0,
            "botch_percentage": 2.0,
        }

        # When: Creating statistics from dict
        stats = RollStatistics.model_validate(data)

        # Then: Statistics are created correctly
        assert stats.total_rolls == 100
        assert len(stats.top_traits) == 2


class TestAsset:
    """Tests for Asset model."""

    def test_all_fields(self):
        """Verify creating asset with all fields."""
        # When: Creating asset
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

        # Then: All fields are set correctly
        assert asset.id == "asset123"
        assert asset.asset_type == "image"
        assert asset.mime_type == "image/png"
        assert asset.original_filename == "avatar.png"
        assert asset.public_url == "https://example.com/avatar.png"
        assert asset.uploaded_by_id == "user123"
        assert asset.company_id == "company123"
        assert asset.user_parent_id == "user123"

    def test_invalid_asset_type_rejected(self):
        """Verify invalid asset type is rejected."""
        # When/Then: Creating asset with invalid asset type raises error
        with pytest.raises(PydanticValidationError):
            Asset(
                id="asset123",
                date_created="2024-01-15T10:30:00Z",
                date_modified="2024-01-15T10:30:00Z",
                asset_type="invalid",
                mime_type="application/octet-stream",
                original_filename="file.txt",
                public_url="https://example.com/file.txt",
                uploaded_by_id="user123",
                company_id="company123",
            )


class TestNote:
    """Tests for Note model."""

    def test_all_fields(self):
        """Verify creating note with all fields."""
        # When: Creating note
        note = Note(
            id="note123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            title="My Note",
            content="This is the content of my note.",
            company_id="note-company-1",
            user_id="note-user-1",
            campaign_id="note-campaign-1",
            book_id="note-book-1",
            chapter_id="note-chapter-1",
            character_id="note-character-1",
        )

        # Then: All fields are set correctly
        assert note.id == "note123"
        assert note.title == "My Note"
        assert note.content == "This is the content of my note."
        assert note.company_id == "note-company-1"
        assert note.user_id == "note-user-1"
        assert note.campaign_id == "note-campaign-1"
        assert note.book_id == "note-book-1"
        assert note.chapter_id == "note-chapter-1"
        assert note.character_id == "note-character-1"


class TestNoteCreate:
    """Tests for NoteCreate model."""

    def test_required_fields(self):
        """Verify creating request with required fields."""
        # When: Creating request
        request = NoteCreate(
            title="Note Title",
            content="Note content here",
        )

        # Then: Fields are set correctly
        assert request.title == "Note Title"
        assert request.content == "Note content here"

    def test_title_min_length_validation(self):
        """Verify title minimum length validation."""
        # When/Then: Creating request with title too short raises error
        with pytest.raises(PydanticValidationError):
            NoteCreate(title="AB", content="Valid content")

    def test_content_min_length_validation(self):
        """Verify content minimum length validation."""
        # When/Then: Creating request with content too short raises error
        with pytest.raises(PydanticValidationError):
            NoteCreate(title="Valid Title", content="AB")


class TestNoteUpdate:
    """Tests for NoteUpdate model."""

    def test_empty_request(self):
        """Verify creating empty update request."""
        # When: Creating request with no fields
        request = NoteUpdate()

        # Then: All fields are None
        assert request.title is None
        assert request.content is None

    def test_partial_update(self):
        """Verify creating request with some fields."""
        # When: Creating request with only title
        request = NoteUpdate(title="Updated Title")

        # Then: Only title is set
        assert request.title == "Updated Title"
        assert request.content is None

    def test_model_dump_excludes_unset(self):
        """Verify model_dump with exclude_unset only includes set fields."""
        # Given: Request with only title set
        request = NoteUpdate(title="Updated Title")

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only title is in the output
        assert data == {"title": "Updated Title"}


class TestQuickroll:
    """Tests for Quickroll model."""

    def test_minimal_quickroll(self):
        """Verify creating quickroll with required fields."""
        # When: Creating quickroll with required fields
        quickroll = Quickroll(
            id="qr123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Quick Attack",
            user_id="user123",
        )

        # Then: Quickroll is created with defaults
        assert quickroll.id == "qr123"
        assert quickroll.name == "Quick Attack"
        assert quickroll.user_id == "user123"
        assert quickroll.description is None
        assert quickroll.trait_ids == []

    def test_full_quickroll(self):
        """Verify creating quickroll with all fields."""
        # When: Creating quickroll with all fields
        quickroll = Quickroll(
            id="qr123",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Quick Attack",
            description="A quick attack roll",
            user_id="user123",
            trait_ids=["trait1", "trait2"],
        )

        # Then: All fields are set correctly
        assert quickroll.description == "A quick attack roll"
        assert quickroll.trait_ids == ["trait1", "trait2"]


class TestQuickrollCreate:
    """Tests for QuickrollCreate model."""

    def test_minimal_request(self):
        """Verify creating request with required fields only."""
        # When: Creating request with name only
        request = QuickrollCreate(name="Quick Roll")

        # Then: Request is created with defaults
        assert request.name == "Quick Roll"
        assert request.description is None
        assert request.trait_ids == []

    def test_full_request(self):
        """Verify creating request with all fields."""
        # When: Creating request with all fields
        request = QuickrollCreate(
            name="Full Roll",
            description="A complete roll",
            trait_ids=["trait1", "trait2"],
        )

        # Then: All fields are set correctly
        assert request.name == "Full Roll"
        assert request.description == "A complete roll"
        assert request.trait_ids == ["trait1", "trait2"]

    def test_name_min_length_validation(self):
        """Verify name minimum length validation."""
        # When/Then: Creating request with name too short raises error
        with pytest.raises(PydanticValidationError):
            QuickrollCreate(name="AB")


class TestQuickrollUpdate:
    """Tests for QuickrollUpdate model."""

    def test_empty_request(self):
        """Verify creating empty update request."""
        # When: Creating request with no fields
        request = QuickrollUpdate()

        # Then: All fields are None
        assert request.name is None
        assert request.description is None
        assert request.trait_ids is None

    def test_partial_update(self):
        """Verify creating request with some fields."""
        # When: Creating request with name only
        request = QuickrollUpdate(name="Updated Name")

        # Then: Only name is set
        assert request.name == "Updated Name"
        assert request.description is None
        assert request.trait_ids is None

    def test_update_explicit_none_for_constrained_fields(self):
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for constrained fields
        request = QuickrollUpdate(name=None, description=None)

        # Then: Fields are None without validation errors
        assert request.name is None
        assert request.description is None

    def test_update_constrained_fields_still_validate_non_none(self):
        """Verify constraints still apply when a non-None value is provided."""
        with pytest.raises(PydanticValidationError):
            QuickrollUpdate(name="ab")

        with pytest.raises(PydanticValidationError):
            QuickrollUpdate(description="ab")


class TestQuickrollCreateConstraints:
    """Tests for QuickrollCreate optional field constraint handling."""

    def test_create_explicit_none_for_optional_constrained_fields(self):
        """Verify explicitly passing None for optional constrained fields does not raise."""
        # When: Creating a request with None for optional description
        request = QuickrollCreate(name="Test Roll", description=None)

        # Then: Description is None without validation errors
        assert request.description is None


class TestUserApproveDTO:
    """Tests for UserApproveDTO model."""

    def test_valid_request(self):
        """Verify creating approve request with valid fields."""
        # When: Creating an approve request
        request = UserApproveDTO(role="PLAYER")

        # Then: Fields are set correctly
        assert request.role == "PLAYER"

    def test_all_roles_accepted(self):
        """Verify all UserRole values are accepted."""
        # When: Creating approve requests with each role
        for role in ("ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"):
            request = UserApproveDTO(role=role)

            # Then: Role is set correctly
            assert request.role == role

    def test_invalid_role_rejected(self):
        """Verify invalid role values are rejected."""
        # When/Then: Creating request with invalid role raises error
        with pytest.raises(PydanticValidationError):
            UserApproveDTO(role="INVALID")

    def test_model_dump(self):
        """Verify model_dump produces correct output."""
        # Given: An approve request
        request = UserApproveDTO(role="STORYTELLER")

        # When: Dumping the model
        data = request.model_dump(mode="json")

        # Then: All fields are present
        assert data == {"role": "STORYTELLER"}


_VALID_USER_PAYLOAD = {
    "id": "user_1",
    "date_created": "2024-01-15T10:30:00Z",
    "date_modified": "2024-01-15T10:30:00Z",
    "username": "testuser",
    "email": "test@example.com",
    "role": "PLAYER",
    "company_id": "company_1",
}


class TestUserDetail:
    """Tests for UserDetail model."""

    def test_user_detail_defaults_embeds_to_none(self) -> None:
        """Verify all embed fields default to None when not provided."""
        from vweb.api_client.models import UserDetail

        detail = UserDetail.model_validate(_VALID_USER_PAYLOAD)
        assert detail.quickrolls is None
        assert detail.notes is None
        assert detail.assets is None
        assert detail.characters is None
        assert isinstance(detail, User)

    def test_user_detail_accepts_embedded_lists(self) -> None:
        """Verify UserDetail accepts embedded list resources."""
        from vweb.api_client.models import UserDetail

        payload = _VALID_USER_PAYLOAD | {
            "quickrolls": [],
            "notes": [],
            "assets": [],
            "characters": [],
        }
        detail = UserDetail.model_validate(payload)
        assert detail.quickrolls == []
        assert detail.notes == []
        assert detail.assets == []
        assert detail.characters == []

    def test_user_detail_rejects_wrong_embed_type(self) -> None:
        """Verify UserDetail rejects non-list embed values."""
        from vweb.api_client.models import UserDetail

        payload = _VALID_USER_PAYLOAD | {"quickrolls": "not-a-list"}
        with pytest.raises(PydanticValidationError):
            UserDetail.model_validate(payload)


class TestUserIdentifyDTO:
    """Tests for UserIdentifyDTO model."""

    def test_minimal_fields(self):
        """Verify provider and token are sufficient."""
        # When: Creating the DTO with only required fields
        dto = UserIdentifyDTO(provider="apple", token="eyJraWQi...")

        # Then: Optional fields default to None
        assert dto.provider == "apple"
        assert dto.token == "eyJraWQi..."
        assert dto.username is None
        assert dto.email is None

    def test_optional_create_fields(self):
        """Verify username and email are accepted for the create path."""
        # When: Creating the DTO with the optional create-only fields
        dto = UserIdentifyDTO(
            provider="github",
            token="gho_abc",
            username="octocat",
            email="octo@example.com",
        )

        # Then: All fields are set
        assert dto.username == "octocat"
        assert dto.email == "octo@example.com"

    def test_unknown_provider_rejected(self):
        """Verify an unsupported provider fails validation."""
        # When/Then: An unknown provider raises a validation error
        with pytest.raises(PydanticValidationError):
            UserIdentifyDTO(provider="myspace", token="x")

    def test_empty_token_rejected(self):
        """Verify an empty token fails validation."""
        # When/Then: An empty token raises a validation error
        with pytest.raises(PydanticValidationError):
            UserIdentifyDTO(provider="apple", token="")


class TestUserIdentityLinkDTO:
    """Tests for UserIdentityLinkDTO model."""

    def test_required_fields(self):
        """Verify provider and token are required and stored."""
        # When: Creating the DTO
        dto = UserIdentityLinkDTO(provider="discord", token="access-token")

        # Then: Fields are set
        assert dto.provider == "discord"
        assert dto.token == "access-token"

    def test_empty_token_rejected(self):
        """Verify an empty token fails validation."""
        # When/Then: An empty token raises a validation error
        with pytest.raises(PydanticValidationError):
            UserIdentityLinkDTO(provider="discord", token="")


class TestIdentityResolution:
    """Tests for IdentityResolution model."""

    @staticmethod
    def _user_data() -> dict:
        """Build a minimal valid user response payload."""
        return _VALID_USER_PAYLOAD | {"role": "UNAPPROVED"}

    @pytest.mark.parametrize("resolution", typing.get_args(IdentityResolutionType))
    def test_valid_resolutions(self, resolution):
        """Verify each resolution value parses with an embedded user."""
        # When: Validating an identify response
        result = IdentityResolution.model_validate(
            {"resolution": resolution, "user": self._user_data()}
        )

        # Then: The resolution and embedded user are parsed
        assert result.resolution == resolution
        assert isinstance(result.user, User)
        assert result.user.username == "testuser"

    def test_unknown_resolution_rejected(self):
        """Verify an unknown resolution value fails validation."""
        # When/Then: An unknown resolution raises a validation error
        with pytest.raises(PydanticValidationError):
            IdentityResolution.model_validate({"resolution": "upserted", "user": self._user_data()})
