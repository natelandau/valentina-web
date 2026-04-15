"""Character sheet service for cached full-sheet retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import session
from vclient import sync_characters_service

from vweb.constants import CACHE_CHARACTER_FULL_SHEET_PREFIX, CACHE_CHARACTER_FULL_SHEET_TTL
from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import Character, CharacterFullSheet, User


class CharacterSheetService:
    """A service for building a character sheet."""

    def __init__(self, character: Character, requesting_user: User):
        self.character = character
        self.requesting_user = requesting_user
        self.cache_key = f"{CACHE_CHARACTER_FULL_SHEET_PREFIX}{self.character.id}"

    def get_full_sheet(self, *, include_available_traits: bool = False) -> CharacterFullSheet:
        """Get the full character sheet.

        Args:
            include_available_traits: Whether to include available traits in the sheet.

        Returns:
            A character full sheet object.
        """
        cache_key = f"{self.cache_key}:{include_available_traits}"
        full_sheet = cache.get(cache_key)
        if full_sheet is not None:
            return full_sheet

        full_sheet = sync_characters_service(
            on_behalf_of=self.requesting_user.id,
            company_id=session["company_id"],
        ).get_full_sheet(self.character.id, include_available_traits=include_available_traits)

        cache.set(cache_key, full_sheet, timeout=CACHE_CHARACTER_FULL_SHEET_TTL)
        return full_sheet

    def clear_cache(self) -> None:
        """Clear the cache."""
        cache.delete(f"{self.cache_key}:{True}")
        cache.delete(f"{self.cache_key}:{False}")
