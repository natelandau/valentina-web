"""Global dictionary term cache.

All dictionary terms are fetched once and cached as a sorted list. Consumers filter
client-side for search results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import session
from vclient import sync_dictionary_service

from vweb.constants import CACHE_DICTIONARY_KEY, CACHE_DICTIONARY_TTL
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm

_STRATEGY = base.PureTTL(ttl=CACHE_DICTIONARY_TTL)


def terms() -> list[DictionaryTerm]:
    """Return all dictionary terms sorted alphabetically (1-hour TTL, shared)."""
    return base.cached_fetch(CACHE_DICTIONARY_KEY, _fetch, _STRATEGY)


def term(term_id: str) -> DictionaryTerm | None:
    """Look up a single dictionary term by ID from the global cache."""
    return next((t for t in terms() if t.id == term_id), None)


def search(query: str, *, include_synonyms: bool = True) -> list[DictionaryTerm]:
    """Filter cached terms by case-insensitive substring on name and optionally synonyms."""
    if not query:
        return terms()

    q = query.lower()
    return [
        t
        for t in terms()
        if q in t.term.lower() or (include_synonyms and any(q in s.lower() for s in t.synonyms))
    ]


def clear() -> None:
    """Remove the cached terms, forcing a fresh API fetch on next access."""
    base.clear_key(CACHE_DICTIONARY_KEY)


def _fetch() -> list[DictionaryTerm]:
    result = sync_dictionary_service(company_id=session["company_id"]).list_all()
    result.sort(key=lambda t: t.term.lower())
    return result
