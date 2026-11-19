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

    def test_fetches_once_then_serves_cache(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify the sheet is fetched once, without available traits, then served from cache."""
        with app.test_request_context("/"):
            seed_session()
            first = get("char-1")
            second = get("char-1")

        assert isinstance(first, CharacterFullSheet)
        assert first is second
        (request,) = fake_vclient.assert_called(
            Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=1
        )
        assert "include_available_traits" not in request.query

    def test_include_available_traits_is_cached_separately(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify the sheet with available traits is a separate entry, fetched with the flag."""
        with app.test_request_context("/"):
            seed_session()
            result_false = get("char-1", include_available_traits=False)
            result_true = get("char-1", include_available_traits=True)

        assert result_false is not result_true
        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=2)
        fake_vclient.assert_called(
            Routes.CHARACTERS_FULL_SHEET,
            params=CHAR_1,
            query={"include_available_traits": "true"},
            times=1,
        )

    def test_requesting_user_not_part_of_cache_key(
        self, app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
    ) -> None:
        """Verify different requesting users share the same cache entry."""
        with app.test_request_context("/"):
            seed_session(user_id="user-1")
            get("char-1")
            session["user_id"] = "user-2"
            get("char-1")

        fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, times=1)


def test_clear_evicts_every_variant_of_only_that_character(
    app: Flask, mock_cache_store: dict, fake_vclient: FakeVClient
) -> None:
    """Verify clear refetches both variants of the cleared character and keeps others cached."""
    with app.test_request_context("/"):
        seed_session()
        get("char-1", include_available_traits=False)
        get("char-1", include_available_traits=True)
        get("char-2")

        clear("char-1")

        get("char-1", include_available_traits=False)
        get("char-1", include_available_traits=True)
        get("char-2")

    fake_vclient.assert_called(Routes.CHARACTERS_FULL_SHEET, params=CHAR_1, times=4)
    fake_vclient.assert_called(
        Routes.CHARACTERS_FULL_SHEET, params={"character_id": "char-2"}, times=1
    )


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
