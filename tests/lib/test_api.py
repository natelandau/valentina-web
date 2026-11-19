"""Tests for vweb.lib.api data-access helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from flask import g, session
from werkzeug.exceptions import NotFound

from tests.conftest import make_dice_roll_result
from tests.helpers import build_global_context
from vweb.api_client import campaigns_service
from vweb.api_client.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignExperienceFactory,
    CampaignFactory,
    CharacterFactory,
    DicerollFactory,
    NoteFactory,
    Routes,
    TraitFactory,
    UserFactory,
)
from vweb.lib.api import (
    count_notes,
    fetch_book_or_404,
    fetch_chapter_or_404,
    get_active_campaign,
    get_character_and_campaign,
    get_characters_for_campaign,
    get_selectable_characters,
    get_user_campaign_experience,
    resolve_characters,
    validate_and_submit_experience,
)
from vweb.lib.cache.dicerolls import recent

if TYPE_CHECKING:
    from vweb.api_client.models import Character
    from vweb.lib.cache.global_context import GlobalContext


_OLDER = CampaignFactory.build(id="older", date_modified=datetime(2025, 1, 1, tzinfo=UTC))
_NEWER = CampaignFactory.build(id="newer", date_modified=datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    ("campaigns", "remembered", "expected"),
    [
        pytest.param([_OLDER, _NEWER], "older", "older", id="remembered"),
        pytest.param([_OLDER, _NEWER], None, "newer", id="most-recent"),
        pytest.param([_OLDER, _NEWER], "deleted", "newer", id="stale-remembered"),
        pytest.param([], None, None, id="no-campaigns"),
    ],
)
def test_get_active_campaign(app, campaigns, remembered, expected) -> None:
    """Verify the remembered campaign wins while it exists, else the most recently modified."""
    with app.test_request_context():
        g.global_context = build_global_context(user_role="PLAYER", campaigns=campaigns)
        if remembered:
            session["last_campaign_id"] = remembered

        result = get_active_campaign()

    assert (result.id if result else None) == expected


def test_get_active_campaign_without_context(app) -> None:
    """Verify pages without a loaded context (unauthenticated) get None instead of an error."""
    with app.test_request_context():
        assert get_active_campaign() is None


def test_get_character_and_campaign(app) -> None:
    """Verify a character resolves with its campaign, and an unknown id resolves to nothing."""
    campaign = CampaignFactory.build(id="camp1")
    hero = CharacterFactory.build(id="hero", campaign_id="camp1")

    with app.test_request_context():
        g.global_context = build_global_context(user_role="PLAYER", campaign=campaign)
        g.global_context.characters = [hero]

        assert get_character_and_campaign("hero") == (hero, campaign)
        assert get_character_and_campaign("missing") == (None, None)


def test_get_user_campaign_experience(app) -> None:
    """Verify a user's experience is found per campaign, and None for unknown users or campaigns."""
    exp = CampaignExperienceFactory.build(campaign_id="camp1")
    user = UserFactory.build(id="test-user-id", campaign_experience=[exp])

    with app.test_request_context():
        g.global_context = build_global_context(user_role="PLAYER", user=user)

        assert get_user_campaign_experience("test-user-id", "camp1") == exp
        assert get_user_campaign_experience("test-user-id", "other") is None
        assert get_user_campaign_experience("nobody", "camp1") is None


@pytest.mark.parametrize(
    ("context_campaign", "books"),
    [
        pytest.param("other", [], id="campaign-missing"),
        pytest.param("camp1", [], id="book-missing"),
        pytest.param("camp1", [CampaignBookFactory.build(id="b1")], id="found"),
    ],
)
def test_fetch_book_or_404(app, mocker, context_campaign: str, books: list) -> None:
    """Verify the book and its campaign are returned only when both exist, else 404."""
    campaign = CampaignFactory.build(id=context_campaign)
    mocker.patch("vweb.lib.cache.campaign_content.books", return_value=books)

    with app.test_request_context("/"):
        g.global_context = build_global_context(user_role="PLAYER", campaign=campaign)

        if context_campaign == "camp1" and books:
            assert fetch_book_or_404("camp1", "b1") == (books[0], campaign)
        else:
            with pytest.raises(NotFound):
                fetch_book_or_404("camp1", "b1")


