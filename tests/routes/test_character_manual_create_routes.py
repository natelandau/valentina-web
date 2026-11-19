"""Tests for manual character creation routes."""

from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Literal

import pytest

from tests.conftest import htmx_post
from tests.helpers import assert_shows_error, session_flashes, setup_form_options
from vweb.api_client.testing import (
    BulkAssignTraitFailureFactory,
    BulkAssignTraitResponseFactory,
    CharacterConceptFactory,
    CharacterFactory,
    CompanyFactory,
    Routes,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask.testing import FlaskClient, TestResponse

    from vweb.api_client.models import Campaign, Character

_PROFILE = {
    "name_first": "Ada",
    "name_last": "Lovelace",
    "game_version": "V5",
    "character_class": "MORTAL",
}


def _mock_form_options(mocker) -> None:
    """Mock fetch_form_options for the manual create routes."""
    setup_form_options(
        mocker,
        "vweb.routes.character_create.manual_views.fetch_form_options",
        character_classes=["VAMPIRE", "WEREWOLF"],
        experience_levels=[],
        skill_focuses=[],
        concepts=CharacterConceptFactory.batch(2),
        vampire_clans=VampireClanFactory.batch(2),
        werewolf_tribes=WerewolfTribeFactory.batch(1),
        werewolf_auspices=WerewolfAuspiceFactory.batch(1),
    )


@pytest.fixture
def use_campaign(mocker, use_context) -> Callable[..., Campaign]:
    """Return a function that serves a context and the form options, returning its campaign."""

    def _use(
        role: str = "PLAYER",
        *,
        characters: list[Character] | None = None,
        manage_npc: Literal["UNRESTRICTED", "STORYTELLER"] = "STORYTELLER",
    ) -> Campaign:
        company = CompanyFactory.build()
        company.settings.permission_manage_npc = manage_npc
        ctx = use_context(user_role=role, company=company, characters=characters)
        _mock_form_options(mocker)
        return ctx.campaigns[0]

    return _use


def _post_profile(
    client: FlaskClient, campaign_id: str, query: str = "", **fields: str
) -> TestResponse:
    return htmx_post(
        client, f"/campaign/{campaign_id}/characters/profile_edit{query}", {**_PROFILE, **fields}
    )


def _seed_temp_character(client: FlaskClient, char_id: str, *, age_seconds: float = 0) -> None:
    with client.session_transaction() as sess:
        sess["temp_character_id"] = char_id
        sess["temp_character_created_at"] = time.time() - age_seconds


def _offered_character_types(body: str) -> list[str]:
    select = re.search(r'<select name="character_type".*?</select>', body, re.DOTALL)
    if select:
        return re.findall(r'<option value="([A-Z]+)"', select.group(0))
    hidden = re.search(r'<input type="hidden" name="character_type" value="([A-Z]+)"', body)
    return [hidden.group(1)] if hidden else []


class TestManualProfileView:
    """Tests for GET /campaign/<id>/characters/profile_edit."""

    def test_renders_profile_form(self, client, use_campaign) -> None:
        """Verify the profile form renders for an authenticated player."""
        # Given a campaign in global context
        campaign = use_campaign()

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then the page renders with the profile fields
        body = response.get_data(as_text=True)
        assert 'name="name_first"' in body
        assert 'name="character_class"' in body

    def test_options_without_game_versions_are_not_hidden(
        self, client, mocker, use_campaign
    ) -> None:
        """Verify options with an empty game_versions list are never hidden by the version filter."""
        # Given form options where werewolf tribes/auspices carry no game_versions
        # (the real blueprint data leaves these untagged, unlike vampire clans)
        campaign = use_campaign()
        setup_form_options(
            mocker,
            "vweb.routes.character_create.manual_views.fetch_form_options",
            character_classes=["VAMPIRE", "WEREWOLF"],
            experience_levels=[],
            skill_focuses=[],
            concepts=[],
            vampire_clans=[],
            werewolf_tribes=[WerewolfTribeFactory.build(name="Black Furies", game_versions=[])],
            werewolf_auspices=[WerewolfAuspiceFactory.build(name="Ahroun", game_versions=[])],
        )

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then the empty-version options render without the always-hide filter that
        # would otherwise suppress every option once a game version is selected
        body = response.get_data(as_text=True)
        assert "Black Furies" in body
        assert "Ahroun" in body
        assert "!''.split(','" not in body

    def test_returns_404_for_invalid_campaign(self, client) -> None:
        """Verify 404 for a non-existent campaign."""
        # When requesting with a bad campaign ID
        response = client.get("/campaign/nonexistent/characters/profile_edit")

        # Then 404 is returned
        assert response.status_code == 404

    @pytest.mark.parametrize(
        ("role", "manage_npc", "expected_types"),
        [
            ("PLAYER", "STORYTELLER", ["PLAYER"]),
            ("PLAYER", "UNRESTRICTED", ["PLAYER", "NPC"]),
            ("STORYTELLER", "STORYTELLER", ["PLAYER", "NPC", "STORYTELLER"]),
        ],
        ids=["restricted-player", "unrestricted-player", "storyteller"],
    )
    def test_offers_only_permitted_character_types(
        self, client, use_campaign, role, manage_npc, expected_types
    ) -> None:
        """Verify the type choice offers only the types the user may assign."""
        # Given a user with the given role and NPC setting
        campaign = use_campaign(role, manage_npc=manage_npc)

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then only the permitted types are offered
        offered = _offered_character_types(response.get_data(as_text=True))
        assert sorted(offered) == sorted(expected_types)

    def test_prefills_from_query_params(self, client, use_campaign) -> None:
        """Verify form is prefilled from query parameters (back button support)."""
        # Given a campaign
        campaign = use_campaign()

        # When requesting with query params
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?name_first=Ada&name_last=Lovelace"
        )

        # Then the form is prefilled
        body = response.get_data(as_text=True)
        assert 'value="Ada"' in body
        assert 'value="Lovelace"' in body

    def test_query_values_stay_inside_alpine_string_literals(self, client, use_campaign) -> None:
        """Verify quote characters in query values cannot break out of the x-data expression."""
        # Given a campaign
        campaign = use_campaign()
        payload = "';alert(1);'\""

        # When a link carries quote characters in the prefilled class and version
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit",
            query_string={"character_class": payload, "game_version": payload},
        )

        # Then the x-data expression Alpine evaluates holds each value as one string literal
        x_data = _x_data_containing(response.get_data(as_text=True), "charClass")
        for key in ("charClass", "gameVersion"):
            literal = re.search(rf'{key}: ("(?:[^"\\]|\\.)*")', x_data)
            assert literal is not None
            assert json.loads(literal.group(1)) == payload


