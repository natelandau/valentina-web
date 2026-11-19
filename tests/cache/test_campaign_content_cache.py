"""Tests for the lazy book/chapter cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import g

from tests.helpers import seed_session
from vweb.api_client.testing import CampaignBookFactory, CampaignChapterFactory, Routes
from vweb.extensions import cache
from vweb.lib.cache import campaign_content as ccc

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.usefixtures("real_cache_services")

_SCOPES = [
    pytest.param(
        Routes.BOOKS_LIST,
        CampaignBookFactory,
        lambda: ccc.books("camp-1"),
        {"company_id": "comp-1", "campaign_id": "camp-1"},
        id="books",
    ),
    pytest.param(
        Routes.CHAPTERS_LIST,
        CampaignChapterFactory,
        lambda: ccc.chapters("camp-1", "book-1"),
        {"company_id": "comp-1", "campaign_id": "camp-1", "book_id": "book-1"},
        id="chapters",
    ),
]


@pytest.fixture
def request_ctx(app, mocker) -> Iterator[None]:
    """Run inside a request with a seeded session and a context carrying a change stamp."""
    with app.test_request_context("/"):
        cache.clear()
        seed_session(user_id="user-1", company_id="comp-1")
        g.global_context = mocker.MagicMock(resources_modified_at="stamp-A")
        yield


@pytest.mark.usefixtures("request_ctx")
@pytest.mark.parametrize(("route", "factory", "read", "params"), _SCOPES)
def test_fetches_once_sorted_by_number(fake_vclient, route, factory, read, params) -> None:
    """Verify a campaign's books or a book's chapters are fetched once and sorted by number."""
    fake_vclient.set_response(route, items=[factory.build(number=3), factory.build(number=1)])

    first = read()
    second = read()

    assert [item.number for item in first] == [1, 3]
    assert second == first
    fake_vclient.assert_called(route, params=params, times=1)


@pytest.mark.usefixtures("request_ctx")
@pytest.mark.parametrize(("route", "factory", "read", "params"), _SCOPES)
def test_refetches_when_company_stamp_changes(fake_vclient, route, factory, read, params) -> None:
    """Verify a change anywhere in the company invalidates the cached list."""
    fake_vclient.set_response(route, items=[factory.build(number=1)])
    read()

    g.global_context.resources_modified_at = "stamp-B"
    read()

    fake_vclient.assert_called(route, params=params, times=2)


@pytest.mark.usefixtures("request_ctx")
def test_clear_evicts_scope(fake_vclient) -> None:
    """Verify clearing a campaign scope forces the next read to refetch."""
    fake_vclient.set_response(Routes.BOOKS_LIST, items=[CampaignBookFactory.build(number=1)])
    ccc.books("camp-1")

    ccc.clear("comp-1", campaign_id="camp-1")
    ccc.books("camp-1")

    fake_vclient.assert_called(Routes.BOOKS_LIST, params={"campaign_id": "camp-1"}, times=2)


@pytest.mark.usefixtures("request_ctx")
def test_clear_requires_a_scope() -> None:
    """Verify clearing with no scope raises rather than silently doing nothing."""
    with pytest.raises(ValueError, match="at least one"):
        ccc.clear("comp-1")
