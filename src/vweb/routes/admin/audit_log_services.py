"""Service-layer helpers for the admin audit log page.

Wraps the vclient audit log API and resolves entity IDs to human-readable
display names with optional navigation URLs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, get_args

from flask import session, url_for
from vclient import sync_companies_service
from vclient.models.audit_logs import AuditLog

if TYPE_CHECKING:
    from vclient.models.pagination import PaginatedResponse

    from vweb.lib.global_context import GlobalContext

ENTITY_TYPES: list[str] = sorted(get_args(AuditLog.model_fields["entity_type"].annotation))


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
    company_id: str = session["company_id"]
    return sync_companies_service().get_audit_log_page(  # ty:ignore[invalid-return-type]
        company_id,
        limit=limit,
        offset=offset,
        entity_type=entity_type or None,  # ty:ignore[invalid-argument-type]
        operation=operation or None,  # ty:ignore[invalid-argument-type]
        acting_user_id=acting_user_id or None,
        date_from=datetime.fromisoformat(date_from) if date_from else None,
        date_to=datetime.fromisoformat(date_to) if date_to else None,
    )


def resolve_acting_user(
    acting_user_id: str | None,
    context: GlobalContext,
) -> tuple[str, str]:
    """Resolve the acting user to a display name and profile URL.

    Args:
        acting_user_id: The ID of the user who performed the action.
        context: The global context containing cached users.

    Returns:
        Tuple of (display_name, url_or_empty_string).
    """
    if not acting_user_id:
        return ("", "")

    user = next((u for u in context.users if u.id == acting_user_id), None)
    if user:
        return (user.username, url_for("profile.profile", user_id=user.id))
    return (acting_user_id, "")


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
    user = next((u for u in context.users if u.id == user_id), None)
    if user:
        return ("User", user.username, url_for("profile.profile", user_id=user.id))
    return ("User", user_id, None)


def _resolve_campaign(campaign_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    campaign = next((c for c in context.campaigns if c.id == campaign_id), None)
    if campaign:
        return (
            "Campaign",
            campaign.name,
            url_for("campaign.campaign", campaign_id=campaign.id),
        )
    return ("Campaign", campaign_id, None)


def _resolve_character(character_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
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
    # Narrow search to the specific campaign when possible
    if campaign_id and campaign_id in context.books_by_campaign:
        books = context.books_by_campaign[campaign_id]
    else:
        books = [
            book for campaign_books in context.books_by_campaign.values() for book in campaign_books
        ]

    book = next((b for b in books if b.id == book_id), None)
    if book and campaign_id:
        return (
            "Book",
            book.name,
            url_for("book_view.book_detail", campaign_id=campaign_id, book_id=book.id),
        )
    return ("Book", book.name if book else book_id, None)