class TestResumeTempCharacter:
    """Tests for returning to the profile step of an in-progress character."""

    def test_resume_prefills_from_temp_character(self, client, use_campaign, fake_vclient) -> None:
        """Verify resuming shows the in-progress character's saved profile."""
        # Given an in-progress character in the session
        campaign = use_campaign()
        fake_vclient.set_response(
            Routes.CHARACTERS_GET,
            model=CharacterFactory.build(id="temp-1", name_first="Saved", name_last="Draft"),
            params={"character_id": "temp-1"},
        )
        _seed_temp_character(client, "temp-1")

        # When resuming the profile step
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit?resume=1")

        # Then the saved profile fills the form and the draft stays in the session
        body = response.get_data(as_text=True)
        assert 'value="Saved"' in body
        assert 'value="Draft"' in body
        with client.session_transaction() as sess:
            assert sess["temp_character_id"] == "temp-1"

    def test_resume_falls_back_when_draft_cannot_load(
        self, client, use_campaign, fake_vclient
    ) -> None:
        """Verify a draft the API cannot return is dropped and the query values are used."""
        # Given an in-progress character the API no longer returns
        campaign = use_campaign()
        fake_vclient.set_error(Routes.CHARACTERS_GET, status_code=404)
        _seed_temp_character(client, "temp-1")

        # When resuming the profile step
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?resume=1&name_first=Fallback"
        )

        # Then the query values fill the form and the stale draft is forgotten
        assert 'value="Fallback"' in response.get_data(as_text=True)
        with client.session_transaction() as sess:
            assert "temp_character_id" not in sess

    def test_fresh_visit_forgets_draft(self, client, use_campaign, fake_vclient) -> None:
        """Verify opening the form without resume starts a new character."""
        # Given an in-progress character in the session
        campaign = use_campaign()
        _seed_temp_character(client, "temp-1")

        # When opening the form without resuming
        client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then the draft is forgotten and not fetched
        with client.session_transaction() as sess:
            assert "temp_character_id" not in sess
        fake_vclient.assert_not_called(Routes.CHARACTERS_GET)


