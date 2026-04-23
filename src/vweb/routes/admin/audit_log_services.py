"""Admin audit log page — constants only.

The resolvers and vclient wrapper live in `vweb.lib.audit_log` (shared with the
audit log card). This module exists so admin can still import `ENTITY_TYPES`
for its filter dropdown.
"""

from __future__ import annotations

from typing import get_args

from vclient.models.audit_logs import AuditLog

ENTITY_TYPES: list[str] = sorted(get_args(AuditLog.model_fields["entity_type"].annotation))
