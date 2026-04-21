"""Tests for vweb.lib.api data-access helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import g, session
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
    CompanyFactory,
    UserFactory,
)

from tests.helpers import build_global_context
from vweb.lib.api import (
    get_active_campaign,
    get_chapter_count_for_campaign,
    get_chapters_for_book,
)
from vweb.lib.global_context import GlobalContext


def _build_ctx(campaigns: list) -> GlobalContext:
    """Build a GlobalContext for helper tests without hitting the API."""
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    return GlobalContext(
        company=company,
        users=[user],
        campaigns=campaigns,
        books_by_campaign={c.id: [] for c in campaigns},
        characters_by_campaign={c.id: [] for c in campaigns},
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )


def test_get_active_campaign_returns_session_campaign(app) -> None:
    """Verify the helper returns the campaign stored in the session when it still exists."""
    # Given two campaigns, one of which is in the session
    older = CampaignFactory.build(name="Older", date_modified=datetime(2025, 1, 1, tzinfo=UTC))
    newer = CampaignFactory.build(name="Newer", date_modified=datetime(2026, 1, 1, tzinfo=UTC))
    ctx = _build_ctx([older, newer])

    with app.test_request_context():
        g.global_context = ctx
        session["last_campaign_id"] = older.id

        # When resolving the active campaign
        result = get_active_campaign()

    # Then the session campaign is returned, not the most recent
    assert result is not None
    assert result.id == older.id


def test_get_active_campaign_falls_back_to_most_recent(app) -> None:
    """Verify the helper returns the most-recently-modified campaign with no session key."""
    # Given two campaigns and no session entry
    older = CampaignFactory.build(name="Older", date_modified=datetime(2025, 1, 1, tzinfo=UTC))
    newer = CampaignFactory.build(name="Newer", date_modified=datetime(2026, 1, 1, tzinfo=UTC))
    ctx = _build_ctx([older, newer])

    with app.test_request_context():
        g.global_context = ctx

        # When resolving the active campaign
        result = get_active_campaign()

    # Then the most-recently-modified campaign is returned
    assert result is not None
    assert result.id == newer.id


def test_get_active_campaign_falls_back_when_session_points_to_deleted_campaign(app) -> None:
    """Verify a stale session id falls through to the most-recently-modified campaign."""
    # Given two existing campaigns and a session pointing to a deleted one
    older = CampaignFactory.build(name="Older", date_modified=datetime(2025, 1, 1, tzinfo=UTC))
    newer = CampaignFactory.build(name="Newer", date_modified=datetime(2026, 1, 1, tzinfo=UTC))
    ctx = _build_ctx([older, newer])

    with app.test_request_context():
        g.global_context = ctx
        session["last_campaign_id"] = "deleted-campaign-id"

        # When resolving the active campaign
        result = get_active_campaign()

    # Then the fallback kicks in and returns the newer campaign
    assert result is not None
    assert result.id == newer.id


def test_get_active_campaign_returns_none_when_user_has_no_campaigns(app) -> None:
    """Verify the helper returns None when the user has zero campaigns."""
    # Given a global context with no campaigns
    ctx = _build_ctx([])

    with app.test_request_context():
        g.global_context = ctx

        # When resolving the active campaign
        result = get_active_campaign()

    # Then None is returned
    assert result is None


def test_get_active_campaign_returns_none_when_context_is_missing(app) -> None:
    """Verify the helper returns None when g.global_context is unset (unauthenticated pages)."""
    # Given a request context with no g.global_context attribute
    with app.test_request_context():
        # When resolving the active campaign
        result = get_active_campaign()

    # Then None is returned instead of raising AttributeError
    assert result is None


class TestChapterHelpers:
    """Tests for chapter-reading helpers in lib/api.py."""

    def test_get_chapters_for_book_returns_chapters_sorted_by_number(self, app) -> None:
        """Verify chapters are returned in ascending number order."""
        # Given a global context with out-of-order chapters for one book
        ch3 = CampaignChapterFactory.build(id="ch3", book_id="b1", number=3)
        ch1 = CampaignChapterFactory.build(id="ch1", book_id="b1", number=1)
        ch2 = CampaignChapterFactory.build(id="ch2", book_id="b1", number=2)

        ctx = build_global_context(
            user_role="PLAYER",
            chapters_by_book={"b1": [ch3, ch1, ch2]},
        )

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching chapters for the book
            result = get_chapters_for_book("b1")

        # Then they are sorted by number
        assert [c.id for c in result] == ["ch1", "ch2", "ch3"]

    def test_get_chapters_for_book_returns_empty_list_for_unknown_book(self, app) -> None:
        """Verify an empty list is returned when the book id is not in the context."""
        ctx = build_global_context(user_role="PLAYER")

        with app.test_request_context("/"):
            g.global_context = ctx

            result = get_chapters_for_book("missing")

        assert result == []

    def test_get_chapter_count_for_campaign_sums_across_books(self, app) -> None:
        """Verify chapter count sums len of chapters across every book in the campaign."""
        campaign = CampaignFactory.build(id="camp1")
        book_a = CampaignBookFactory.build(id="book-a", campaign_id="camp1")
        book_b = CampaignBookFactory.build(id="book-b", campaign_id="camp1")
        chapters_a = [CampaignChapterFactory.build(book_id="book-a") for _ in range(3)]
        chapters_b = [CampaignChapterFactory.build(book_id="book-b") for _ in range(2)]

        ctx = build_global_context(
            user_role="PLAYER",
            campaign=campaign,
            books_by_campaign={"camp1": [book_a, book_b]},
            chapters_by_book={"book-a": chapters_a, "book-b": chapters_b},
        )

        with app.test_request_context("/"):
            g.global_context = ctx
            assert get_chapter_count_for_campaign("camp1") == 5

    def test_get_chapter_count_for_campaign_returns_zero_when_no_books(self, app) -> None:
        """Verify zero is returned when the campaign has no books."""
        campaign = CampaignFactory.build(id="camp1")
        ctx = build_global_context(user_role="PLAYER", campaign=campaign)

        with app.test_request_context("/"):
            g.global_context = ctx
            assert get_chapter_count_for_campaign("camp1") == 0