class TestManualProfileCreate:
    """Tests for POST /campaign/<id>/characters/profile_edit in create mode."""

    def test_valid_profile_creates_temp_character(self, client, use_campaign, fake_vclient) -> None:
        """Verify a valid profile creates a temporary character and moves on to traits."""
        # Given an API that creates the draft
        campaign = use_campaign()
        fake_vclient.set_response(
            Routes.CHARACTERS_CREATE, model=CharacterFactory.build(id="temp-new")
        )

        # When submitting the profile
        response = _post_profile(client, campaign.id)

        # Then a temporary character is created for the user and remembered in the session
        fake_vclient.assert_called(
            Routes.CHARACTERS_CREATE,
            json_subset={
                **_PROFILE,
                "campaign_id": campaign.id,
                "is_temporary": True,
                "user_player_id": "test-user-id",
            },
            times=1,
        )
        with client.session_transaction() as sess:
            assert sess["temp_character_id"] == "temp-new"

        # And the traits step posts to the finalize endpoint
        body = response.get_data(as_text=True)
        assert f"/campaign/{campaign.id}/characters/profile_edit/create" in body

    def test_missing_name_rerenders_without_saving(
        self, client, use_campaign, fake_vclient
    ) -> None:
        """Verify an invalid profile keeps the user's input and is not sent to the API."""
        # Given a campaign
        campaign = use_campaign()

        # When submitting without a first name
        response = _post_profile(client, campaign.id, name_first="")

        # Then the form keeps the entered values and nothing is created
        assert 'value="Lovelace"' in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHARACTERS_CREATE)

    def test_api_field_error_shows_inline(self, client, use_campaign, fake_vclient) -> None:
        """Verify a field-level validation error from the API is shown on the form."""
        # Given an API that rejects the first name
        campaign = use_campaign()
        fake_vclient.set_error(
            Routes.CHARACTERS_CREATE,
            status_code=400,
            detail="Validation failed",
            invalid_parameters=[{"field": "name_first", "message": "Name already taken"}],
        )

        # When submitting the profile
        response = _post_profile(client, campaign.id)

        # Then the API's message is shown
        assert "Name already taken" in response.get_data(as_text=True)

    def test_invalid_character_type_shows_error(self, client, use_campaign) -> None:
        """Verify an unknown character_type value renders an inline error instead of a 500."""
        # Given a player crafting an invalid character_type enum value
        campaign = use_campaign()

        # When submitting the profile form with a bogus character_type
        response = _post_profile(client, campaign.id, character_type="NOT_A_REAL_TYPE")

        # Then the form re-renders with an error
        assert response.status_code == 200
        assert_shows_error(response)

    @pytest.mark.parametrize("character_type", ["NPC", "STORYTELLER"])
    def test_player_cannot_create_privileged_type(
        self, client, use_campaign, fake_vclient, character_type
    ) -> None:
        """Verify a restricted player cannot create an NPC or storyteller character."""
        # Given a PLAYER under the default storyteller-only NPC setting
        campaign = use_campaign()

        # When submitting the profile form with a crafted type
        response = _post_profile(client, campaign.id, character_type=character_type)

        # Then the form re-renders with an error and no character is created
        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.CHARACTERS_CREATE)


