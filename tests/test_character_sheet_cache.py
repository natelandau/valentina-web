"""Tests for the character sheet cache module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models.full_sheet import CharacterFullSheet
from vclient.testing import CharacterFullSheetFactory

from tests.helpers import make_cache_store_mock
from vweb.constants import CACHE_CHARACTER_FULL_SHEET_PREFIX
from vweb.lib.cache.character_sheet import clear, get

if TYPE_CHECKING:
    from flask import Flask


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for character_sheet cache."""
    return make_cache_store_mock(mocker, "vweb.lib.cache.base.cache")


@pytest.fixture
def mock_char_svc(mocker) -> MagicMock:
    """Mock the sync_characters_service factory."""
    svc = MagicMock()
    svc.get_full_sheet.return_value = CharacterFullSheetFactory.build()
    mocker.patch("vweb.lib.cache.character_sheet.sync_characters_service", return_value=svc)
    return svc


class TestGet:
    """Tests for get()."""

    def test_fetches_from_api_on_cache_miss(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify get calls the API when the cache is empty."""
        # Given an empty cache and a session with company_id
        # When fetching the character sheet
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            result = get("char-1", "user-1")

        # Then a CharacterFullSheet is returned and the API is hit once with correct args
        assert isinstance(result, CharacterFullSheet)
        mock_char_svc.get_full_sheet.assert_called_once_with(
            "char-1", include_available_traits=False
        )

    def test_returns_cached_on_hit(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify a second call returns the cached value without re-calling the API."""
        # Given one populated fetch
        # When fetching twice
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            first = get("char-1", "user-1")
            second = get("char-1", "user-1")

        # Then both share the cached instance and the API was called only once
        assert first is second
        mock_char_svc.get_full_sheet.assert_called_once()

    def test_include_available_traits_true_uses_distinct_key(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify include_available_traits=True and False produce separate cache entries."""
        # Given two distinct sheets returned in sequence
        sheet_without = CharacterFullSheetFactory.build()
        sheet_with = CharacterFullSheetFactory.build()
        mock_char_svc.get_full_sheet.side_effect = [sheet_without, sheet_with]

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"

            # When fetching with include_available_traits=False then True
            result_false = get("char-1", "user-1", include_available_traits=False)
            result_true = get("char-1", "user-1", include_available_traits=True)

        # Then both API calls were made because the keys differ
        assert mock_char_svc.get_full_sheet.call_count == 2
        assert result_false is not result_true

        # Then the cache holds separate entries for each flag
        key_false = f"{CACHE_CHARACTER_FULL_SHEET_PREFIX}char-1:False"
        key_true = f"{CACHE_CHARACTER_FULL_SHEET_PREFIX}char-1:True"
        assert key_false in mock_cache_store
        assert key_true in mock_cache_store

    def test_on_behalf_of_not_part_of_cache_key(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify different requesting_user_id values share the same cache entry."""
        # Given a cached result for user-1
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            get("char-1", "user-1")
            # When a different user requests the same character sheet
            get("char-1", "user-2")

        # Then the API was hit only once, proving user ID is not part of the key
        mock_char_svc.get_full_sheet.assert_called_once()


class TestClear:
    """Tests for clear()."""

    def test_evicts_both_variants_on_clear(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify clear evicts both the True and False key variants for a character."""
        # Given both cache variants are primed with distinct sheets
        sheets = [CharacterFullSheetFactory.build() for _ in range(4)]
        mock_char_svc.get_full_sheet.side_effect = sheets

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"

            # Prime both variants
            get("char-1", "user-1", include_available_traits=False)
            get("char-1", "user-1", include_available_traits=True)
            assert mock_char_svc.get_full_sheet.call_count == 2

            # When the cache is cleared
            clear("char-1")

            # Then both variants are re-fetched on the next access
            get("char-1", "user-1", include_available_traits=False)
            get("char-1", "user-1", include_available_traits=True)

        # Then the API was called four times total (2 cold, 2 after clear)
        assert mock_char_svc.get_full_sheet.call_count == 4

    def test_clear_does_not_evict_other_characters(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify clear only removes keys for the specified character, not others."""
        # Given both char-1 and char-2 are cached
        mock_char_svc.get_full_sheet.return_value = CharacterFullSheetFactory.build()

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            get("char-1", "user-1")
            get("char-2", "user-1")
            assert mock_char_svc.get_full_sheet.call_count == 2

            # When only char-1 is cleared
            clear("char-1")

            # Then char-2 is still cached (no additional API call)
            get("char-2", "user-1")

        assert mock_char_svc.get_full_sheet.call_count == 2

    def test_forces_refetch_after_clear(
        self, app: Flask, mock_cache_store: dict, mock_char_svc: MagicMock
    ) -> None:
        """Verify clearing the cache forces a fresh API fetch on next access."""
        # Given two distinct API responses in sequence
        sheet_v1 = CharacterFullSheetFactory.build()
        sheet_v2 = CharacterFullSheetFactory.build()
        mock_char_svc.get_full_sheet.side_effect = [sheet_v1, sheet_v2]

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"

            # When fetching, clearing, then fetching again
            first = get("char-1", "user-1")
            clear("char-1")
            second = get("char-1", "user-1")

        # Then different objects are returned after the clear
        assert first is not second
        assert mock_char_svc.get_full_sheet.call_count == 2