@pytest.mark.parametrize("found", [True, False])
def test_fetch_chapter_or_404(app, mocker, *, found: bool) -> None:
    """Verify the chapter is returned when the book lists it, else 404."""
    chapter = CampaignChapterFactory.build(id="ch1", book_id="b1")
    mocker.patch(
        "vweb.lib.cache.campaign_content.chapters", return_value=[chapter] if found else []
    )

    with app.test_request_context("/"):
        g.global_context = build_global_context(user_role="PLAYER")

        if found:
            assert fetch_chapter_or_404("camp1", "b1", "ch1") is chapter
        else:
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
        user = UserFactory.build(id="user-1")
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
            session["user_id"] = user.id
            g.global_context = ctx
            g.requesting_user = user

            # When fetching recent player dicerolls
            result = recent(campaign.id)

        # Then API order is preserved and trait names resolve (unknown ids silently dropped)
        assert [row.id for row in result] == ["r-newer", "r-older"]
        assert result[0].trait_names == ["Strength", "Brawl"]
        assert result[1].trait_names == []

    def test_passes_campaignid_and_limit_to_service(self, app, fake_vclient, mocker) -> None:
        """Verify the campaign id scope and limit are forwarded to the dicerolls API."""
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1")

        mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})
        fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[])

        ctx = self._make_context(user=user, characters=[], campaign=campaign)

        with app.test_request_context("/"):
            session["company_id"] = "test-company-id"
            session["user_id"] = user.id
            g.global_context = ctx
            g.requesting_user = user

            recent(campaign.id, limit=25)

        # Then the request is scoped to the requesting user and company
        (request,) = fake_vclient.assert_called(
            Routes.DICEROLLS_LIST, params={"company_id": "test-company-id"}, times=1
        )
        assert request.headers["on-behalf-of"] == user.id
        # And the page fetch is scoped to the campaign with the requested limit,
        # with character_type="PLAYER" so the API drops storyteller/NPC rolls
        # before applying the limit.
        assert request.query == {
            "campaignid": campaign.id,
            "character_type": "PLAYER",
            "limit": "25",
            "offset": "0",
        }

    def test_caches_per_scope_and_user(self, app, fake_vclient, mocker) -> None:
        """Verify repeated identical scope+user reads hit the dicerolls service once."""
        # Given a request context with a requesting user and company
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            session["user_id"] = "user-1"
            g.requesting_user = mocker.MagicMock(id="user-1")
            g.global_context = mocker.MagicMock(characters=[])
            from vweb.extensions import cache

            cache.clear()

            fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[])
            mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

            # When called twice with the same scope
            recent(campaign_id="camp-1", limit=25)
            recent(campaign_id="camp-1", limit=25)

            # Then the API is hit only once
            fake_vclient.assert_called(
                Routes.DICEROLLS_LIST, query={"campaignid": "camp-1"}, times=1
            )

    def test_cache_isolates_per_requesting_user(self, app, fake_vclient, mocker) -> None:
        """Verify the same scope cached for two different users triggers two service calls."""
        # Given a request context with a requesting user and company
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            session["user_id"] = "user-1"
            g.requesting_user = mocker.MagicMock(id="user-1")
            g.global_context = mocker.MagicMock(characters=[])
            from vweb.extensions import cache

            cache.clear()

            fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[])
            mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

            # When called for two different requesting users in the same scope
            recent(campaign_id="camp-1", limit=25)
            session["user_id"] = "user-2"
            recent(campaign_id="camp-1", limit=25)

            # Then each user triggers its own API call
            (first, second) = fake_vclient.assert_called(Routes.DICEROLLS_LIST, times=2)
            assert first.headers["on-behalf-of"] == "user-1"
            assert second.headers["on-behalf-of"] == "user-2"


