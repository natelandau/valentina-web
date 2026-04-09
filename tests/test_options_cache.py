"""Tests for global API options cache."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from tests.helpers import make_cache_store_mock
from vweb.lib.options_cache import (
    ApiOptions,
    AssetOptions,
    CharacterOptions,
    CompanyOptions,
    GameplayOptions,
    UserOptions,
    _parse_options,
    clear_options_cache,
    get_options,
)

if TYPE_CHECKING:
    from flask import Flask

SAMPLE_RAW: dict = {
    "companies": {
        "CompanyPermission": ["USER", "ADMIN", "OWNER"],
        "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
        "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
        "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
    },
    "characters": {
        "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
        "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
        "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
        "CharacterStatus": ["ALIVE", "DEAD"],
        "CharacterType": ["PLAYER", "NPC", "STORYTELLER", "DEVELOPER"],
        "GameVersion": ["V4", "V5"],
        "HunterCreed": ["ENTREPRENEURIAL", "FAITHFUL"],
        "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
        "InventoryItemType": ["BOOK", "CONSUMABLE", "ENCHANTED", "EQUIPMENT", "OTHER", "WEAPON"],
        "SpecialtyType": ["ACTION", "OTHER"],
        "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
        "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
        "_related": {"traits": "http://example.com/traits"},
    },
    "users": {
        "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED"],
    },
    "gameplay": {
        "DiceSize": [4, 6, 8, 10, 20, 100],
        "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
    },
}


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for options_cache."""
    return make_cache_store_mock(mocker, "vweb.lib.options_cache.cache")


@pytest.fixture
def mock_options_svc(mocker):
    """Mock the sync_options_service factory."""
    svc = MagicMock()
    svc.get_options.return_value = SAMPLE_RAW
    mocker.patch("vweb.lib.options_cache.sync_options_service", return_value=svc)
    return svc


class TestParseOptions:
    """Tests for _parse_options()."""

    def test_parses_all_categories(self) -> None:
        """Verify _parse_options creates a fully populated ApiOptions."""
        result = _parse_options(SAMPLE_RAW)

        assert isinstance(result, ApiOptions)
        assert isinstance(result.companies, CompanyOptions)
        assert isinstance(result.characters, CharacterOptions)
        assert isinstance(result.users, UserOptions)
        assert isinstance(result.gameplay, GameplayOptions)
        assert isinstance(result.assets, AssetOptions)

    def test_parses_company_options(self) -> None:
        """Verify company permission lists are correctly mapped."""
        result = _parse_options(SAMPLE_RAW)

        assert result.companies.company_permission == ["USER", "ADMIN", "OWNER"]
        assert result.companies.permission_manage_campaign == ["UNRESTRICTED", "STORYTELLER"]

    def test_parses_character_options(self) -> None:
        """Verify character enumerations are correctly mapped."""
        result = _parse_options(SAMPLE_RAW)

        assert "VAMPIRE" in result.characters.character_class
        assert result.characters.character_type == ["PLAYER", "NPC", "STORYTELLER", "DEVELOPER"]
        assert result.characters.inventory_item_type == [
            "BOOK",
            "CONSUMABLE",
            "ENCHANTED",
            "EQUIPMENT",
            "OTHER",
            "WEAPON",
        ]

    def test_parses_gameplay_options(self) -> None:
        """Verify dice sizes are parsed as integers."""
        result = _parse_options(SAMPLE_RAW)

        assert result.gameplay.dice_size == [4, 6, 8, 10, 20, 100]
        assert all(isinstance(d, int) for d in result.gameplay.dice_size)

    def test_ignores_related_urls(self) -> None:
        """Verify _related keys in characters are ignored (not mapped to any field)."""
        result = _parse_options(SAMPLE_RAW)

        # _related is not a field on CharacterOptions, so it's silently skipped
        assert not hasattr(result.characters, "_related")

    def test_handles_empty_response(self) -> None:
        """Verify _parse_options handles an empty dict gracefully."""
        result = _parse_options({})

        assert result.companies.company_permission == []
        assert result.characters.character_class == []
        assert result.gameplay.dice_size == []


class TestGetOptions:
    """Tests for get_options()."""

    def test_fetches_from_api_on_cache_miss(
        self, app: Flask, mock_cache_store: dict, mock_options_svc: MagicMock
    ) -> None:
        """Verify get_options calls the API when the cache is empty."""
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_options()

        assert isinstance(result, ApiOptions)
        assert result.characters.character_class == [
            "VAMPIRE",
            "WEREWOLF",
            "MAGE",
            "HUNTER",
            "GHOUL",
            "MORTAL",
        ]
        mock_options_svc.get_options.assert_called_once()

    def test_returns_cached_on_hit(
        self, app: Flask, mock_cache_store: dict, mock_options_svc: MagicMock
    ) -> None:
        """Verify get_options returns cached value without calling the API again."""
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            first = get_options()
            second = get_options()

        assert first is second
        mock_options_svc.get_options.assert_called_once()

    def test_caches_with_correct_key(
        self, app: Flask, mock_cache_store: dict, mock_options_svc: MagicMock
    ) -> None:
        """Verify the cached value is stored under the expected key."""
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            get_options()

        assert "api_options" in mock_cache_store
        assert isinstance(mock_cache_store["api_options"], ApiOptions)


class TestClearOptionsCache:
    """Tests for clear_options_cache()."""

    def test_forces_refetch_on_next_call(
        self, app: Flask, mock_cache_store: dict, mock_options_svc: MagicMock
    ) -> None:
        """Verify clear_options_cache forces a fresh API fetch on next access."""
        raw_v2 = {
            **SAMPLE_RAW,
            "characters": {**SAMPLE_RAW["characters"], "CharacterClass": ["VAMPIRE"]},
        }
        mock_options_svc.get_options.side_effect = [SAMPLE_RAW, raw_v2]

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            first = get_options()
            assert len(first.characters.character_class) == 6

            clear_options_cache()

            second = get_options()
            assert len(second.characters.character_class) == 1

        assert mock_options_svc.get_options.call_count == 2
