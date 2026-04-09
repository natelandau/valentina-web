"""Global dictionary term cache.

All dictionary terms are fetched once and cached as a sorted list.
Consumers filter client-side for search results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import session
from vclient import sync_dictionary_service

from vweb.constants import CACHE_DICTIONARY_KEY, CACHE_DICTIONARY_TTL
from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm


def get_all_terms() -> list[DictionaryTerm]:
    """Return all dictionary terms sorted alphabetically by term name.

    Fetches from the API on cache miss. Cached with 1-hour TTL, shared
    across all users and requests.

    Returns:
        Sorted list of DictionaryTerm models.
    """
    cached: list[DictionaryTerm] | None = cache.get(CACHE_DICTIONARY_KEY)
    if cached is not None:
        return cached

    terms = sync_dictionary_service(company_id=session["company_id"]).list_all()
    terms.sort(key=lambda t: t.term.lower())
    cache.set(CACHE_DICTIONARY_KEY, terms, timeout=CACHE_DICTIONARY_TTL)
    return terms


def get_term(term_id: str) -> DictionaryTerm | None:
    """Look up a single dictionary term by ID from the global cache.

    Args:
        term_id: The dictionary term ID to look up.

    Returns:
        The DictionaryTerm model, or None if the ID is not found.
    """
    return next((t for t in get_all_terms() if t.id == term_id), None)


def search_terms(query: str, *, include_synonyms: bool = True) -> list[DictionaryTerm]:
    """Filter cached terms by case-insensitive substring match on term name and optionally synonyms.

    Args:
        query: Search string to match against term names (and synonyms if enabled).
        include_synonyms: When True, also match against each term's synonyms list.

    Returns:
        Filtered list of matching DictionaryTerm models, preserving sort order.
    """
    if not query:
        return get_all_terms()

    q = query.lower()
    return [
        t
        for t in get_all_terms()
        if q in t.term.lower() or (include_synonyms and any(q in s.lower() for s in t.synonyms))
    ]


def clear_dictionary_cache() -> None:
    """Remove the cached terms, forcing a fresh API fetch on next access."""
    cache.delete(CACHE_DICTIONARY_KEY)
