"""Tests for vweb.lib.api data-access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from flask import g, session
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    DicerollFactory,
    Routes,
    TraitFactory,
    UserFactory,
)
from werkzeug.exceptions import NotFound

from tests.conftest import make_dice_roll_result
from tests.helpers import build_global_context
from vweb.lib.api import (
    fetch_book_or_404,
    fetch_chapter_or_404,
    get_active_campaign,
    get_characters_for_campaign,
)
from vweb.lib.cache.dicerolls import recent
from vweb.lib.cache.global_context import GlobalContext

if TYPE_CHECKING:
    from vclient.models import Character


def _build_ctx(campaigns: list) -> GlobalContext:
    """Build a GlobalContext for helper tests without hitting the API."""
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    return GlobalContext(
        company=company,
        users=[user],
        campaigns=campaigns,
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


class TestFetchBookOr404:
    """Tests for the ``fetch_book_or_404`` lookup helper in lib/api.py."""

    def test_returns_book_and_campaign_when_both_exist(self, app, mocker) -> None:
        """Verify the helper returns the (book, campaign) pair when both exist."""
        # Given a campaign in the context and a book returned by the lazy cache
        campaign = CampaignFactory.build(id="camp1")
        book = CampaignBookFactory.build(id="b1", campaign_id="camp1")
        ctx = build_global_context(user_role="PLAYER", campaign=campaign)
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[book])

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching the book
            result_book, result_campaign = fetch_book_or_404("camp1", "b1")

        # Then both the book and campaign are returned
        assert result_book.id == "b1"
        assert result_campaign.id == "camp1"

    def test_aborts_404_when_campaign_missing(self, app, mocker) -> None:
        """Verify the helper aborts 404 when the campaign is not in the context."""
        # Given a context whose campaign id does not match the request
        ctx = build_global_context(user_role="PLAYER", campaign=CampaignFactory.build(id="other"))
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[])

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching a book for an unknown campaign, then it aborts 404
            with pytest.raises(NotFound):
                fetch_book_or_404("camp1", "b1")

    def test_aborts_404_when_book_missing(self, app, mocker) -> None:
        """Verify the helper aborts 404 when the book is absent from the cache result."""
        # Given a valid campaign but a book cache that omits the requested book
        campaign = CampaignFactory.build(id="camp1")
        ctx = build_global_context(user_role="PLAYER", campaign=campaign)
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[])

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching a missing book, then it aborts 404
            with pytest.raises(NotFound):
                fetch_book_or_404("camp1", "b1")


class TestFetchChapterOr404:
    """Tests for the ``fetch_chapter_or_404`` lookup helper in lib/api.py."""

    def test_returns_chapter_when_present(self, app, mocker) -> None:
        """Verify the helper returns the chapter when present in the cache result."""
        # Given a chapter returned by the lazy chapter cache
        chapter = CampaignChapterFactory.build(id="ch1", book_id="b1")
        ctx = build_global_context(user_role="PLAYER")
        mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=[chapter])

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching the chapter
            result = fetch_chapter_or_404("camp1", "b1", "ch1")

        # Then the matching chapter is returned
        assert result.id == "ch1"

    def test_aborts_404_when_chapter_missing(self, app, mocker) -> None:
        """Verify the helper aborts 404 when the chapter is absent from the cache result."""
        # Given a chapter cache that omits the requested chapter
        ctx = build_global_context(user_role="PLAYER")
        mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=[])

        with app.test_request_context("/"):
            g.global_context = ctx

            # When fetching a missing chapter, then it aborts 404
            with pytest.raises(NotFound):
                fetch_chapter_or_404("camp1", "b1", "ch1")


class TestRecentDicerolls:
    """Tests for the ``recent()`` function in lib/cache/dicerolls.py."""

    def _make_context(self, *, user, characters, campaign) -> GlobalContext:
        """Build a GlobalContext aligned with the user's role for the helper tests."""
        return build_global_context(
            user_role=user.role,
            user=user,
            campaign=campaign,
            characters=characters,
        )

    def test_resolves_trait_names_and_preserves_api_order(self, app, fake_vclient, mocker) -> None:
        """Verify trait names resolve and the API's newest-first order is preserved as-is."""
        # Given two player rolls returned by the API in newest-first order
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", role="PLAYER")
        player_char = CharacterFactory.build(
            id="char-player", type="PLAYER", name="Hero", campaign_id=campaign.id
        )
        strength = TraitFactory.build(id="t-str", name="Strength")
        brawl = TraitFactory.build(id="t-brawl", name="Brawl")
        newer = DicerollFactory.build(
            id="r-newer",
            character_id="char-player",
            user_id="user-1",
            dice_size=10,
            num_dice=5,
            trait_ids=["t-str", "t-brawl", "t-missing"],
            result=make_dice_roll_result(),
        )
        older = DicerollFactory.build(
            id="r-older",
            character_id="char-player",
            user_id="user-1",
            dice_size=6,
            num_dice=2,
            trait_ids=[],
            result=make_dice_roll_result(),
        )

        fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[newer, older])
        mocker.patch(
            "vweb.lib.cache.blueprint.traits",
            return_value={"t-str": strength, "t-brawl": brawl},
        )

        ctx = self._make_context(user=user, characters=[player_char], campaign=campaign)

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When fetching recent player dicerolls
            result = recent(campaign.id)

        # Then API order is preserved and trait names resolve (unknown ids silently dropped)
        assert [row.id for row in result] == ["r-newer", "r-older"]
        assert result[0].trait_names == ["Strength", "Brawl"]
        assert result[1].trait_names == []

    def test_passes_campaignid_and_limit_to_service(self, app, mocker) -> None:
        """Verify the campaign id scope and limit are forwarded to the dicerolls service."""
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", role="PLAYER")

        mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

        page = mocker.MagicMock(items=[])
        fake_service = mocker.MagicMock()
        fake_service.get_page.return_value = page
        service_factory = mocker.patch(
            "vweb.lib.cache.dicerolls.sync_dicerolls_service", return_value=fake_service
        )

        ctx = self._make_context(user=user, characters=[], campaign=campaign)

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            recent(campaign.id, limit=25)

        # Then the service is scoped to the requesting user and company
        service_factory.assert_called_once_with(on_behalf_of=user.id, company_id="test-company-id")
        # And the page fetch is scoped to the campaign with the requested limit,
        # with character_type="PLAYER" so the API drops storyteller/NPC rolls
        # before applying the limit.
        fake_service.get_page.assert_called_once_with(
            campaignid=campaign.id,
            characterid=None,
            userid=None,
            character_type="PLAYER",
            limit=25,
            offset=0,
        )

    def test_caches_per_scope_and_user(self, app, mocker) -> None:
        """Verify repeated identical scope+user reads hit the dicerolls service once."""
        # Given a request context with a requesting user and company
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            g.requesting_user = mocker.MagicMock(id="user-1")
            g.global_context = mocker.MagicMock(characters=[])
            from vweb.extensions import cache

            cache.clear()

            svc = mocker.patch("vweb.lib.cache.dicerolls.sync_dicerolls_service")
            page = mocker.MagicMock()
            page.items = []
            svc.return_value.get_page.return_value = page
            mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

            # When called twice with the same scope
            recent(campaign_id="camp-1", limit=25)
            recent(campaign_id="camp-1", limit=25)

            # Then the underlying service is hit only once
            svc.return_value.get_page.assert_called_once()

    def test_cache_isolates_per_requesting_user(self, app, mocker) -> None:
        """Verify the same scope cached for two different users triggers two service calls."""
        # Given a request context with a requesting user and company
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            g.requesting_user = mocker.MagicMock(id="user-1")
            g.global_context = mocker.MagicMock(characters=[])
            from vweb.extensions import cache

            cache.clear()

            svc = mocker.patch("vweb.lib.cache.dicerolls.sync_dicerolls_service")
            page = mocker.MagicMock()
            page.items = []
            svc.return_value.get_page.return_value = page
            mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

            # When called for two different requesting users in the same scope
            recent(campaign_id="camp-1", limit=25)
            g.requesting_user.id = "user-2"
            recent(campaign_id="camp-1", limit=25)

            # Then each user triggers its own service call
            assert svc.return_value.get_page.call_count == 2


