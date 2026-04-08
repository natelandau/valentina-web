"""Global context data caching with company-level timestamp invalidation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from vclient import (
    sync_books_service,
    sync_campaigns_service,
    sync_characters_service,
    sync_companies_service,
    sync_users_service,
)

from vweb.config import get_settings
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


def _fetch_global_data() -> GlobalContext:
    """Fetch all global company data from the API.

    Returns:
        GlobalContext populated with fresh API data.
    """
    settings = get_settings()
    admin_id = settings.api.server_admin_user_id
    company_id = settings.api.default_company_id

    logger.debug("Fetching global company data")

    company = sync_companies_service().get(company_id)
    users = sync_users_service().list_all()
    campaigns = sync_campaigns_service(user_id=admin_id).list_all()

    characters_by_campaign: dict[str, list[Character]] = {}
    characters: list[Character] = []
    books_by_campaign: dict[str, list[CampaignBook]] = {}
    if campaigns:
        char_results = [
            sync_characters_service(user_id=admin_id, campaign_id=c.id).list_all()
            for c in campaigns
        ]
        characters_by_campaign = {
            c.id: chars for c, chars in zip(campaigns, char_results, strict=True)
        }
        characters = [char for chars in char_results for char in chars]

        book_results = [
            sync_books_service(user_id=admin_id, campaign_id=c.id).list_all() for c in campaigns
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
    )


def _ts_key(company_id: str) -> str:
    return f"global_timestamp:{company_id}"


def _ctx_key(company_id: str) -> str:
    return f"global_ctx:{company_id}"


def load_global_context() -> GlobalContext:
    """Load global context with company-level timestamp invalidation.

    Returns:
        GlobalContext with current company data.
    """
    company_id = get_settings().api.default_company_id

    ts_key = _ts_key(company_id)
    api_timestamp = cache.get(ts_key)
    if api_timestamp is None:
        company = sync_companies_service().get(company_id)
        api_timestamp = (
            company.resources_modified_at.isoformat() if company.resources_modified_at else ""
        )
        cache.set(ts_key, api_timestamp, timeout=120)

    ctx_key = _ctx_key(company_id)
    cached = cache.get(ctx_key)
    if cached is not None:
        cached_timestamp, cached_global_context = cached
        if cached_timestamp == api_timestamp:
            return cached_global_context

    global_context = _fetch_global_data()
    cache.set(ctx_key, (global_context.resources_modified_at, global_context))
    return global_context


def clear_global_context_cache() -> None:
    """Clear global context caches. Call after mutations or for testing.

    Only deletes global context keys — does not affect blueprint, character trait,
    or campaign stats caches.
    """
    company_id = get_settings().api.default_company_id
    cache.delete(_ts_key(company_id))
    cache.delete(_ctx_key(company_id))


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

    admin_id = get_settings().api.server_admin_user_id
    stats = sync_campaigns_service(user_id=admin_id).get_statistics(campaign_id)
    cache.set(cache_key, stats, timeout=30)
    return stats
