"""Global context data caching with company-level timestamp invalidation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from vclient import (
    sync_campaigns_service,
    sync_characters_service,
    sync_companies_service,
    sync_users_service,
)

from vweb.constants import CACHE_GLOBAL_CONTEXT_TIMESTAMP_TTL
from vweb.extensions import cache
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import (
        Campaign,
        Character,
        Company,
        User,
    )


@dataclass
class GlobalContext:
    """All data needed to render company-specific data across the application with Flask-Caching."""

    company: Company
    users: list[User]
    campaigns: list[Campaign]
    characters_by_campaign: dict[str, list[Character]] = field(default_factory=dict)
    characters: list[Character] = field(default_factory=list)
    resources_modified_at: str = ""
    pending_user_count: int = 0


def _fetch_global_data(
    company_id: str, user_id: str, company: Company | None = None
) -> GlobalContext:
    """Fetch all global company data from the API.

    Args:
        company_id: The company to fetch data for.
        user_id: The user whose perspective determines visible campaigns/characters.
        company: An already-fetched company to reuse, avoiding a redundant API call
            on the cold path where the caller fetched it for the timestamp.

    Returns:
        GlobalContext populated with fresh API data.
    """
    logger.debug("Fetching global company data")

    if company is None:
        company = sync_companies_service().get(company_id)
    users_svc = sync_users_service(on_behalf_of=user_id, company_id=company_id)
    users = users_svc.list_all()
    campaigns = sync_campaigns_service(on_behalf_of=user_id, company_id=company_id).list_all()

    # Only admins have API permission to list unapproved users.
    requesting_user = next((u for u in users if u.id == user_id), None)
    pending_user_count = (
        len(users_svc.list_all_unapproved())
        if requesting_user is not None and requesting_user.role == "ADMIN"
        else 0
    )

    characters: list[Character] = []
    characters_by_campaign: dict[str, list[Character]] = defaultdict(list)
    if campaigns:
        characters = sync_characters_service(on_behalf_of=user_id, company_id=company_id).list_all()
        for char in characters:
            characters_by_campaign[char.campaign_id].append(char)

    return GlobalContext(
        company=company,
        users=users,
        campaigns=campaigns,
        characters_by_campaign=characters_by_campaign,
        characters=characters,
        resources_modified_at=company.resources_modified_at.isoformat()
        if company.resources_modified_at
        else "",
        pending_user_count=pending_user_count,
    )


def _ts_key(company_id: str) -> str:
    return f"global_timestamp:{company_id}"


def load(company_id: str, user_id: str) -> GlobalContext:
    """Load global context with company-level timestamp invalidation.

    A lock-free fast path returns the cached context when both the company timestamp
    and the per-user context are warm and consistent. Otherwise a per-(company, user)
    single-flight rebuild ensures only one request rebuilds while others wait and reuse
    the result — preventing a cold-cache thundering herd across the dashboard's lazy
    cards.

    Args:
        company_id: The company to load context for.
        user_id: The user whose perspective determines visible data.

    Returns:
        GlobalContext with current company data.
    """
    ts_key = _ts_key(company_id)
    ctx_key = f"global_ctx:{company_id}:{user_id}"

    # Fast path: warm timestamp + warm matching context, no lock.
    api_timestamp = cache.get(ts_key)
    if api_timestamp is not None:
        cached = cache.get(ctx_key)
        if cached is not None and cached[0] == api_timestamp:
            return cached[1]

    def rebuild() -> GlobalContext:
        # Resolve the timestamp inside the lock; another waiter may have set it.
        local_timestamp = cache.get(ts_key)
        company: Company | None = None
        if local_timestamp is None:
            company = sync_companies_service().get(company_id)
            local_timestamp = (
                company.resources_modified_at.isoformat() if company.resources_modified_at else ""
            )
            cache.set(ts_key, local_timestamp, timeout=CACHE_GLOBAL_CONTEXT_TIMESTAMP_TTL)

        # Double-check: a prior holder of this lock may have just rebuilt it.
        cached = cache.get(ctx_key)
        if cached is not None and cached[0] == local_timestamp:
            return cached[1]

        global_context = _fetch_global_data(company_id, user_id, company=company)
        cache.set(ctx_key, (global_context.resources_modified_at, global_context))
        return global_context

    return base.single_flight(ctx_key, rebuild)


def clear(company_id: str, user_id: str) -> None:
    """Clear global context caches. Call after mutations or for testing.

    Only deletes the timestamp and per-user context keys — does not affect blueprint,
    character-sheet, or stats caches.

    Args:
        company_id: The company whose context to clear.
        user_id: The user whose cached context to clear.
    """
    cache.delete(_ts_key(company_id))
    cache.delete(f"global_ctx:{company_id}:{user_id}")
