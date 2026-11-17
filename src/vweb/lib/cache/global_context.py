"""Global context data caching with company-level timestamp invalidation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flask import session
from loguru import logger

from vweb.api_client import (
    campaigns_service,
    characters_service,
    companies_service,
    default_client,
    users_service,
)
from vweb.api_client.exceptions import APIError
from vweb.constants import CACHE_GLOBAL_CONTEXT_TIMESTAMP_TTL
from vweb.extensions import cache
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vweb.api_client.models import (
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

    Fetch the company, users, campaigns, and characters concurrently, since none
    depends on another. Characters are discarded when there are no campaigns.

    Args:
        company_id: The company to fetch data for.
        user_id: The user whose perspective determines visible campaigns/characters.
        company: An already-fetched company to reuse, avoiding a redundant API call
            on the cold path where the caller fetched it for the timestamp.

    Returns:
        GlobalContext populated with fresh API data.
    """
    logger.debug("Fetching global company data")

    companies_svc = companies_service()
    users_svc = users_service(on_behalf_of=user_id, company_id=company_id)
    campaigns_svc = campaigns_service(on_behalf_of=user_id, company_id=company_id)
    characters_svc = characters_service(on_behalf_of=user_id, company_id=company_id)

    def fetch_company() -> Company:
        return company if company is not None else companies_svc.get(company_id)

    def fetch_users() -> tuple[list[User], int]:
        users = users_svc.list_all()
        # Only admins have API permission to list unapproved users.
        requesting_user = next((u for u in users if u.id == user_id), None)
        pending_user_count = (
            users_svc.get_unapproved_page(limit=1).total
            if requesting_user is not None and requesting_user.role == "ADMIN"
            else 0
        )
        return users, pending_user_count

    def fetch_characters() -> list[Character] | APIError:
        # Fetched alongside campaigns and used only when campaigns exist, so its error
        # is held until then rather than failing a company that has no campaigns.
        try:
            return characters_svc.list_all()
        except APIError as error:
            return error

    (users, pending_user_count), campaigns, characters_result, fetched_company = (
        default_client().run_parallel(
            fetch_users, campaigns_svc.list_all, fetch_characters, fetch_company
        )
    )

    characters: list[Character] = []
    characters_by_campaign: dict[str, list[Character]] = defaultdict(list)
    if campaigns:
        if isinstance(characters_result, APIError):
            raise characters_result
        characters = characters_result
        for char in characters:
            characters_by_campaign[char.campaign_id].append(char)

    return GlobalContext(
        company=fetched_company,
        users=users,
        campaigns=campaigns,
        characters_by_campaign=characters_by_campaign,
        characters=characters,
        resources_modified_at=fetched_company.resources_modified_at.isoformat()
        if fetched_company.resources_modified_at
        else "",
        pending_user_count=pending_user_count,
    )


def _ts_key(company_id: str) -> str:
    return f"global_timestamp:{company_id}"


def _ctx_key(company_id: str, user_id: str) -> str:
    # company_id stays readable for tenant-level grouping; the per-user component is
    # hashed so the key shape matches the other company-scoped caches.
    return f"global_ctx:{company_id}:{base.hash_key(user_id)}"


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
    ctx_key = _ctx_key(company_id, user_id)

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
            company = companies_service().get(company_id)
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
    cache.delete(_ctx_key(company_id, user_id))


def clear_current() -> None:
    """Clear the requesting user's global context, scoped from the Flask session.

    Call after any local mutation that affects the user's global context
    (campaigns, characters, books, notes, users, etc.) so the next request
    rebuilds ``g.global_context`` with fresh API data. Requires an active
    request with ``company_id`` and ``user_id`` in the session; pass explicit
    ids to :func:`clear` outside that context (e.g. auth flows).
    """
    clear(session["company_id"], session["user_id"])
