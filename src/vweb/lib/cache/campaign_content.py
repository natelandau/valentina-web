"""Lazy, scoped caches for campaign books and chapters.

Books and chapters are NOT loaded into the request-scoped GlobalContext (that eager
fan-out caused rate-limit storms). They are fetched on demand here, only by the routes
and the audit-log resolver that render them.

Invalidation mirrors GlobalContext: values carry the company ``resources_modified_at``
stamp and are only served while the stamp matches (TimestampValidated), keeping other
users eventually consistent. Because the stamp's bump semantics are not guaranteed,
mutation handlers also call ``clear`` so the acting user sees their own edit next
request. Keys are scoped to company+campaign (books) / company+book (chapters) WITHOUT
a requesting-user component: this content is campaign-wide, and a user who cannot see a
campaign never reaches these accessors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g, session
from vclient import sync_books_service, sync_chapters_service

from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import CampaignBook, CampaignChapter

_CACHE_TTL_SECONDS = 60 * 60  # safety-net only; correctness from stamp + explicit clear
_STRATEGY = base.TimestampValidated(
    ttl=_CACHE_TTL_SECONDS,
    current_stamp=lambda: g.global_context.resources_modified_at,
)


def _books_key(company_id: str, campaign_id: str) -> str:
    return f"books:{company_id}:{campaign_id}"


def _chapters_key(company_id: str, book_id: str) -> str:
    return f"chapters:{company_id}:{book_id}"


def books(campaign_id: str) -> list[CampaignBook]:
    """Return a campaign's books sorted by number, from a lazy per-campaign cache."""
    company_id = session["company_id"]

    def fetch() -> list[CampaignBook]:
        result = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=g.requesting_user.id, company_id=company_id
        ).list_all()
        return sorted(result, key=lambda book: book.number)

    return base.cached_fetch(_books_key(company_id, campaign_id), fetch, _STRATEGY)


def chapters(campaign_id: str, book_id: str) -> list[CampaignChapter]:
    """Return a book's chapters sorted by number, from a lazy per-book cache.

    Args:
        campaign_id: The campaign the book belongs to (required to scope the API call).
        book_id: The book whose chapters to return.
    """
    company_id = session["company_id"]

    def fetch() -> list[CampaignChapter]:
        result = sync_chapters_service(
            campaign_id=campaign_id,
            book_id=book_id,
            on_behalf_of=g.requesting_user.id,
            company_id=company_id,
        ).list_all()
        return sorted(result, key=lambda chapter: chapter.number)

    return base.cached_fetch(_chapters_key(company_id, book_id), fetch, _STRATEGY)


def clear(company_id: str, *, campaign_id: str | None = None, book_id: str | None = None) -> None:
    """Evict the books and/or chapters cache for a scope after a mutation.

    Args:
        company_id: The company the scope belongs to.
        campaign_id: When given, evict that campaign's books cache.
        book_id: When given, evict that book's chapters cache.

    Raises:
        ValueError: If neither campaign_id nor book_id is provided.
    """
    if campaign_id is None and book_id is None:
        msg = "Provide at least one of campaign_id or book_id to clear."
        raise ValueError(msg)
    if campaign_id is not None:
        base.clear_key(_books_key(company_id, campaign_id))
    if book_id is not None:
        base.clear_key(_chapters_key(company_id, book_id))
