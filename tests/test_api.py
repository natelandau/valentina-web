"""Tests for vweb.lib.api data-access helpers."""

from __future__ import annotations

from datetime import UTC, datetime

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

from tests.conftest import make_dice_roll_result
from tests.helpers import build_global_context
from vweb.lib.api import (
    get_active_campaign,
    get_chapter_count_for_campaign,
    get_chapters_for_book,
    get_recent_player_dicerolls,
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


class TestGetRecentPlayerDicerolls:
    """Tests for get_recent_player_dicerolls helper in lib/api.py."""

    def _make_context(self, *, user, characters, campaign) -> GlobalContext:
        """Build a GlobalContext aligned with the user's role for the helper tests."""
        return build_global_context(
            user_role=user.role,
            user=user,
            campaign=campaign,
            characters=characters,
        )

    def test_filters_out_non_player_characters_and_rolls_without_character(
        self, app, fake_vclient, mocker
    ) -> None:
        """Verify only rolls for PLAYER-type characters in the campaign are returned."""
        # Given player, storyteller, and no-character rolls
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", username="alice", role="PLAYER")
        player_char = CharacterFactory.build(
            id="char-player", type="PLAYER", name="Hero", campaign_id=campaign.id
        )
        storyteller_char = CharacterFactory.build(
            id="char-st", type="STORYTELLER", name="Villain", campaign_id=campaign.id
        )

        player_roll = DicerollFactory.build(
            id="r1",
            character_id="char-player",
            user_id="user-1",
            dice_size=10,
            trait_ids=[],
            result=make_dice_roll_result(),
        )
        storyteller_roll = DicerollFactory.build(
            id="r2",
            character_id="char-st",
            user_id="user-1",
            dice_size=10,
            trait_ids=[],
            result=make_dice_roll_result(),
        )
        no_character_roll = DicerollFactory.build(
            id="r3",
            character_id=None,
            user_id="user-1",
            dice_size=10,
            trait_ids=[],
            result=make_dice_roll_result(),
        )

        fake_vclient.set_response(
            Routes.DICEROLLS_LIST,
            items=[player_roll, storyteller_roll, no_character_roll],
        )
        mocker.patch("vweb.lib.api.get_all_traits", return_value={})

        ctx = self._make_context(
            user=user, characters=[player_char, storyteller_char], campaign=campaign
        )

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When fetching recent player dicerolls
            result = get_recent_player_dicerolls(campaign.id)

        # Then only the player character's roll is kept
        assert [row.id for row in result] == ["r1"]
        assert result[0].character_name == "Hero"
        assert result[0].dice_size == 10

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
            "vweb.lib.api.get_all_traits",
            return_value={"t-str": strength, "t-brawl": brawl},
        )

        ctx = self._make_context(user=user, characters=[player_char], campaign=campaign)

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When fetching recent player dicerolls
            result = get_recent_player_dicerolls(campaign.id)

        # Then API order is preserved and trait names resolve (unknown ids silently dropped)
        assert [row.id for row in result] == ["r-newer", "r-older"]
        assert result[0].trait_names == ["Strength", "Brawl"]
        assert result[1].trait_names == []

    def test_passes_campaignid_and_limit_to_service(self, app, mocker) -> None:
        """Verify the campaign id scope and limit are forwarded to the dicerolls service."""
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", role="PLAYER")

        mocker.patch("vweb.lib.api.get_all_traits", return_value={})

        page = mocker.MagicMock(items=[])
        fake_service = mocker.MagicMock()
        fake_service.get_page.return_value = page
        service_factory = mocker.patch(
            "vweb.lib.api.sync_dicerolls_service", return_value=fake_service
        )

        ctx = self._make_context(user=user, characters=[], campaign=campaign)

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            get_recent_player_dicerolls(campaign.id, limit=25)

        # Then the service is scoped to the requesting user and company
        service_factory.assert_called_once_with(on_behalf_of=user.id, company_id="test-company-id")
        # And the page fetch is scoped to the campaign with the requested limit
        fake_service.get_page.assert_called_once_with(
            campaignid=campaign.id,
            characterid=None,
            userid=None,
            limit=25,
            offset=0,
        )


class TestGetRecentPlayerDicerollsScopes:
    """Tests for scope-based filtering in get_recent_player_dicerolls."""

    def test_character_id_scope_skips_player_filter(self, app, fake_vclient, mocker) -> None:
        """Verify character-scoped calls pass character_id to the API and skip the PLAYER post-filter."""
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
        mocker.patch("vweb.lib.api.get_all_traits", return_value={})

        ctx = build_global_context(
            user_role=user.role, user=user, campaign=campaign, characters=[npc_char]
        )

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When requesting rolls scoped by character_id
            result = get_recent_player_dicerolls(campaign_id="", character_id="npc-1")

        # Then the NPC roll is returned (no PLAYER post-filter applied)
        assert len(result) == 1
        assert result[0].id == "r-npc"

    def test_user_id_scope_passes_userid_filter(self, app, mock_global_context, mocker) -> None:
        """Verify user-scoped calls pass userid to the underlying API."""
        # Given a mocked dicerolls service so we can inspect the API call
        from unittest.mock import MagicMock

        from vweb.lib.api import get_recent_player_dicerolls

        fake_service = MagicMock()
        fake_service.get_page.return_value = MagicMock(items=[])
        mocker.patch(
            "vweb.lib.api.sync_dicerolls_service",
            autospec=True,
        ).return_value = fake_service
        mocker.patch("vweb.lib.api.get_all_traits", return_value={})

        # When requesting rolls scoped by user_id
        with app.test_request_context():
            g.requesting_user = mock_global_context.users[0]
            g.global_context = mock_global_context
            session["company_id"] = mock_global_context.company.id
            get_recent_player_dicerolls(campaign_id="", user_id="u-42")

        # Then userid="u-42" is forwarded to get_page
        fake_service.get_page.assert_called_once_with(
            campaignid=None,
            characterid=None,
            userid="u-42",
            limit=50,
            offset=0,
        )

    def test_campaign_only_still_applies_player_filter(self, app, fake_vclient, mocker) -> None:
        """Verify campaign-only scope preserves the PLAYER-characters post-filter."""
        # Given an NPC roll in a campaign (NPC character not in the campaign's PLAYER list)
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1", role="PLAYER")
        player_char = CharacterFactory.build(
            id="char-player", type="PLAYER", name="Hero", campaign_id=campaign.id
        )

        roll = DicerollFactory.build(
            id="r-npc",
            character_id="not-a-player-character",
            user_id="user-1",
            dice_size=10,
            trait_ids=[],
            result=make_dice_roll_result(),
        )
        fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[roll])
        mocker.patch("vweb.lib.api.get_all_traits", return_value={})

        ctx = build_global_context(
            user_role=user.role, user=user, campaign=campaign, characters=[player_char]
        )

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            g.global_context = ctx
            g.requesting_user = user

            # When requesting rolls with only a campaign scope
            result = get_recent_player_dicerolls(campaign_id=campaign.id)

        # Then the roll is filtered out
        assert result == []