class TestManualFinalizeView:
    """Tests for POST /campaign/<id>/characters/profile_edit/create."""

    def _set_temp_character(self, fake_vclient, campaign_id: str, **kwargs) -> None:
        fake_vclient.set_response(
            Routes.CHARACTERS_GET,
            model=CharacterFactory.build(
                id="new-manual-char",
                campaign_id=campaign_id,
                is_temporary=True,
                user_creator_id="test-user-id",
                **kwargs,
            ),
            params={"character_id": "new-manual-char"},
        )

    def _post_finalize(self, client: FlaskClient, campaign_id: str) -> TestResponse:
        return htmx_post(
            client,
            f"/campaign/{campaign_id}/characters/profile_edit/create",
            {**_PROFILE, "trait:trait-1": "3", "trait:trait-2": "0"},
        )

    @pytest.mark.parametrize(
        ("character_type", "player_id"),
        [("PLAYER", "test-user-id"), ("NPC", None), ("STORYTELLER", None)],
    )
    def test_creates_character_and_redirects(
        self, client, use_campaign, fake_vclient, character_type: str, player_id: str | None
    ) -> None:
        """Verify finalizing assigns the chosen traits free and makes the character permanent."""
        # Given a temp character the requester created, which has no player
        # when it is an NPC or storyteller character
        campaign = use_campaign()
        self._set_temp_character(
            fake_vclient, campaign.id, type=character_type, user_player_id=player_id
        )
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN,
            model=BulkAssignTraitResponseFactory.build(failed=[]),
        )
        _seed_temp_character(client, "new-manual-char")

        # When submitting the finalize form
        response = self._post_finalize(client, campaign.id)

        # Then only the positive trait is assigned at no cost and the character is kept
        [assign] = fake_vclient.requests_for(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN, params={"character_id": "new-manual-char"}
        )
        assert [(t["trait_id"], t["value"], t["currency"]) for t in assign.json] == [
            ("trait-1", 3, "NO_COST")
        ]
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            params={"character_id": "new-manual-char"},
            json={"is_temporary": False},
            times=1,
        )

        # And the user goes to the new character with the draft forgotten
        assert "/character/new-manual-char" in response.headers.get("HX-Redirect", "")
        with client.session_transaction() as sess:
            assert "temp_character_id" not in sess

    def test_failed_traits_warn_but_finalize(self, client, use_campaign, fake_vclient) -> None:
        """Verify traits the API could not assign are reported while the character is kept."""
        # Given a bulk assign where one trait fails
        campaign = use_campaign()
        self._set_temp_character(fake_vclient, campaign.id)
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN,
            model=BulkAssignTraitResponseFactory.build(
                failed=[BulkAssignTraitFailureFactory.build(trait_id="trait-1")]
            ),
        )
        _seed_temp_character(client, "new-manual-char")

        # When finalizing
        response = self._post_finalize(client, campaign.id)

        # Then a warning names the failed trait and the character is still finalized
        flashes = session_flashes(client)
        assert any(cat == "warning" and "trait-1" in msg for cat, msg in flashes)
        fake_vclient.assert_called(Routes.CHARACTERS_UPDATE, json={"is_temporary": False})
        assert "/character/new-manual-char" in response.headers.get("HX-Redirect", "")

    def test_redirects_to_profile_when_no_temp_character(self, client, use_campaign) -> None:
        """Verify redirect to profile form when no temp_character_id in session."""
        # Given a campaign but no temp character in session
        campaign = use_campaign()

        # When submitting the finalize form without a temp character
        response = self._post_finalize(client, campaign.id)

        # Then redirect to profile is returned
        assert "profile_edit" in response.headers.get("HX-Redirect", "")

    def test_rerenders_traits_on_api_error(self, client, use_campaign, fake_vclient) -> None:
        """Verify a server error assigning traits re-renders the traits form without internals."""
        # Given a failing bulk assign
        campaign = use_campaign()
        self._set_temp_character(fake_vclient, campaign.id, user_player_id="test-user-id")
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN, status_code=500, detail="db exploded"
        )
        _seed_temp_character(client, "new-manual-char")

        # When submitting the finalize form
        response = self._post_finalize(client, campaign.id)

        # Then the traits form shows an error without the API's internals
        assert_shows_error(response)
        assert "db exploded" not in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHARACTERS_UPDATE)

    def test_load_server_error_returns_to_profile(self, client, use_campaign, fake_vclient) -> None:
        """Verify a server error loading the draft returns to the profile step with an error."""
        # Given loading the in-progress character fails server-side
        campaign = use_campaign()
        fake_vclient.set_error(Routes.CHARACTERS_GET, status_code=500, detail="db exploded")
        _seed_temp_character(client, "new-manual-char")

        # When finalizing
        response = self._post_finalize(client, campaign.id)

        # Then an error is flashed without the detail and the user returns to the profile step
        assert "profile_edit" in response.headers.get("HX-Redirect", "")
        flashes = session_flashes(client)
        assert [cat for cat, _ in flashes] == ["error"]
        assert "db exploded" not in flashes[0][1]
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_BULK_ASSIGN)


