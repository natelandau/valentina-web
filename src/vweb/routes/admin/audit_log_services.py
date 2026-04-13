"""Service-layer helpers for the admin audit log page.

Wraps the vclient audit log API and resolves entity IDs to human-readable
display names with optional navigation URLs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flask import session, url_for
from vclient import sync_companies_service

if TYPE_CHECKING:
    from vclient.models.audit_logs import AuditLog
    from vclient.models.pagination import PaginatedResponse

    from vweb.lib.global_context import GlobalContext


def get_audit_log_page(  # noqa: PLR0913
    *,
    limit: int = 20,
    offset: int = 0,
    entity_type: str = "",
    operation: str = "",
    acting_user_id: str = "",
    date_from: str = "",
    date_to: str = "",
) -> PaginatedResponse[AuditLog]:
    """Fetch a page of audit log entries for the current company.

    Empty-string filter values are omitted so the API returns unfiltered results
    for those dimensions. Date strings are parsed to datetime objects before
    forwarding.

    Args:
        limit: Maximum number of entries per page.
        offset: Number of entries to skip.
        entity_type: Filter by entity type (e.g. "USER", "CAMPAIGN").
        operation: Filter by operation (e.g. "CREATE", "UPDATE", "DELETE").
        acting_user_id: Filter by the user who performed the action.
        date_from: ISO date string for the start of the date range.
        date_to: ISO date string for the end of the date range.

    Returns:
        PaginatedResponse[AuditLog]: Paginated audit log entries.
    """
    kwargs: dict[str, object] = {"limit": limit, "offset": offset}

    if entity_type:
        kwargs["entity_type"] = entity_type
    if operation:
        kwargs["operation"] = operation
    if acting_user_id:
        kwargs["acting_user_id"] = acting_user_id
    if date_from:
        kwargs["date_from"] = datetime.fromisoformat(date_from)
    if date_to:
        kwargs["date_to"] = datetime.fromisoformat(date_to)

    company_id: str = session["company_id"]
    return sync_companies_service().get_audit_log_page(company_id, **kwargs)  # type: ignore[arg-type]


def resolve_entities(
    log: AuditLog,
    context: GlobalContext,
) -> list[tuple[str, str, str | None]]:
    """Map audit log entity IDs to display names and navigation URLs.

    Checks entity IDs in a fixed order (user, campaign, character, book, chapter)
    and resolves each present ID against the global context. Unresolvable IDs fall
    back to the raw ID string with no URL.

    Args:
        log: The audit log entry to resolve.
        context: The global context containing cached users, campaigns, characters, and books.

    Returns:
        List of (label, display_name, url_or_none) tuples for each present entity ID.
    """
    results: list[tuple[str, str, str | None]] = []

    if log.user_id:
        results.append(_resolve_user(log.user_id, context))

    if log.campaign_id:
        results.append(_resolve_campaign(log.campaign_id, context))

    if log.character_id:
        results.append(_resolve_character(log.character_id, context))

    if log.book_id:
        results.append(_resolve_book(log.book_id, log.campaign_id, context))

    if log.chapter_id:
        results.append(("Chapter", log.chapter_id, None))

    return results


def _resolve_user(user_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    """Look up a user by ID and return a display tuple."""
    user = next((u for u in context.users if u.id == user_id), None)
    if user:
        return ("User", user.username, url_for("profile.profile", user_id=user.id))
    return ("User", user_id, None)


def _resolve_campaign(campaign_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    """Look up a campaign by ID and return a display tuple."""
    campaign = next((c for c in context.campaigns if c.id == campaign_id), None)
    if campaign:
        return (
            "Campaign",
            campaign.name,
            url_for("campaign.campaign", campaign_id=campaign.id),
        )
    return ("Campaign", campaign_id, None)


def _resolve_character(character_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    """Look up a character by ID and return a display tuple."""
    character = next((c for c in context.characters if c.id == character_id), None)
    if character:
        return (
            "Character",
            character.name,
            url_for("character_view.character", character_id=character.id),
        )
    return ("Character", character_id, None)


def _resolve_book(
    book_id: str, campaign_id: str | None, context: GlobalContext
) -> tuple[str, str, str | None]:
    """Look up a book by ID and return a display tuple."""
    all_books = [book for books in context.books_by_campaign.values() for book in books]
    book = next((b for b in all_books if b.id == book_id), None)
    if book and campaign_id:
        return (
            "Book",
            book.name,
            url_for("book_view.book_detail", campaign_id=campaign_id, book_id=book.id),
        )
    return ("Book", book.name if book else book_id, None)
