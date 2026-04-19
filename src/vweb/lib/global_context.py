"""Global context data caching with company-level timestamp invalidation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flask import g
from loguru import logger
from vclient import (
    sync_books_service,
    sync_campaigns_service,
    sync_characters_service,
    sync_companies_service,
    sync_users_service,
)

from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import Campaign, CampaignBook, Character, Company, RollStatistics, User


@dataclass
class GlobalContext:
    """All data needed to render company-specific data across the application with Flask-Caching."""

    company: Company
    users: list[User]
    campaigns: list[Campaign]
    characters_by_campaign: dict[str, list[Character]] = field(default_factory=dict)
    characters: list[Character] = field(default_factory=list)
    books_by_campaign: dict[str, list[CampaignBook]] = field(default_factory=dict)
    resources_modified_at: str = ""
    pending_user_count: int = 0


def _fetch_global_data(company_id: str, user_id: str) -> GlobalContext:
    """Fetch all global company data from the API.

    Args:
        company_id: The company to fetch data for.
        user_id: The user whose perspective determines visible campaigns/characters/books.

    Returns:
        GlobalContext populated with fresh API data.
    """
    logger.debug("Fetching global company data")

    company = sync_companies_service().get(company_id)
    users_svc = sync_users_service(on_behalf_of=user_id, company_id=company_id)
    users = users_svc.list_all()
    campaigns = sync_campaigns_service(on_behalf_of=user_id, company_id=company_id).list_all()

    # Only admins have API permission to list unapproved users; this count drives
    # the pending-approval indicator in the global nav and admin tabs.
    requesting_user = next((u for u in users if u.id == user_id), None)
    pending_user_count = (
        len(users_svc.list_all_unapproved())
        if requesting_user is not None and requesting_user.role == "ADMIN"
        else 0
    )

    characters: list[Character] = []
    characters_by_campaign: dict[str, list[Character]] = defaultdict(list)
    books_by_campaign: dict[str, list[CampaignBook]] = {}
    if campaigns:
        characters = sync_characters_service(on_behalf_of=user_id, company_id=company_id).list_all()
        for char in characters:
            characters_by_campaign[char.campaign_id].append(char)

        book_results = [
            sync_books_service(
                campaign_id=c.id, on_behalf_of=user_id, company_id=company_id
            ).list_all()
            for c in campaigns
        ]
        books_by_campaign = {c.id: books for c, books in zip(campaigns, book_results, strict=True)}

    return GlobalContext(
        company=company,
        users=users,
        campaigns=campaigns,
        characters_by_campaign=characters_by_campaign,
        characters=characters,
        books_by_campaign=books_by_campaign,
        resources_modified_at=company.resources_modified_at.isoformat()
        if company.resources_modified_at
        else "",
        pending_user_count=pending_user_count,
    )


def _ts_key(company_id: str) -> str:
    return f"global_timestamp:{company_id}"


def load_global_context(company_id: str, user_id: str) -> GlobalContext:
    """Load global context with company-level timestamp invalidation.

    Args:
        company_id: The company to load context for.
        user_id: The user whose perspective determines visible data.

    Returns:
        GlobalContext with current company data.
    """
    ts_key = _ts_key(company_id)
    api_timestamp = cache.get(ts_key)
    if api_timestamp is None:
        company = sync_companies_service().get(company_id)
        api_timestamp = (
            company.resources_modified_at.isoformat() if company.resources_modified_at else ""
        )
        cache.set(ts_key, api_timestamp, timeout=120)

    ctx_key = f"global_ctx:{company_id}:{user_id}"
    cached = cache.get(ctx_key)
    if cached is not None:
        cached_timestamp, cached_global_context = cached
        if cached_timestamp == api_timestamp:
            return cached_global_context

    global_context = _fetch_global_data(company_id, user_id)
    cache.set(ctx_key, (global_context.resources_modified_at, global_context))
    return global_context


def clear_global_context_cache(company_id: str, user_id: str) -> None:
    """Clear global context caches. Call after mutations or for testing.

    Only deletes global context keys — does not affect blueprint, character trait,
    or campaign stats caches.

    Args:
        company_id: The company whose context to clear.
        user_id: The user whose cached context to clear.
    """
    cache.delete(_ts_key(company_id))
    cache.delete(f"global_ctx:{company_id}:{user_id}")


def get_campaign_statistics(campaign_id: str) -> RollStatistics:
    """Fetch campaign statistics with a 30-second cache TTL.

    Args:
        campaign_id: The campaign to fetch statistics for.

    Returns:
        RollStatistics for the campaign.
    """
    cache_key = f"campaign_stats:{campaign_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    user_id = g.requesting_user.id
    company_id = g.global_context.company.id
    stats = sync_campaigns_service(on_behalf_of=user_id, company_id=company_id).get_statistics(
        campaign_id
    )
    cache.set(cache_key, stats, timeout=30)
    return stats
