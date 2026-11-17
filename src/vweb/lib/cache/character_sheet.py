"""Cached full character-sheet retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from vweb.constants import CACHE_CHARACTER_FULL_SHEET_TTL
from vweb.lib import api_services
from vweb.lib.cache import base

if TYPE_CHECKING:
    from collections.abc import Callable

    from vweb.api_client.models import CharacterFullSheet

_CACHE_CHARACTER_FULL_SHEET_PREFIX: Final[str] = "char_full_sheet:"
_STRATEGY = base.ShortTTL(ttl=CACHE_CHARACTER_FULL_SHEET_TTL)


def get(character_id: str, *, include_available_traits: bool = False) -> CharacterFullSheet:
    """Return a character's full sheet, fetching on cache miss (60s TTL, per character).

    Args:
        character_id: The character whose sheet to return.
        include_available_traits: Whether to include available traits in the sheet.

    Returns:
        The character's full sheet.
    """
    # Sheet content is per-character, not per-viewer, so the requesting user is not in the key
    key = f"{_CACHE_CHARACTER_FULL_SHEET_PREFIX}{character_id}:{include_available_traits}"
    return base.cached_fetch(
        key,
        lambda: api_services.characters().get_full_sheet(
            character_id, include_available_traits=include_available_traits
        ),
        _STRATEGY,
    )


def _variant_keys(character_id: str) -> tuple[str, str]:
    prefix = f"{_CACHE_CHARACTER_FULL_SHEET_PREFIX}{character_id}"
    return f"{prefix}:{True}", f"{prefix}:{False}"


def update(character_id: str, apply: Callable[[CharacterFullSheet], None]) -> None:
    """Apply a local change to every cached sheet variant for a character, without fetching.

    Use after an API write that returns the new state, so the next sheet read is served
    from the cache instead of a full-sheet fetch. Variants that are not cached are skipped.

    Args:
        character_id: The character whose cached sheets to change.
        apply: Callable that mutates a sheet in place.
    """
    for key in _variant_keys(character_id):
        base.update_key(key, apply, _STRATEGY)


def clear(character_id: str) -> None:
    """Evict both sheet variants (with and without available traits) for a character."""
    base.clear_key(*_variant_keys(character_id))