class TestManualFinalizeGuards:
    """Tests that finalize only assigns free traits to the requester's in-progress character."""

    def _post_finalize(self, client, campaign_id: str) -> TestResponse:
        return htmx_post(
            client,
            f"/campaign/{campaign_id}/characters/profile_edit/create",
            {"trait:trait-1": "5"},
        )

    @pytest.mark.parametrize(
        ("is_temporary", "owner", "same_campaign"),
        [
            (False, "test-user-id", True),
            (True, "someone-else", True),
            (True, "test-user-id", False),
        ],
        ids=["already-permanent", "other-creator", "other-campaign"],
    )
    def test_refuses_character_that_is_not_the_requesters_temp_character(
        self, client, use_campaign, fake_vclient, is_temporary, owner, same_campaign
    ) -> None:
        """Verify a stale or foreign temp_character_id cannot receive NO_COST traits."""
        # Given a session pointing at a character that is permanent or created by someone else
        campaign = use_campaign()
        character = CharacterFactory.build(
            id="char-1",
            campaign_id=campaign.id if same_campaign else "other-campaign",
            is_temporary=is_temporary,
            user_creator_id=owner,
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_GET, model=character, params={"character_id": "char-1"}
        )
        _seed_temp_character(client, "char-1")

        # When the finalize form is replayed
        response = self._post_finalize(client, campaign.id)

        # Then no traits are assigned and the stale session is cleared
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_BULK_ASSIGN)
        assert "profile_edit" in response.headers.get("HX-Redirect", "")
        with client.session_transaction() as sess:
            assert "temp_character_id" not in sess

    @pytest.mark.parametrize(
        ("age_seconds", "api_status"),
        [(24 * 60 * 60, None), (0, 404)],
        ids=["expired-session", "deleted-character"],
    )
    def test_refuses_stale_temp_session(
        self, client, use_campaign, fake_vclient, age_seconds, api_status
    ) -> None:
        """Verify an expired session or a deleted draft cannot finalize."""
        # Given a temp session past the TTL, or one whose character no longer exists
        campaign = use_campaign()
        if api_status:
            fake_vclient.set_error(Routes.CHARACTERS_GET, status_code=api_status)
        _seed_temp_character(client, "char-1", age_seconds=age_seconds)

        # When finalizing
        response = self._post_finalize(client, campaign.id)

        # Then nothing is assigned and the stale session is cleared
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_BULK_ASSIGN)
        assert "profile_edit" in response.headers.get("HX-Redirect", "")
        with client.session_transaction() as sess:
            assert "temp_character_id" not in sess


