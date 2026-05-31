"""Global system status cache.

Fetch the API's health/status payload and cache it shared across all users
with a 30-second TTL. The health endpoint requires no authentication and is not
company-scoped, so a single static cache key serves every visitor and the API
is hit at most once per TTL window regardless of traffic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient import sync_system_service

from vweb.constants import CACHE_SYSTEM_STATUS_KEY, CACHE_SYSTEM_STATUS_TTL
from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import SystemHealth


def get_system_health() -> SystemHealth:
    """Return the API system health, fetching from the API on cache miss.

    Cached with a 30-second TTL and shared across all users and requests, so the
    underlying health endpoint is called at most once per window no matter how
    many visitors view the status.

    Returns:
        A SystemHealth instance describing database/cache connectivity, latency,
        uptime, and the API version.
    """
    cached: SystemHealth | None = cache.get(CACHE_SYSTEM_STATUS_KEY)
    if cached is not None:
        return cached

    result = sync_system_service().health()
    cache.set(CACHE_SYSTEM_STATUS_KEY, result, timeout=CACHE_SYSTEM_STATUS_TTL)
    return result


def clear_system_status_cache() -> None:
    """Remove the cached system health, forcing a fresh API fetch on next access."""
    cache.delete(CACHE_SYSTEM_STATUS_KEY)
