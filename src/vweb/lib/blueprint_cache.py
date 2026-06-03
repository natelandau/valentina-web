"""Global blueprint trait cache.

All ~300 blueprint traits are fetched once and cached as a dict keyed by trait ID.
Consumers filter client-side by game_version, character_class, etc.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from flask import session
from vclient import sync_character_blueprint_service

from vweb.extensions import cache

if TYPE_CHECKING:
    from collections.abc import Callable

    from vclient.models import Trait, TraitSubcategory

_CACHE_BLUEPRINT_ALL_TRAITS_KEY: str = "bp_all_traits"
_CACHE_BLUEPRINT_TTL: int = 60 * 60  # 1 hour
_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_KEY: str = "bp_all_sheet_sections"

# Single-flight locks: on a cold cache, collapse concurrent fetches of the shared
# blueprint dictionaries into one instead of each request re-fetching all traits.
_traits_lock = threading.Lock()
_subcategories_lock = threading.Lock()


def _get_cached_dict[T](
    cache_key: str, lock: threading.Lock, fetch: Callable[[], dict[str, T]]
) -> dict[str, T]:
    """Return a cached dict, building it under a single-flight lock on a cold cache.

    A lock-free fast path serves warm reads. On a miss, one caller acquires the lock
    and builds while concurrent callers wait and reuse the result, preventing a
    cold-cache stampede that re-fetches the whole blueprint dictionary N times.

    Args:
        cache_key: Cache key under which the built dict is stored.
        lock: Single-flight lock guarding the cold-cache build for this key.
        fetch: Callable that builds the dict on a cache miss.

    Returns:
        The cached dict, built once on a cold cache.
    """
    cached: dict[str, T] | None = cache.get(cache_key)
    if cached is not None:
        return cached
    with lock:
        cached = cache.get(cache_key)  # double-check: another caller may have just built it
        if cached is not None:
            return cached
        result = fetch()
        cache.set(cache_key, result, timeout=_CACHE_BLUEPRINT_TTL)
        return result


def get_all_subcategories() -> dict[str, TraitSubcategory]:
    """Return all blueprint sheet sections as a dict keyed by sheet section ID.

    Cached for 1 hour and shared across all users; a single-flight lock collapses
    concurrent cold-cache fetches into one.
    """
    return _get_cached_dict(
        _CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_KEY,
        _subcategories_lock,
        lambda: {
            sc.id: sc
            for sc in sync_character_blueprint_service(
                company_id=session["company_id"]
            ).list_all_subcategories()
        },
    )


def get_subcategory(subcategory_id: str) -> TraitSubcategory | None:
    """Return a single blueprint subcategory by ID from the global cache."""
    return get_all_subcategories().get(subcategory_id)


def get_all_traits() -> dict[str, Trait]:
    """Return all blueprint traits as a dict keyed by trait ID.

    Fetches all traits via ``list_all_traits()`` on a cold cache (1-hour TTL, shared
    across users). A single-flight lock collapses concurrent cold-cache fetches into
    one instead of each request re-fetching the full trait list.

    Returns:
        Mapping of trait ID to Trait model.
    """
    return _get_cached_dict(
        _CACHE_BLUEPRINT_ALL_TRAITS_KEY,
        _traits_lock,
        lambda: {
            trait.id: trait
            for trait in sync_character_blueprint_service(
                company_id=session["company_id"]
            ).list_all_traits()
        },
    )


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
