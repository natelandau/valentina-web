"""Statistics caching with per-scope dispatch.

Cache roll statistics for one of three scopes (campaign / user / character)
behind a 30-second Redis/SimpleCache TTL. The underlying API calls live on
three separate vclient services, so this helper is the single place that
knows how to dispatch by scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from flask import g, session
from vclient import (
    sync_campaigns_service,
    sync_characters_service,
    sync_users_service,
)

from vweb.extensions import cache

if TYPE_CHECKING:
    from vclient.models import RollStatistics

ScopeType = Literal["campaign", "user", "character"]
_CACHE_TTL_SECONDS = 30
_NUM_TOP_TRAITS = 1


def get_statistics(scope_type: ScopeType, scope_id: str) -> RollStatistics:
    """Fetch roll statistics for a single scope with a 30-second cache TTL.

    Dispatch to the right vclient service based on ``scope_type``.

    Args:
        scope_type: Which entity the stats are scoped to.
        scope_id: The ID of the scoped entity.

    Returns:
        RollStatistics for the requested scope.

    Raises:
        ValueError: If scope_type is not one of "campaign", "user", or
            "character".
    """
    if scope_type not in ("campaign", "user", "character"):
        msg = f"Unknown scope_type: {scope_type!r}"
        raise ValueError(msg)

    cache_key = f"stats:{scope_type}:{scope_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    user_id = g.requesting_user.id
    company_id = session["company_id"]

    if scope_type == "campaign":
        svc = sync_campaigns_service(on_behalf_of=user_id, company_id=company_id)
    elif scope_type == "user":
        svc = sync_users_service(on_behalf_of=user_id, company_id=company_id)
    else:  # scope_type == "character"
        svc = sync_characters_service(on_behalf_of=user_id, company_id=company_id)

    stats = svc.get_statistics(scope_id, num_top_traits=_NUM_TOP_TRAITS)
    cache.set(cache_key, stats, timeout=_CACHE_TTL_SECONDS)
    return stats
