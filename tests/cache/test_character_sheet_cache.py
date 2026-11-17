"""Tests for the character sheet cache module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from flask import session

from tests.helpers import seed_session
from vweb.api_client.models.full_sheet import CharacterFullSheet
from vweb.api_client.testing import FakeVClient, Routes
from vweb.lib.cache.character_sheet import clear, get, update

if TYPE_CHECKING:
    from flask import Flask

CHAR_1 = {"company_id": "test-company-id", "character_id": "char-1"}


class TestGet:
    """Tests for get()."""

    def test_fetches_from_api_on_cache_miss(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify get calls the API when the cache is empty."""
        # Given an empty cache and a session with company_id
        # When fetching the character sheet
        with app.test_request_context("/"):
            seed_session()
            result = get("char-1")

        # Then a CharacterFullSheet is returned and the API is hit once without available traits
        assert isinstance(result, CharacterFullSheet)
        (request,) = fake_vclient.assert_called(
            Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=1
        )
        assert "include_available_traits" not in request.query

    def test_returns_cached_on_hit(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify a second call returns the cached value without re-calling the API."""
        # Given one populated fetch
        # When fetching twice
        with app.test_request_context("/"):
            seed_session()
            first = get("char-1")
            second = get("char-1")

        # Then both share the cached instance and the API was called only once
        assert first is second
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, times=1)

    def test_include_available_traits_true_uses_distinct_key(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify include_available_traits=True and False produce separate cache entries."""
        with app.test_request_context("/"):
            seed_session()

            # When fetching with include_available_traits=False then True
            result_false = get("char-1", include_available_traits=False)
            result_true = get("char-1", include_available_traits=True)

        # Then both API calls were made because the keys differ, one asking for available traits
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=2)
        fake_vclient.assert_called(
            Routes.CHARACTERS_FULL_SHEET,
            params=CHAR_1,
            query={"include_available_traits": "true"},
            times=1,
        )
        assert result_false is not result_true

        # Then the cache holds separate entries for each flag
        key_false = "char_full_sheet:char-1:False"
        key_true = "char_full_sheet:char-1:True"
        assert key_false in mock_cache_store
        assert key_true in mock_cache_store

    def test_requesting_user_not_part_of_cache_key(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify different requesting users share the same cache entry."""
        # Given a cached result for user-1
        with app.test_request_context("/"):
            seed_session(user_id="user-1")
            get("char-1")
            # When a different user requests the same character sheet
            session["user_id"] = "user-2"
            get("char-1")

        # Then the API was hit only once, proving user ID is not part of the key
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, times=1)


class TestClear:
    """Tests for clear()."""

    def test_evicts_both_variants_on_clear(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify clear evicts both the True and False key variants for a character."""
        with app.test_request_context("/"):
            seed_session()

            # Given both cache variants are primed
            get("char-1", include_available_traits=False)
            get("char-1", include_available_traits=True)
            fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, times=2)

            # When the cache is cleared
            clear("char-1")

            # Then both variants are re-fetched on the next access
            get("char-1", include_available_traits=False)
            get("char-1", include_available_traits=True)

        # Then the API was called four times total (2 cold, 2 after clear)
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=4)

    def test_clear_does_not_evict_other_characters(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify clear only removes keys for the specified character, not others."""
        with app.test_request_context("/"):
            seed_session()

            # Given both char-1 and char-2 are cached
            get("char-1")
            get("char-2")

            # When only char-1 is cleared
            clear("char-1")

            # Then char-2 is still cached (no additional API call)
            get("char-2")

        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=1)
        fake_vclient.assert_called(
            Routes.CHARACTERS_FULL_SHEET, params={"character_id": "char-2"}, times=1
        )

    def test_forces_refetch_after_clear(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify clearing the cache forces a fresh API fetch on next access."""
        with app.test_request_context("/"):
            seed_session()

            # When fetching, clearing, then fetching again
            first = get("char-1")
            clear("char-1")
            second = get("char-1")

        # Then different objects are returned after the clear
        assert first is not second
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=2)


class TestUpdate:
    """Tests for update()."""

    def test_rewrites_every_cached_variant_without_fetching(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify update changes both cached variants and makes no API call."""
        with app.test_request_context("/"):
            seed_session()

            # Given both variants are cached
            get("char-1", include_available_traits=False)
            get("char-1", include_available_traits=True)

            # When updating the character's name in place
            update("char-1", lambda sheet: setattr(sheet.character, "name_first", "Changed"))

            # Then both variants read back changed with no further fetch
            without = get("char-1", include_available_traits=False)
            with_traits = get("char-1", include_available_traits=True)

        assert without.character.name_first == "Changed"
        assert with_traits.character.name_first == "Changed"
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, times=2)

    def test_skips_uncached_sheet(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify update on a cold cache neither fetches nor stores anything."""
        apply = MagicMock()

        with app.test_request_context("/"):
            update("char-1", apply)

        apply.assert_not_called()
        fake_vclient.assert_not_called(Routes.CHARACTERS_FULL_SHEET)
        assert mock_cache_store == {}