class TestRecentDicerollsScopes:
    """Tests for scope-based filtering in the ``recent()`` function in lib/cache/dicerolls.py."""

    def test_character_id_scope_skips_player_filter(self, app, fake_vclient, mocker) -> None:
        """Verify character-scoped calls trust the API scope and do not set character_type."""
        # Given a diceroll for an NPC character (would be filtered out in campaign-only mode)
        campaign = CampaignFactory.build(id="camp-1")
        user = UserFactory.build(id="user-1")
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
            session["user_id"] = user.id
            g.global_context = ctx
            g.requesting_user = user

            # When requesting rolls scoped by character_id
            result = recent(campaign_id="", character_id="npc-1")

        # Then the NPC roll is returned (no PLAYER post-filter applied)
        assert len(result) == 1
        assert result[0].id == "r-npc"

    def test_user_id_scope_passes_userid_filter(
        self, app, mock_global_context, fake_vclient, mocker
    ) -> None:
        """Verify user-scoped calls pass userid to the underlying API."""
        # Given the API returns no rolls
        fake_vclient.set_response(Routes.DICEROLLS_LIST, items=[])
        mocker.patch("vweb.lib.cache.blueprint.traits", return_value={})

        # When requesting rolls scoped by user_id
        with app.test_request_context():
            g.requesting_user = mock_global_context.users[0]
            g.global_context = mock_global_context
            session["company_id"] = mock_global_context.company.id
            session["user_id"] = mock_global_context.users[0].id
            recent(campaign_id="", user_id="u-42")

        # Then userid="u-42" is sent, and character_type is unset
        # so non-player rolls for that user are still returned.
        (request,) = fake_vclient.assert_called(Routes.DICEROLLS_LIST, times=1)
        assert request.query == {"userid": "u-42", "limit": "25", "offset": "0"}


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


class TestGetSelectableCharacters:
    """Tests for ``get_selectable_characters``."""

    def test_returns_only_player_and_npc_sorted(self, app) -> None:
        """Verify only PLAYER and NPC characters are returned, name-sorted."""
        # Given a campaign whose roster includes every character type
        campaign = CampaignFactory.build(name="Picker Campaign")
        roster = [
            CharacterFactory.build(type="STORYTELLER", name="Story One", campaign_id=campaign.id),
            CharacterFactory.build(type="PLAYER", name="Zed Player", campaign_id=campaign.id),
            CharacterFactory.build(type="NPC", name="Amy NPC", campaign_id=campaign.id),
        ]
        ctx = build_global_context(user_role="STORYTELLER", campaign=campaign, characters=roster)

        # When listing selectable characters
        with app.test_request_context():
            g.global_context = ctx
            result = get_selectable_characters(campaign.id)

        # Then storyteller characters are excluded and the rest are name-sorted
        assert [c.name for c in result] == ["Amy NPC", "Zed Player"]


class TestResolveCharacters:
    """Tests for ``resolve_characters``."""

    def test_resolves_ids_to_characters_sorted_dropping_unknown(self, app) -> None:
        """Verify known ids resolve to name-sorted characters and unknown ids are dropped."""
        # Given a campaign roster
        campaign = CampaignFactory.build(name="Resolve Campaign")
        hero = CharacterFactory.build(
            id="c-hero", type="PLAYER", name="Hero", campaign_id=campaign.id
        )
        villain = CharacterFactory.build(
            id="c-vil", type="NPC", name="Villain", campaign_id=campaign.id
        )
        ctx = build_global_context(
            user_role="PLAYER", campaign=campaign, characters=[hero, villain]
        )

        # When resolving a mix of known and unknown ids
        with app.test_request_context():
            g.global_context = ctx
            result = resolve_characters(campaign.id, ["c-vil", "c-hero", "c-missing"])

        # Then only the known characters are returned, name-sorted
        assert [c.id for c in result] == ["c-hero", "c-vil"]

    def test_empty_ids_returns_empty(self, app) -> None:
        """Verify an empty id list returns an empty list without touching the roster."""
        # Given any context
        ctx = build_global_context(user_role="PLAYER")

        # When resolving an empty id list
        with app.test_request_context():
            g.global_context = ctx
            result = resolve_characters("any-campaign", [])

        # Then the result is empty
        assert result == []


