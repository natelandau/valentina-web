"""Statistics caching with per-scope dispatch.

Cache roll statistics for one of three scopes (campaign / user / character) behind a
30-second TTL. The underlying API calls live on three separate vclient services, so
this helper is the single place that knows how to dispatch by scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from vweb.constants import CACHE_STATISTICS_TTL
from vweb.lib import api_services
from vweb.lib.cache import base

if TYPE_CHECKING:
    from vweb.api_client.models import RollStatistics

ScopeType = Literal["campaign", "user", "character"]
_NUM_TOP_TRAITS = 1
_STRATEGY = base.ShortTTL(ttl=CACHE_STATISTICS_TTL)


def get(scope_type: ScopeType, scope_id: str) -> RollStatistics:
    """Fetch roll statistics for a single scope with a 30-second cache TTL.

    Args:
        scope_type: Which entity the stats are scoped to.
        scope_id: The ID of the scoped entity.

    Returns:
        RollStatistics for the requested scope.

    Raises:
        ValueError: If scope_type is not one of "campaign", "user", or "character".
    """
    if scope_type not in ("campaign", "user", "character"):
        msg = f"Unknown scope_type: {scope_type!r}"
        raise ValueError(msg)

    key = f"stats:{scope_type}:{scope_id}"
    return base.cached_fetch(key, lambda: _fetch(scope_type, scope_id), _STRATEGY)


def _fetch(scope_type: ScopeType, scope_id: str) -> RollStatistics:
    if scope_type == "campaign":
        svc = api_services.campaigns()
    elif scope_type == "user":
        svc = api_services.users()
    else:  # scope_type == "character"
        svc = api_services.characters()

    return svc.get_statistics(scope_id, num_top_traits=_NUM_TOP_TRAITS)
