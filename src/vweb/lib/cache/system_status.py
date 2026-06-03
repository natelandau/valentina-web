"""Global system status cache.

Fetch the API's health/status payload and cache it shared across all users with a
30-second TTL. The health endpoint requires no authentication and is not
company-scoped, so a single static cache key serves every visitor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient import sync_system_service

from vweb.constants import CACHE_SYSTEM_STATUS_KEY, CACHE_SYSTEM_STATUS_TTL
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vclient.models import SystemHealth

_STRATEGY = base.ShortTTL(ttl=CACHE_SYSTEM_STATUS_TTL)


def get() -> SystemHealth:
    """Return the API system health, fetching on cache miss (30s TTL, shared)."""
    return base.cached_fetch(CACHE_SYSTEM_STATUS_KEY, _fetch, _STRATEGY)


def clear() -> None:
    """Remove the cached system health, forcing a fresh API fetch on next access."""
    base.clear_key(CACHE_SYSTEM_STATUS_KEY)


def _fetch() -> SystemHealth:
    return sync_system_service().health()
