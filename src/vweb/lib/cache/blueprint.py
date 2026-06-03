"""Global blueprint trait cache.

Every blueprint trait is fetched once and cached as a dict keyed by trait ID, then
consumers filter client-side by game_version, character_class, etc. The reference
catalog endpoints page at 1000 items per request, so a cold-cache fill pulls the full
set (~750 traits, ~500 KB) in a single API request before caching it for the full TTL.
Single-flight ensures only one request performs that fill.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from flask import session
from vclient import sync_character_blueprint_service

from vweb.constants import CACHE_BLUEPRINT_TTL
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import Trait, TraitSubcategory

_CACHE_BLUEPRINT_ALL_TRAITS_PREFIX: Final[str] = "bp_all_traits:"
_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_PREFIX: Final[str] = "bp_all_sheet_sections:"

_STRATEGY = base.PureTTL(ttl=CACHE_BLUEPRINT_TTL)


def _traits_key() -> str:
    return f"{_CACHE_BLUEPRINT_ALL_TRAITS_PREFIX}{session['company_id']}"


def _sections_key() -> str:
    return f"{_CACHE_BLUEPRINT_ALL_SHEET_SECTIONS_PREFIX}{session['company_id']}"


def traits() -> dict[str, Trait]:
    """Return the company's blueprint traits keyed by trait ID (1-hour TTL, per company)."""
    return base.cached_fetch(_traits_key(), _fetch_traits, _STRATEGY)


def trait(trait_id: str) -> Trait | None:
    """Look up a single blueprint trait by ID from the global cache.

    Args:
        trait_id: The blueprint trait ID to look up.

    Returns:
        The Trait model, or None if the ID is not found.
    """
    return traits().get(trait_id)


def subcategories() -> dict[str, TraitSubcategory]:
    """Return the company's blueprint sheet sections keyed by ID (1-hour TTL, per company)."""
    return base.cached_fetch(_sections_key(), _fetch_subcategories, _STRATEGY)


def subcategory(subcategory_id: str) -> TraitSubcategory | None:
    """Return a single blueprint subcategory by ID from the global cache.

    Args:
        subcategory_id: The blueprint subcategory ID to look up.

    Returns:
        The TraitSubcategory model, or None if the ID is not found.
    """
    return subcategories().get(subcategory_id)


def clear() -> None:
    """Remove the current company's cached blueprint dicts (traits + subcategories)."""
    base.clear_key(_traits_key(), _sections_key())


def _fetch_traits() -> dict[str, Trait]:
    return {
        t.id: t
        for t in sync_character_blueprint_service(
            company_id=session["company_id"]
        ).list_all_traits()
    }


def _fetch_subcategories() -> dict[str, TraitSubcategory]:
    return {
        sc.id: sc
        for sc in sync_character_blueprint_service(
            company_id=session["company_id"]
        ).list_all_subcategories()
    }
