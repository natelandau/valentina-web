"""Tests for the lazy book/chapter cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import CampaignBookFactory, CampaignChapterFactory

from vweb.extensions import cache
from vweb.lib import campaign_content_cache as ccc

if TYPE_CHECKING:
    from flask.ctx import RequestContext


@pytest.fixture(autouse=True)
def _clear_cache(app) -> None:
    """Ensure each test starts with an empty cache."""
    with app.app_context():
        cache.clear()


def _set_request_context(app, mocker, stamp: str = "2026-01-01T00:00:00+00:00") -> RequestContext:
    """Push an app context with a fake g.global_context stamp and a session company."""
    ctx = app.test_request_context("/")
    ctx.push()
    from flask import g, session

    session["company_id"] = "comp-1"
    g.requesting_user = mocker.MagicMock(id="user-1")
    g.global_context = mocker.MagicMock(resources_modified_at=stamp)
    return ctx


def test_get_books_for_campaign_caches_and_sorts(app, mocker):
    """Verify books are fetched once, cached, and returned sorted by number."""
    # Given a request context and a books service returning unsorted books
    ctx = _set_request_context(app, mocker)
    books = [CampaignBookFactory.build(number=2), CampaignBookFactory.build(number=1)]
    svc = mocker.patch.object(ccc, "sync_books_service")
    svc.return_value.list_all.return_value = books

    # When fetched twice
    first = ccc.get_books_for_campaign("camp-1")
    second = ccc.get_books_for_campaign("camp-1")

    # Then sorted by number and the service is hit only once
    assert [b.number for b in first] == [1, 2]
    assert second == first
    svc.return_value.list_all.assert_called_once()
    ctx.pop()


def test_get_books_refetches_on_stamp_change(app, mocker):
    """Verify a changed company timestamp forces a refetch."""
    # Given cached books under one stamp
    ctx = _set_request_context(app, mocker, stamp="stamp-A")
    svc = mocker.patch.object(ccc, "sync_books_service")
    svc.return_value.list_all.return_value = [CampaignBookFactory.build(number=1)]
    ccc.get_books_for_campaign("camp-1")

    # When the stamp changes
    from flask import g

    g.global_context.resources_modified_at = "stamp-B"
    ccc.get_books_for_campaign("camp-1")

    # Then the service is hit again
    assert svc.return_value.list_all.call_count == 2
    ctx.pop()


def test_get_chapters_for_book_caches_and_sorts(app, mocker):
    """Verify chapters are fetched once, cached, and sorted by number."""
    # Given a chapters service returning unsorted chapters
    ctx = _set_request_context(app, mocker)
    chapters = [CampaignChapterFactory.build(number=3), CampaignChapterFactory.build(number=1)]
    svc = mocker.patch.object(ccc, "sync_chapters_service")
    svc.return_value.list_all.return_value = chapters

    # When fetched twice
    first = ccc.get_chapters_for_book("camp-1", "book-1")
    ccc.get_chapters_for_book("camp-1", "book-1")

    # Then sorted and fetched once
    assert [c.number for c in first] == [1, 3]
    svc.return_value.list_all.assert_called_once()
    ctx.pop()


def test_get_chapters_refetches_on_stamp_change(app, mocker):
    """Verify a changed company timestamp forces a chapters refetch."""
    # Given cached chapters under one stamp
    ctx = _set_request_context(app, mocker, stamp="stamp-A")
    svc = mocker.patch.object(ccc, "sync_chapters_service")
    svc.return_value.list_all.return_value = [CampaignChapterFactory.build(number=1)]
    ccc.get_chapters_for_book("camp-1", "book-1")

    # When the stamp changes
    from flask import g

    g.global_context.resources_modified_at = "stamp-B"
    ccc.get_chapters_for_book("camp-1", "book-1")

    # Then the service is hit again
    assert svc.return_value.list_all.call_count == 2
    ctx.pop()


def test_clear_campaign_content_cache_evicts_scope(app, mocker):
    """Verify clearing a scope forces the next read to refetch."""
    # Given cached books for a campaign
    ctx = _set_request_context(app, mocker)
    svc = mocker.patch.object(ccc, "sync_books_service")
    svc.return_value.list_all.return_value = [CampaignBookFactory.build(number=1)]
    ccc.get_books_for_campaign("camp-1")

    # When the campaign scope is cleared
    ccc.clear_campaign_content_cache("comp-1", campaign_id="camp-1")
    ccc.get_books_for_campaign("camp-1")

    # Then the service is hit again
    assert svc.return_value.list_all.call_count == 2
    ctx.pop()


def test_clear_campaign_content_cache_requires_a_scope(app, mocker):
    """Verify clearing with no scope raises rather than silently doing nothing."""
    # Given a request context
    ctx = _set_request_context(app, mocker)

    # When/Then clearing with neither scope raises ValueError
    with pytest.raises(ValueError, match="at least one"):
        ccc.clear_campaign_content_cache("comp-1")
    ctx.pop()
