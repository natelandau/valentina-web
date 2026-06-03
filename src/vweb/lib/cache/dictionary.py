"""Per-company dictionary term cache.

All of a company's dictionary terms are fetched once and cached as a sorted list.
The endpoint is company-scoped, so the cache key includes the company id. Consumers
filter client-side for search results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from flask import session
from vclient import sync_dictionary_service

from vweb.constants import CACHE_DICTIONARY_TTL
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm

# v2: the cached value now bundles an id index alongside the sorted list, so an
# old list-shaped value from a rolling deploy must not be read under this key.
_CACHE_DICTIONARY_PREFIX: Final[str] = "dictionary_terms_v2:"
_STRATEGY = base.PureTTL(ttl=CACHE_DICTIONARY_TTL)


def _key() -> str:
    return f"{_CACHE_DICTIONARY_PREFIX}{session['company_id']}"


@dataclass(frozen=True)
class _DictionaryCache:
    """Cached dictionary in both shapes its consumers need, built once per fetch."""

    ordered: list[DictionaryTerm]  # sorted by term name, for list/search rendering
    by_id: dict[str, DictionaryTerm]  # O(1) single-term lookup, mirrors blueprint.traits()


def _load() -> _DictionaryCache:
    return base.cached_fetch(_key(), _fetch, _STRATEGY)


def terms() -> list[DictionaryTerm]:
    """Return all dictionary terms sorted alphabetically (1-hour TTL, shared)."""
    return _load().ordered


def term(term_id: str) -> DictionaryTerm | None:
    """Look up a single dictionary term by ID from the global cache."""
    return _load().by_id.get(term_id)


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
    """Remove the current company's cached terms, forcing a fresh API fetch."""
    base.clear_key(_key())


def _fetch() -> _DictionaryCache:
    result = sync_dictionary_service(company_id=session["company_id"]).list_all()
    result.sort(key=lambda t: t.term.lower())
    return _DictionaryCache(ordered=result, by_id={t.id: t for t in result})
