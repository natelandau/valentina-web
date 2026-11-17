"""Tests for the lazy book/chapter cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    Routes,
)
from vweb.extensions import cache
from vweb.lib.cache import campaign_content as ccc

if TYPE_CHECKING:
    from flask.ctx import RequestContext

pytestmark = pytest.mark.usefixtures("real_cache_services")


@pytest.fixture(autouse=True)
def _clear_cache(app) -> None:
    """Ensure each test starts with an empty cache."""
    with app.app_context():
        cache.clear()


def _set_request_context(app, mocker, stamp: str = "2026-01-01T00:00:00+00:00") -> RequestContext:
    """Push an app context with a fake g.global_context stamp and a session company."""
    ctx = app.test_request_context("/")
    ctx.push()
    from flask import g

    seed_session(user_id="user-1", company_id="comp-1")
    g.global_context = mocker.MagicMock(resources_modified_at=stamp)
    return ctx


def test_books_caches_and_sorts(app, mocker, fake_vclient):
    """Verify books are fetched once, cached, and returned sorted by number."""
    # Given a request context and the API returning unsorted books
    ctx = _set_request_context(app, mocker)
    books = [CampaignBookFactory.build(number=2), CampaignBookFactory.build(number=1)]
    fake_vclient.set_response(Routes.BOOKS_LIST, items=books)

    # When fetched twice
    first = ccc.books("camp-1")
    second = ccc.books("camp-1")

    # Then sorted by number and the campaign's books are fetched only once
    assert [b.number for b in first] == [1, 2]
    assert second == first
    fake_vclient.assert_called(
        Routes.BOOKS_LIST, params={"company_id": "comp-1", "campaign_id": "camp-1"}, times=1
    )
    ctx.pop()


def test_books_refetches_on_stamp_change(app, mocker, fake_vclient):
    """Verify a changed company timestamp forces a refetch."""
    # Given cached books under one stamp
    ctx = _set_request_context(app, mocker, stamp="stamp-A")
    fake_vclient.set_response(Routes.BOOKS_LIST, items=[CampaignBookFactory.build(number=1)])
    ccc.books("camp-1")

    # When the stamp changes
    from flask import g

    g.global_context.resources_modified_at = "stamp-B"
    ccc.books("camp-1")

    # Then the books are fetched again
    fake_vclient.assert_called(Routes.BOOKS_LIST, params={"campaign_id": "camp-1"}, times=2)
    ctx.pop()


def test_chapters_caches_and_sorts(app, mocker, fake_vclient):
    """Verify chapters are fetched once, cached, and sorted by number."""
    # Given the API returning unsorted chapters
    ctx = _set_request_context(app, mocker)
    chapters = [CampaignChapterFactory.build(number=3), CampaignChapterFactory.build(number=1)]
    fake_vclient.set_response(Routes.CHAPTERS_LIST, items=chapters)

    # When fetched twice
    first = ccc.chapters("camp-1", "book-1")
    ccc.chapters("camp-1", "book-1")

    # Then sorted and the book's chapters are fetched once
    assert [c.number for c in first] == [1, 3]
    fake_vclient.assert_called(
        Routes.CHAPTERS_LIST,
        params={"company_id": "comp-1", "campaign_id": "camp-1", "book_id": "book-1"},
        times=1,
    )
    ctx.pop()


def test_chapters_refetches_on_stamp_change(app, mocker, fake_vclient):
    """Verify a changed company timestamp forces a chapters refetch."""
    # Given cached chapters under one stamp
    ctx = _set_request_context(app, mocker, stamp="stamp-A")
    fake_vclient.set_response(Routes.CHAPTERS_LIST, items=[CampaignChapterFactory.build(number=1)])
    ccc.chapters("camp-1", "book-1")

    # When the stamp changes
    from flask import g

    g.global_context.resources_modified_at = "stamp-B"
    ccc.chapters("camp-1", "book-1")

    # Then the chapters are fetched again
    fake_vclient.assert_called(Routes.CHAPTERS_LIST, params={"book_id": "book-1"}, times=2)
    ctx.pop()


def test_clear_evicts_scope(app, mocker, fake_vclient):
    """Verify clearing a scope forces the next read to refetch."""
    # Given cached books for a campaign
    ctx = _set_request_context(app, mocker)
    fake_vclient.set_response(Routes.BOOKS_LIST, items=[CampaignBookFactory.build(number=1)])
    ccc.books("camp-1")

    # When the campaign scope is cleared
    ccc.clear("comp-1", campaign_id="camp-1")
    ccc.books("camp-1")

    # Then the books are fetched again
    fake_vclient.assert_called(Routes.BOOKS_LIST, params={"campaign_id": "camp-1"}, times=2)
    ctx.pop()


def test_clear_requires_a_scope(app, mocker):
    """Verify clearing with no scope raises rather than silently doing nothing."""
    # Given a request context
    ctx = _set_request_context(app, mocker)

    # When/Then clearing with neither scope raises ValueError
    with pytest.raises(ValueError, match="at least one"):
        ccc.clear("comp-1")
    ctx.pop()
