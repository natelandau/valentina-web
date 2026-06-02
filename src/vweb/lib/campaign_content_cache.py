"""Lazy, scoped caches for campaign books and chapters.

Books and chapters are NOT loaded into the request-scoped GlobalContext (that
eager fan-out caused rate-limit storms). They are fetched on demand here, only by
the routes and the audit-log resolver that actually render them.

Invalidation mirrors GlobalContext: cache values carry the company
``resources_modified_at`` stamp and are only returned when the stamp still matches,
which keeps other users eventually consistent. Because the stamp's bump semantics
are not guaranteed, mutation handlers also call ``clear_campaign_content_cache`` so
the acting user always sees their own edit on the next request.

Cache keys are scoped to ``company + campaign`` (books) and ``company + book``
(chapters) WITHOUT a requesting-user component. This is deliberate and safe: books
and chapters are campaign-wide content, not per-user-filtered data, and a user who
cannot see a campaign never reaches these accessors (campaign membership is enforced
earlier via the global context / ``fetch_campaign_or_404``). Contrast with the
dice-rolls cache and the global context, which ARE per-user keyed because they carry
user-visibility-filtered data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g, session
from vclient import sync_books_service, sync_chapters_service

from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import CampaignBook, CampaignChapter

# Safety-net TTL only; correctness comes from the stamp + explicit clear.
_CACHE_TTL_SECONDS = 60 * 60  # 1 hour


def _books_key(company_id: str, campaign_id: str) -> str:
    return f"books:{company_id}:{campaign_id}"


def _chapters_key(company_id: str, book_id: str) -> str:
    return f"chapters:{company_id}:{book_id}"


def get_books_for_campaign(campaign_id: str) -> list[CampaignBook]:
    """Return a campaign's books, sorted by number, from a lazy per-campaign cache.

    Fetch from the API on a cold cache or when the company timestamp has advanced.

    Args:
        campaign_id: The campaign whose books to return.

    Returns:
        The campaign's books ordered by ``number`` ascending.
    """
    company_id = session["company_id"]
    stamp = g.global_context.resources_modified_at
    key = _books_key(company_id, campaign_id)

    cached = cache.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    books = sync_books_service(
        campaign_id=campaign_id, on_behalf_of=g.requesting_user.id, company_id=company_id
    ).list_all()
    books = sorted(books, key=lambda book: book.number)
    cache.set(key, (stamp, books), timeout=_CACHE_TTL_SECONDS)
    return books


def get_chapters_for_book(campaign_id: str, book_id: str) -> list[CampaignChapter]:
    """Return a book's chapters, sorted by number, from a lazy per-book cache.

    Fetch from the API on a cold cache or when the company timestamp has advanced.

    Args:
        campaign_id: The campaign the book belongs to (required to scope the API call).
        book_id: The book whose chapters to return.

    Returns:
        The book's chapters ordered by ``number`` ascending.
    """
    company_id = session["company_id"]
    stamp = g.global_context.resources_modified_at
    key = _chapters_key(company_id, book_id)

    cached = cache.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    chapters = sync_chapters_service(
        campaign_id=campaign_id,
        book_id=book_id,
        on_behalf_of=g.requesting_user.id,
        company_id=company_id,
    ).list_all()
    chapters = sorted(chapters, key=lambda chapter: chapter.number)
    cache.set(key, (stamp, chapters), timeout=_CACHE_TTL_SECONDS)
    return chapters


def clear_campaign_content_cache(
    company_id: str, *, campaign_id: str | None = None, book_id: str | None = None
) -> None:
    """Evict the books and/or chapters cache for a scope after a mutation.

    Call alongside ``clear_global_context_cache`` wherever a book or chapter is
    created, updated, or deleted so the acting user sees the change immediately.

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
        cache.delete(_books_key(company_id, campaign_id))
    if book_id is not None:
        cache.delete(_chapters_key(company_id, book_id))