class TestRecentDicerollsScopes:
    """Tests for scope-based filtering in the ``recent()`` function in lib/cache/dicerolls.py."""

    def test_character_id_scope_skips_player_filter(self, app, fake_vclient, mocker) -> None:
        """Verify character-scoped calls trust the API scope and do not set character_type."""
        # Given a diceroll for an NPC character (would be filtered out in campaign-only mode)
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", role="PLAYER")
        npc_char = CharacterFactory.build(
            id="npc-1", type="NPC", name="NPC", campaign_id=campaign.id
        )

        roll = DicerollFactory.build(
            id="r-npc",
            character_id="npc-1",
            user_id="user-1",
            dice_size=10,
            trait_ids=[],
            result=make_dice_roll_result(),
        )
        fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[roll])
        mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

        ctx = build_global_context(
            user_role=user.role, user=user, campaign=campaign, characters=[npc_char]
        )

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When requesting rolls scoped by character_id
            result = recent(campaign_id="", character_id="npc-1")

        # Then the NPC roll is returned (no PLAYER post-filter applied)
        assert len(result) == 1
        assert result[0].id == "r-npc"

    def test_user_id_scope_passes_userid_filter(self, app, mock_global_context, mocker) -> None:
        """Verify user-scoped calls pass userid to the underlying API."""
        # Given a mocked dicerolls service so we can inspect the API call
        from unittest.mock import MagicMock

        fake_service = MagicMock()
        fake_service.get_page.return_value = MagicMock(items=[])
        mocker.patch(
            "vweb.lib.cache.dicerolls.sync_dicerolls_service",
            autospec=True,
        ).return_value = fake_service
        mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

        # When requesting rolls scoped by user_id
        with app.test_request_context():
            g.requesting_user = mock_global_context.users[0]
            g.global_context = mock_global_context
            session["company_id"] = mock_global_context.company.id
            recent(campaign_id="", user_id="u-42")

        # Then userid="u-42" is forwarded to get_page, and character_type is unset
        # so non-player rolls for that user are still returned.
        fake_service.get_page.assert_called_once_with(
            campaignid=None,
            characterid=None,
            userid="u-42",
            character_type=None,
            limit=25,
            offset=0,
        )


