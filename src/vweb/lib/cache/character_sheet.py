"""Cached full character-sheet retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from flask import session
from vclient import sync_characters_service

from vweb.constants import CACHE_CHARACTER_FULL_SHEET_TTL
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import CharacterFullSheet

_CACHE_CHARACTER_FULL_SHEET_PREFIX: Final[str] = "char_full_sheet:"
_STRATEGY = base.ShortTTL(ttl=CACHE_CHARACTER_FULL_SHEET_TTL)


def get(
    character_id: str,
    requesting_user_id: str,
    *,
    include_available_traits: bool = False,
) -> CharacterFullSheet:
    """Return a character's full sheet, fetching on cache miss (60s TTL, per character).

    Args:
        character_id: The character whose sheet to return.
        requesting_user_id: The user the API call is made on behalf of.
        include_available_traits: Whether to include available traits in the sheet.

    Returns:
        The character's full sheet.
    """
    # requesting_user_id is the on_behalf_of caller only; sheet content is per-character, not per-viewer, so it is intentionally not part of the key
    key = f"{_CACHE_CHARACTER_FULL_SHEET_PREFIX}{character_id}:{include_available_traits}"
    return base.cached_fetch(
        key,
        lambda: sync_characters_service(
            on_behalf_of=requesting_user_id,
            company_id=session["company_id"],
        ).get_full_sheet(character_id, include_available_traits=include_available_traits),
        _STRATEGY,
    )


def clear(character_id: str) -> None:
    """Evict both sheet variants (with and without available traits) for a character."""
    prefix = f"{_CACHE_CHARACTER_FULL_SHEET_PREFIX}{character_id}"
    base.clear_key(f"{prefix}:{True}", f"{prefix}:{False}")
