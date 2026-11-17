"""Pydantic models for Audit Log API responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from vweb.api_client.constants import AuditEntityType, AuditOperation


class AuditLog(BaseModel):
    """Response model for an audit log entry.

    Represents a single audit trail record for entity changes within a company.
    """

    id: str
    date_created: datetime
    entity_type: AuditEntityType
    operation: AuditOperation
    target_entity_id: str
    description: str
    changes: dict[str, Any] | None = None
    company_id: str
    acting_user_id: str | None = None
    user_id: str | None = None
    campaign_id: str | None = None
    book_id: str | None = None
    chapter_id: str | None = None
    character_id: str | None = None
    request_id: str | None = None
    summary: str | None = None


class AuditLogDetail(AuditLog):
    """Audit log entry with request forensic details.

    Extends AuditLog with raw request information, returned when
    ``include=request_details`` is passed to the audit log endpoint.
    """

    method: str | None = None
    url: str | None = None
    request_json: dict[str, Any] | None = None
    request_body: str | None = None
    path_params: dict[str, str] | None = None
    query_params: dict[str, str] | None = None
    operation_id: str | None = None
    handler_name: str | None = None


__all__ = [
    "AuditLog",
    "AuditLogDetail",
]
