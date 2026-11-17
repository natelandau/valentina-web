"""Shared query parameter builder for audit log endpoints."""

from collections.abc import Sequence
from datetime import datetime


def _build_audit_params(
    *,
    acting_user_id: str | None = None,
    user_id: str | None = None,
    campaign_id: str | None = None,
    book_id: str | None = None,
    chapter_id: str | None = None,
    character_id: str | None = None,
    entity_type: str | None = None,
    operation: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    include: Sequence[str] | None = None,
) -> dict[str, str]:
    """Build query parameter dict from audit log filter kwargs.

    Only include non-None values. Serialize datetimes to ISO 8601 and
    join include lists with commas.

    Args:
        acting_user_id: Filter by the user who performed the action.
        user_id: Filter by the user affected by the action.
        campaign_id: Filter by campaign ID.
        book_id: Filter by book ID.
        chapter_id: Filter by chapter ID.
        character_id: Filter by character ID.
        entity_type: Filter by entity type (e.g., "CAMPAIGN", "CHARACTER").
        operation: Filter by operation type (CREATE, UPDATE, DELETE).
        date_from: Return logs on or after this datetime (ISO 8601 serialized).
        date_to: Return logs on or before this datetime (ISO 8601 serialized).
        include: Additional data to include (e.g., ("request_details",)).

    Returns:
        A dict of query parameters with only non-None values included.
    """
    string_params: dict[str, str | None] = {
        "acting_user_id": acting_user_id,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "character_id": character_id,
        "entity_type": entity_type,
        "operation": operation,
    }
    params: dict[str, str] = {k: v for k, v in string_params.items() if v is not None}

    if date_from is not None:
        params["date_from"] = date_from.isoformat()
    if date_to is not None:
        params["date_to"] = date_to.isoformat()
    if include is not None:
        params["include"] = ",".join(include)

    return params
