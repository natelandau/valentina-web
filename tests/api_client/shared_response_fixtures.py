"""Shared response fixtures."""

from collections.abc import Callable

import pytest


@pytest.fixture
def note_response_data() -> dict:
    """Return sample note response data."""
    return {
        "id": "note123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "title": "Test Note",
        "content": "This is test content",
    }


@pytest.fixture
def statistics_response_data() -> dict:
    """Return sample statistics response data."""
    return {
        "botches": 5,
        "successes": 50,
        "failures": 30,
        "criticals": 15,
        "total_rolls": 100,
        "average_difficulty": 6.5,
        "average_pool": 4.2,
        "top_traits": [{"name": "Strength", "count": 20}],
        "criticals_percentage": 15.0,
        "success_percentage": 50.0,
        "failure_percentage": 30.0,
        "botch_percentage": 5.0,
    }


@pytest.fixture
def asset_response_data_factory() -> Callable[..., dict]:
    """Return a factory for creating sample asset response data.

    Call with keyword arguments to set context-specific fields like filename
    and parent IDs. All parent ID fields default to None.
    """

    def _create(
        *,
        original_filename: str = "test.png",
        public_url: str = "https://example.com/test.png",
        character_id: str | None = None,
        campaign_id: str | None = None,
        book_id: str | None = None,
        chapter_id: str | None = None,
        user_parent_id: str | None = None,
    ) -> dict:
        return {
            "id": "asset123",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "asset_type": "image",
            "mime_type": "image/png",
            "original_filename": original_filename,
            "public_url": public_url,
            "uploaded_by_id": "user123",
            "company_id": "company123",
            "character_id": character_id,
            "campaign_id": campaign_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "user_parent_id": user_parent_id,
        }

    return _create


@pytest.fixture
def trait_response_data() -> dict:
    """Return sample trait response data."""
    return {
        "id": "trait123",
        "name": "Strength",
        "description": "Physical power and might",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "link": None,
        "show_when_zero": True,
        "max_value": 5,
        "min_value": 0,
        "initial_cost": 1,
        "upgrade_cost": 2,
        "sheet_section_name": "Attributes",
        "sheet_section_id": "section123",
        "category_name": "Physical",
        "category_id": "cat123",
        "custom_for_character_id": None,
        "subcategory_id": None,
        "subcategory_name": None,
        "pool": None,
        "system": None,
        "is_rollable": True,
        "powers": [
            {
                "id": "power1",
                "level": 1,
                "name": None,
                "description": "Barely able to lift a chair.",
                "system": None,
                "link": None,
            },
            {
                "id": "power2",
                "level": 2,
                "name": None,
                "description": "Average human strength.",
                "system": None,
                "link": None,
            },
        ],
        "character_classes": ["VAMPIRE", "WEREWOLF"],
        "game_versions": ["V5"],
    }


@pytest.fixture
def character_trait_response_data(trait_response_data: dict) -> dict:
    """Return sample character trait response data."""
    return {
        "id": "ct123",
        "character_id": "char123",
        "value": 3,
        "trait": trait_response_data,
        "specialties": [
            {
                "id": "spec123",
                "name": "Knives",
                "date_created": "2024-01-15T10:30:00Z",
                "date_modified": "2024-01-15T10:30:00Z",
            }
        ],
    }


@pytest.fixture
def character_response_data() -> dict:
    """Return sample character response data."""
    return {
        "id": "char123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "date_killed": None,
        "character_class": "VAMPIRE",
        "type": "PLAYER",
        "game_version": "V5",
        "status": "ALIVE",
        "starting_points": 0,
        "name_first": "John",
        "name_last": "Doe",
        "name_nick": "Johnny",
        "name": "Johnny",
        "name_full": "John Doe",
        "age": 35,
        "date_of_birth": "1888-06-15",
        "biography": "A mysterious vampire.",
        "demeanor": "Friendly",
        "nature": "Warrior",
        "concept_id": "concept123",
        "user_creator_id": "user123",
        "user_player_id": "user456",
        "company_id": "company123",
        "campaign_id": "campaign123",
        "asset_ids": ["asset1", "asset2"],
        "character_trait_ids": ["trait1", "trait2"],
        "chapter_ids": ["chap1"],
        "specialties": [
            {
                "id": "spec1",
                "name": "Brawl: Kindred",
                "type": "ACTION",
                "description": "Skilled in fighting other Kindred",
            }
        ],
        "vampire_attributes": {
            "clan_id": "clan123",
            "clan_name": "Ventrue",
            "generation": 10,
            "sire": "Ancient One",
            "bane": {"name": "Rarefied Tastes", "description": "Feeds only on specific blood"},
            "compulsion": None,
        },
        "werewolf_attributes": None,
        "mage_attributes": None,
        "hunter_attributes": None,
        "is_temporary": False,
    }


@pytest.fixture
def user_response_data() -> dict:
    """Return sample user response data."""
    return {
        "id": "507f1f77bcf86cd799439011",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name_first": "Test",
        "name_last": "User",
        "username": "testuser",
        "email": "test@example.com",
        "role": "PLAYER",
        "company_id": "company123",
        "discord_profile": {
            "id": "discord123",
            "username": "testuser",
        },
        "google_profile": {
            "id": "google123",
            "email": "test@gmail.com",
            "verified_email": True,
            "username": "testuser",
        },
        "github_profile": {
            "id": "github123",
            "login": "testuser",
            "username": "testuser",
            "email": "test@github.com",
        },
        "apple_profile": {
            "id": "001234.abcd5678",
            "email": "test@privaterelay.appleid.com",
            "fullname": "Test User",
        },
        "campaign_experience": [
            {"campaign_id": "campaign1", "xp_current": 50, "xp_total": 100, "cool_points": 5}
        ],
        "asset_ids": ["asset1"],
    }


@pytest.fixture
def company_response_data() -> dict:
    """Return sample company response data."""
    return {
        "id": "507f1f77bcf86cd799439011",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name": "Test Company",
        "description": "A test company",
        "email": "test@example.com",
        "resources_modified_at": "2024-01-15T10:30:00Z",
        "settings": {
            "character_autogen_xp_cost": 10,
            "character_autogen_num_choices": 3,
            "character_autogen_starting_points": 5,
            "permission_manage_campaign": "UNRESTRICTED",
            "permission_manage_npc": "UNRESTRICTED",
            "permission_grant_xp": "UNRESTRICTED",
            "permission_free_trait_changes": "UNRESTRICTED",
            "permission_recoup_xp": "UNRESTRICTED",
            "specialty_xp_cost_enabled": False,
        },
    }


@pytest.fixture
def paginated_companies_response(company_response_data: dict) -> dict:
    """Return sample paginated companies response."""
    return {
        "items": [company_response_data],
        "limit": 10,
        "offset": 0,
        "total": 1,
    }


@pytest.fixture
def health_response_data() -> dict:
    """Return sample health response data."""
    return {
        "database_status": "online",
        "cache_status": "online",
        "database_latency_ms": 1.2,
        "cache_latency_ms": 0.5,
        "uptime": "3d 12h 45m",
        "version": "0.7.0",
    }
