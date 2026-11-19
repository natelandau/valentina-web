"""Tests for the generic statistics cache helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import RollStatisticsFactory, Routes
from vweb.lib.cache.statistics import get

if TYPE_CHECKING:
    from vweb.api_client.testing import FakeVClient
    from vweb.lib.cache.statistics import ScopeType


@pytest.mark.parametrize(
    ("scope_type", "route", "id_param"),
    [
        ("campaign", Routes.CAMPAIGNS_STATISTICS, "campaign_id"),
        ("user", Routes.USERS_STATISTICS, "user_id"),
        ("character", Routes.CHARACTERS_STATISTICS, "character_id"),
    ],
)
def test_fetches_scope_statistics_once(
    app, mock_cache_store, fake_vclient: FakeVClient, scope_type: ScopeType, route, id_param: str
) -> None:
    """Verify each scope requests its own statistics with the top trait, then serves the cache."""
    stats = RollStatisticsFactory.build()
    fake_vclient.set_response(route, model=stats)

    with app.test_request_context():
        seed_session(user_id="user-1", company_id="comp-1")
        first = get(scope_type, "scope-1")
        second = get(scope_type, "scope-1")

    assert first == second == stats
    fake_vclient.assert_called(
        route,
        params={"company_id": "comp-1", id_param: "scope-1"},
        query={"num_top_traits": 1},
        times=1,
    )


def test_unknown_scope_type_raises(app) -> None:
    """Verify an unknown scope_type raises ValueError."""
    with app.test_request_context(), pytest.raises(ValueError, match="scope_type"):
        get("bogus", "id-1")  # ty:ignore[invalid-argument-type]