class TestProfileEditMode:
    """Tests for GET/POST /campaign/<id>/characters/profile_edit?character_id=<id>."""

    def _set_character(self, fake_vclient, **kwargs) -> None:
        fake_vclient.set_response(
            Routes.CHARACTERS_GET,
            model=CharacterFactory.build(id="char-123", **kwargs),
            params={"character_id": "char-123"},
        )

    def test_edit_mode_prefills_from_character(self, client, use_campaign, fake_vclient) -> None:
        """Verify edit mode pre-fills form from existing character."""
        # Given an existing character
        campaign = use_campaign()
        self._set_character(
            fake_vclient, name_first="Ada", name_last="Lovelace", campaign_id=campaign.id
        )

        # When opening the edit form
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            headers={"HX-Request": "true"},
        )

        # Then the character's names fill the form
        body = response.get_data(as_text=True)
        assert 'value="Ada"' in body
        assert 'value="Lovelace"' in body

    def test_edit_mode_locks_class_and_game_version(
        self, client, use_campaign, fake_vclient
    ) -> None:
        """Verify class and game version cannot be changed in edit mode, since the API keeps them."""
        # Given an existing V5 hunter
        campaign = use_campaign()
        self._set_character(
            fake_vclient, campaign_id=campaign.id, character_class="HUNTER", game_version="V5"
        )

        # When the edit form renders
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            headers={"HX-Request": "true"},
        )

        # Then neither field can be chosen and both are submitted unchanged
        body = response.get_data(as_text=True)
        assert '<select name="character_class"' not in body
        assert '<select name="game_version"' not in body
        assert re.search(r'name="character_class"\s+value="HUNTER"', body)
        assert re.search(r'name="game_version"\s+value="V5"', body)

    def test_edit_post_updates_and_redirects(self, client, use_campaign, fake_vclient) -> None:
        """Verify a valid edit updates the character and redirects to it."""
        # Given the user's own character
        campaign = use_campaign()
        self._set_character(
            fake_vclient,
            campaign_id=campaign.id,
            game_version="V5",
            character_class="MORTAL",
            user_player_id="test-user-id",
        )

        # When submitting the edit
        response = _post_profile(
            client, campaign.id, "?character_id=char-123", name_first="Updated", name_last="Name"
        )

        # Then the new values are sent and the user returns to the character
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            params={"character_id": "char-123"},
            json_subset={"name_first": "Updated", "name_last": "Name"},
            times=1,
        )
        assert "/character/char-123" in response.headers.get("HX-Redirect", "")

    def test_edit_post_validation_error_rerenders(self, client, use_campaign, fake_vclient) -> None:
        """Verify an invalid edit re-renders the form without updating."""
        # Given the user's own character
        campaign = use_campaign()
        self._set_character(fake_vclient, campaign_id=campaign.id, user_player_id="test-user-id")

        # When submitting a too-short first name
        response = _post_profile(client, campaign.id, "?character_id=char-123", name_first="Ab")

        # Then the form keeps the input and nothing is updated
        assert 'value="Ab"' in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHARACTERS_UPDATE)

    @pytest.mark.parametrize(
        "failing_route",
        [Routes.CHARACTERS_UPDATE, Routes.CHARACTERS_GET],
        ids=["update-fails", "load-fails"],
    )
    def test_edit_server_error_shows_error_without_detail(
        self, client, use_campaign, fake_vclient, failing_route
    ) -> None:
        """Verify a server error loading or saving the character shows an error, not the detail."""
        # Given the user's own character and a failing API call
        campaign = use_campaign()
        self._set_character(fake_vclient, campaign_id=campaign.id, user_player_id="test-user-id")
        fake_vclient.set_error(
            failing_route,
            status_code=500,
            detail="db exploded",
            params={"character_id": "char-123"},
        )

        # When submitting the edit form
        response = _post_profile(client, campaign.id, "?character_id=char-123")

        # Then an error is shown without the detail
        assert_shows_error(response)
        assert "db exploded" not in response.get_data(as_text=True)

    def test_edit_denied_for_non_editor(self, client, use_campaign, fake_vclient) -> None:
        """Verify a player cannot edit a character they do not own."""
        # Given a player and an existing player character owned by someone else
        other_char = CharacterFactory.build(id="char-other", user_player_id="someone-else")
        campaign = use_campaign(characters=[other_char])
        fake_vclient.set_response(
            Routes.CHARACTERS_GET, model=other_char, params={"character_id": "char-other"}
        )

        # When submitting an edit for that character
        response = _post_profile(
            client, campaign.id, "?character_id=char-other", character_type="PLAYER"
        )

        # Then the update is never attempted and the user is redirected away
        fake_vclient.assert_not_called(Routes.CHARACTERS_UPDATE)
        assert response.headers.get("HX-Redirect") is not None

    def test_edit_rejects_npc_type_for_restricted_player(
        self, client, use_campaign, fake_vclient
    ) -> None:
        """Verify a player who owns a character cannot switch its type to NPC when restricted."""
        # Given a restricted player editing their OWN player character (passes the edit guard)
        own_char = CharacterFactory.build(
            id="char-own", user_player_id="test-user-id", type="PLAYER"
        )
        campaign = use_campaign(characters=[own_char])
        fake_vclient.set_response(
            Routes.CHARACTERS_GET, model=own_char, params={"character_id": "char-own"}
        )

        # When submitting an edit that switches the type to NPC
        response = _post_profile(
            client, campaign.id, "?character_id=char-own", character_type="NPC"
        )

        # Then the form re-renders with an error and no update occurs
        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.CHARACTERS_UPDATE)


def _x_data_containing(html: str, needle: str) -> str:
    """Return the decoded x-data attribute value that mentions ``needle``, as a browser sees it."""
    found: list[str] = []

    class _Collector(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            found.extend(v for k, v in attrs if k == "x-data" and v and needle in v)

    _Collector().feed(html)
    assert found, f"no x-data attribute containing {needle!r}"
    return found[0]