class TestGetCharactersForCampaign:
    """Tests for ``get_characters_for_campaign``.

    The API already scopes the roster by role via the on-behalf-of header, so
    this helper performs no type filtering; it only reads the campaign's bucket
    from the context and sorts by name.
    """

    @staticmethod
    def _campaign_characters(campaign_id: str) -> list[Character]:
        """Build the real character types for the given campaign, name-unsorted."""
        return [
            CharacterFactory.build(type="STORYTELLER", name="Story One", campaign_id=campaign_id),
            CharacterFactory.build(type="PLAYER", name="Player One", campaign_id=campaign_id),
            CharacterFactory.build(type="NPC", name="Npc One", campaign_id=campaign_id),
        ]

    def test_returns_context_roster_sorted_without_filtering(self, app) -> None:
        """Verify the helper returns the campaign roster verbatim, sorted by name."""
        # Given a campaign whose context bucket already reflects API role scoping
        campaign = CampaignFactory.build(name="Visibility Campaign")
        ctx = build_global_context(
            user_role="PLAYER",
            campaign=campaign,
            characters=self._campaign_characters(campaign.id),
        )

        # When listing characters for the campaign
        with app.test_request_context():
            g.global_context = ctx
            characters = get_characters_for_campaign(campaign.id)

        # Then every character in the bucket is returned, sorted A-Z by name
        assert [character.name for character in characters] == [
            "Npc One",
            "Player One",
            "Story One",
        ]

    def test_returns_empty_list_for_unknown_campaign(self, app) -> None:
        """Verify an unknown campaign id yields an empty list, not an error."""
        # Given a context with no characters for the requested campaign
        ctx = build_global_context(user_role="PLAYER")

        # When listing characters for a campaign id not in the bucket
        with app.test_request_context():
            g.global_context = ctx
            characters = get_characters_for_campaign("missing-campaign-id")

        # Then the result is empty
        assert characters == []
