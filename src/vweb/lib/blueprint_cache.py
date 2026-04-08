"""Global blueprint trait cache.

All ~300 blueprint traits are fetched once and cached as a dict keyed by trait ID.
Consumers filter client-side by game_version, character_class, etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient import sync_character_blueprint_service

from vweb.extensions import cache

_CACHE_BLUEPRINT_ALL_TRAITS_KEY: str = "bp_all_traits"
_CACHE_BLUEPRINT_TTL: int = 60 * 60  # 1 hour
_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_KEY: str = "bp_all_sheet_sections"


if TYPE_CHECKING:
    from vclient.models import Trait, TraitSubcategory


def get_all_subcategories() -> dict[str, TraitSubcategory]:
    """Return all blueprint sheet sections as a dict keyed by sheet section ID."""
    cached: dict[str, TraitSubcategory] | None = cache.get(_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_KEY)
    if cached is not None:
        return cached
    subcategories = sync_character_blueprint_service().list_all_subcategories()
    result = {sc.id: sc for sc in subcategories}
    cache.set(_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_KEY, result, timeout=_CACHE_BLUEPRINT_TTL)
    return result


def get_subcategory(subcategory_id: str) -> TraitSubcategory | None:
    """Return a single blueprint subcategory by ID from the global cache."""
    return get_all_subcategories().get(subcategory_id)


def get_all_traits() -> dict[str, Trait]:
    """Return all blueprint traits as a dict keyed by trait ID.

    Fetches from the API on cache miss via ``list_all_traits()`` with no filters.
    Cached with 1-hour TTL. Shared across all users and requests.

    Returns:
        Mapping of trait ID to Trait model.
    """
    cached: dict[str, Trait] | None = cache.get(_CACHE_BLUEPRINT_ALL_TRAITS_KEY)
    if cached is not None:
        return cached

    traits = sync_character_blueprint_service().list_all_traits()
    result = {t.id: t for t in traits}
    cache.set(_CACHE_BLUEPRINT_ALL_TRAITS_KEY, result, timeout=_CACHE_BLUEPRINT_TTL)
    return result


def get_trait(trait_id: str) -> Trait | None:
    """Look up a single blueprint trait by ID from the global cache.

    Args:
        trait_id: The blueprint trait ID to look up.

    Returns:
        The Trait model, or None if the ID is not found.
    """
    return get_all_traits().get(trait_id)


def clear_blueprint_cache() -> None:
    """Remove the cached traits dict, forcing a fresh API fetch on next access."""
    cache.delete(_CACHE_BLUEPRINT_ALL_TRAITS_KEY)