class TestValidateAndSubmitExperience:
    """Tests for validate_and_submit_experience."""

    @staticmethod
    def _submit(app, form_data: dict) -> list[str]:
        with app.test_request_context():
            session["company_id"] = "company-1"
            session["user_id"] = "st1"
            return validate_and_submit_experience(form_data, user_id="u1", campaign_id="c1")

    @pytest.mark.parametrize(
        "form_data",
        [
            pytest.param({"xp": "-5", "cool_points": "0"}, id="negative-xp"),
            pytest.param({"xp": "0", "cool_points": "-1"}, id="negative-cool-points"),
            pytest.param({"xp": "0", "cool_points": "0"}, id="all-zero"),
            pytest.param({"xp": "abc", "cool_points": "1"}, id="non-integer-xp"),
            pytest.param({"xp": "1", "cool_points": "1.5"}, id="non-integer-cool-points"),
        ],
    )
    def test_rejects_invalid_amounts_without_calling_the_api(
        self, app, fake_vclient, form_data: dict
    ) -> None:
        """Verify non-integer, zero, and negative amounts return an error and send nothing."""
        assert len(self._submit(app, form_data)) == 1
        assert fake_vclient.requests == []

    @pytest.mark.parametrize(
        ("xp", "cool_points"),
        [(3, 0), (0, 2), (3, 2)],
        ids=["xp-only", "cool-points-only", "both"],
    )
    def test_submits_only_positive_amounts(
        self, app, fake_vclient, mocker, xp: int, cool_points: int
    ) -> None:
        """Verify each positive amount is granted as the signed-in user and zero ones are skipped."""
        clear = mocker.patch("vweb.lib.api.cache.global_context.clear_current")

        errors = self._submit(app, {"xp": str(xp), "cool_points": str(cool_points)})

        assert errors == []
        clear.assert_called_once()
        for route, amount in (
            (Routes.USERS_EXPERIENCE_XP_ADD, xp),
            (Routes.USERS_EXPERIENCE_CP_ADD, cool_points),
        ):
            if amount:
                (request,) = fake_vclient.assert_called(
                    route,
                    params={"company_id": "company-1", "user_id": "u1"},
                    json={"amount": amount, "campaign_id": "c1"},
                    times=1,
                )
                assert request.headers["on-behalf-of"] == "st1"
            else:
                fake_vclient.assert_not_called(route)

    @pytest.mark.parametrize(
        ("refused_route", "form_data", "xp_reset", "cache_cleared"),
        [
            # A refused XP grant stops before cool points
            pytest.param(
                Routes.USERS_EXPERIENCE_XP_ADD,
                {"xp": "99999", "cool_points": "1"},
                False,
                False,
                id="xp",
            ),
            # XP already landed, so XP resets to stop a resubmit granting it twice
            pytest.param(
                Routes.USERS_EXPERIENCE_CP_ADD,
                {"xp": "5", "cool_points": "99"},
                True,
                True,
                id="cp-after-xp",
            ),
            pytest.param(
                Routes.USERS_EXPERIENCE_CP_ADD,
                {"xp": "0", "cool_points": "99"},
                False,
                False,
                id="cp-alone",
            ),
        ],
    )
    def test_refused_grant_shows_the_api_reason(
        self, app, fake_vclient, mocker, *, refused_route, form_data, xp_reset, cache_cleared
    ) -> None:
        """Verify an API refusal shows its reason and only resets XP once XP was granted."""
        fake_vclient.set_error(
            refused_route,
            status_code=400,
            invalid_parameters=[{"field": "amount", "message": "Too many"}],
        )
        clear = mocker.patch("vweb.lib.api.cache.global_context.clear_current")
        xp_before = form_data["xp"]

        errors = self._submit(app, form_data)

        assert len(errors) == 1
        assert "Too many" in errors[0]
        assert form_data["xp"] == ("0" if xp_reset else xp_before)
        assert clear.called is cache_cleared
        if refused_route == Routes.USERS_EXPERIENCE_XP_ADD:
            fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_CP_ADD)

    @pytest.mark.parametrize(
        ("failing_route", "form_data", "xp_reset"),
        [
            pytest.param(
                Routes.USERS_EXPERIENCE_XP_ADD, {"xp": "3", "cool_points": "2"}, True, id="xp"
            ),
            pytest.param(
                Routes.USERS_EXPERIENCE_CP_ADD,
                {"xp": "5", "cool_points": "2"},
                True,
                id="cp-after-xp",
            ),
            pytest.param(
                Routes.USERS_EXPERIENCE_CP_ADD,
                {"xp": "0", "cool_points": "2"},
                False,
                id="cp-alone",
            ),
        ],
    )
    def test_server_error_is_an_unknown_outcome(
        self, app, fake_vclient, mocker, failing_route, form_data, xp_reset
    ) -> None:
        """Verify a 5xx, which may follow an applied grant, asks the user to check the total.

        The context is refreshed, XP resets so a resubmit cannot grant it twice, and the
        server's detail is never shown.
        """
        fake_vclient.set_error(failing_route, status_code=500, detail="db exploded")
        clear = mocker.patch("vweb.lib.api.cache.global_context.clear_current")
        xp_before = form_data["xp"]

        errors = self._submit(app, form_data)

        assert len(errors) == 1
        assert "db exploded" not in errors[0]
        assert form_data["xp"] == ("0" if xp_reset else xp_before)
        clear.assert_called_once()
        if failing_route == Routes.USERS_EXPERIENCE_XP_ADD:
            fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_CP_ADD)

    def test_unreachable_api_is_an_unknown_outcome(self, app, fake_vclient, mocker) -> None:
        """Verify a network failure is reported, not raised, and resets XP like a 5xx."""
        fake_vclient.set_connection_error(Routes.USERS_EXPERIENCE_XP_ADD)
        clear = mocker.patch("vweb.lib.api.cache.global_context.clear_current")
        form_data = {"xp": "5", "cool_points": "2"}

        errors = self._submit(app, form_data)

        assert len(errors) == 1
        assert form_data["xp"] == "0"
        fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_CP_ADD)
        clear.assert_called_once()


def test_count_notes_returns_api_total(app, fake_vclient) -> None:
    """Verify count_notes reports the API's total, not the size of the first page."""
    # Given a campaign whose notes span more than one page
    fake_vclient.set_response(Routes.CAMPAIGNS_NOTES_LIST, items=NoteFactory.batch(3))

    # When counting the campaign's notes
    with app.app_context():
        svc = campaigns_service(on_behalf_of="user-1", company_id="company-1")
        count = count_notes(svc, "campaign-1")

    # Then the count is the paginated total
    assert count == 3


def test_count_notes_returns_zero_on_api_error(app, fake_vclient) -> None:
    """Verify count_notes falls back to zero when the notes endpoint fails."""
    # Given a notes endpoint that errors
    fake_vclient.set_error(Routes.CAMPAIGNS_NOTES_LIST, status_code=500)

    # When counting the campaign's notes
    with app.app_context():
        svc = campaigns_service(on_behalf_of="user-1", company_id="company-1")
        count = count_notes(svc, "campaign-1")

    # Then the count is zero
    assert count == 0
