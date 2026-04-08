"""Tests for manual character creation routes."""

from __future__ import annotations

from vclient.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)

from tests.conftest import get_csrf
from tests.helpers import assert_shows_error, build_global_context, setup_form_options


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


class TestManualProfileView:
    """Tests for GET /campaign/<id>/characters/profile_edit."""

    def test_renders_profile_form(self, client, mocker) -> None:
        """Verify the profile form renders for an authenticated player."""
        # Given a campaign in global context
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then the page renders successfully with form fields
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "name_first" in body
        assert "character_class" in body

    def test_returns_404_for_invalid_campaign(self, client) -> None:
        """Verify 404 for a non-existent campaign."""
        # When requesting with a bad campaign ID
        response = client.get("/campaign/nonexistent/characters/profile_edit")

        # Then 404 is returned
        assert response.status_code == 404

    def test_character_type_hidden_for_player(self, client, mocker) -> None:
        """Verify character_type dropdown is not shown to regular players."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then character_type select is not present
        body = response.get_data(as_text=True)
        assert 'name="character_type"' not in body

    def test_character_type_shown_for_storyteller(self, client, mocker) -> None:
        """Verify character_type dropdown appears for storytellers."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        # When requesting the profile form
        response = client.get(f"/campaign/{campaign.id}/characters/profile_edit")

        # Then character_type select is present
        body = response.get_data(as_text=True)
        assert 'name="character_type"' in body

    def test_prefills_from_query_params(self, client, mocker) -> None:
        """Verify form is prefilled from query parameters (back button support)."""
        # Given a campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        # When requesting with query params
        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?name_first=Ada&name_last=Lovelace"
        )

        # Then the form is prefilled
        body = response.get_data(as_text=True)
        assert 'value="Ada"' in body
        assert 'value="Lovelace"' in body


class TestManualTraitsView:
    """Tests for POST /campaign/<id>/characters/profile_edit/traits."""

    def test_traits_stub_returns_placeholder(self, client, mocker) -> None:
        """Verify the traits POST stub returns a placeholder response."""
        # Given a campaign in global context
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        csrf = get_csrf(client)

        # When posting to the traits stub URL
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit/traits",
            data={"csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the stub response is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "coming soon" in body

    def test_profile_post_rerenders_on_missing_name(self, client, mocker) -> None:
        """Verify missing name_first on profile POST re-renders form with error."""
        # Given a campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)
        csrf = get_csrf(client)

        # When posting to profile URL without name_first
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit",
            data={
                "name_last": "Lovelace",
                "game_version": "V5",
                "character_class": "MORTAL",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then profile form is re-rendered with field-level error
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "text-error" in body

    def test_profile_post_validates_vampire_requires_clan(self, client, mocker) -> None:
        """Verify vampire class requires vampire_clan_id on profile POST."""
        # Given a campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)
        csrf = get_csrf(client)

        # When posting vampire without clan to the profile URL
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit",
            data={
                "name_first": "Drac",
                "name_last": "Ula",
                "game_version": "V5",
                "character_class": "VAMPIRE",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then profile form is re-rendered with field-level error
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "text-error" in body

    def test_profile_post_validates_hunter_requires_creed(self, client, mocker) -> None:
        """Verify hunter class requires creed on profile POST."""
        # Given a campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)
        csrf = get_csrf(client)

        # When posting hunter without creed to the profile URL
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit",
            data={
                "name_first": "Van",
                "name_last": "Helsing",
                "game_version": "V5",
                "character_class": "HUNTER",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then profile form is re-rendered with field-level error
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "text-error" in body


class TestManualFinalizeView:
    """Tests for POST /campaign/<id>/characters/profile_edit/create."""

    def test_creates_character_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful creation redirects to the character sheet."""
        from vclient.testing import BulkAssignTraitResponseFactory, Routes

        # Given a campaign and a temp character in session
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        temp_char = CharacterFactory.build(id="new-manual-char", campaign_id=campaign.id)
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN,
            model=BulkAssignTraitResponseFactory.build(),
            params={"character_id": "new-manual-char"},
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_UPDATE,
            model=temp_char,
            params={"character_id": "new-manual-char"},
        )

        with client.session_transaction() as sess:
            sess["temp_character_id"] = "new-manual-char"

        csrf = get_csrf(client)

        # When submitting the finalize form
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit/create",
            data={
                "name_first": "Ada",
                "name_last": "Lovelace",
                "game_version": "V5",
                "character_class": "MORTAL",
                "trait:trait-1": "3",
                "trait:trait-2": "0",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then character is finalized and redirect is set
        assert response.status_code == 200
        assert "/character/new-manual-char" in response.headers.get("HX-Redirect", "")

    def test_redirects_to_profile_when_no_temp_character(self, client, mocker) -> None:
        """Verify redirect to profile form when no temp_character_id in session."""
        # Given a campaign but no temp character in session
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        csrf = get_csrf(client)

        # When submitting the finalize form without a temp character
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit/create",
            data={
                "name_first": "Ada",
                "name_last": "Lovelace",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then redirect to profile is returned
        assert response.status_code == 200
        assert "profile_edit" in response.headers.get("HX-Redirect", "")

    def test_rerenders_traits_on_api_error(self, client, mocker, fake_vclient) -> None:
        """Verify API error re-renders traits form with error flash."""
        from vclient.testing import CharacterFullSheetFactory, Routes

        # Given a campaign and a failing API
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        temp_char = CharacterFactory.build(id="new-manual-char", campaign_id=campaign.id)
        full_sheet = CharacterFullSheetFactory.build(id="new-manual-char")
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_BULK_ASSIGN,
            status_code=500,
            params={"character_id": "new-manual-char"},
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_GET,
            model=temp_char,
            params={"character_id": "new-manual-char"},
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_FULL_SHEET,
            model=full_sheet,
            params={"character_id": "new-manual-char"},
        )

        with client.session_transaction() as sess:
            sess["temp_character_id"] = "new-manual-char"

        csrf = get_csrf(client)

        # When submitting the finalize form
        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit/create",
            data={
                "name_first": "Ada",
                "name_last": "Lovelace",
                "game_version": "V5",
                "character_class": "MORTAL",
                "trait:trait-1": "3",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then traits form is re-rendered with error
        assert response.status_code == 200
        assert_shows_error(response)


class TestProfileEditMode:
    """Tests for GET/POST /campaign/<id>/characters/profile_edit?character_id=<id>."""

    def test_edit_mode_prefills_from_character(self, client, mocker, fake_vclient) -> None:
        """Verify edit mode pre-fills form from existing character."""
        from vclient.testing import Routes

        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        character = CharacterFactory.build(
            id="char-123",
            name_first="Ada",
            name_last="Lovelace",
            campaign_id=campaign.id,
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_GET, model=character, params={"character_id": "char-123"}
        )

        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="Ada"' in body
        assert 'value="Lovelace"' in body

    def test_edit_mode_game_version_disabled(self, client, mocker, fake_vclient) -> None:
        """Verify game version is disabled in edit mode."""
        from vclient.testing import Routes

        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        character = CharacterFactory.build(
            id="char-123", campaign_id=campaign.id, game_version="V5"
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_GET, model=character, params={"character_id": "char-123"}
        )

        response = client.get(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            headers={"HX-Request": "true"},
        )

        body = response.get_data(as_text=True)
        assert '<select class="select w-full" disabled>' in body
        assert '<input type="hidden" name="game_version" value="V5"' in body

    def test_edit_post_updates_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful edit POST updates character and redirects."""
        from vclient.testing import Routes

        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        character = CharacterFactory.build(
            id="char-123",
            campaign_id=campaign.id,
            game_version="V5",
            character_class="MORTAL",
        )
        fake_vclient.set_response(
            Routes.CHARACTERS_UPDATE, model=character, params={"character_id": "char-123"}
        )

        csrf = get_csrf(client)

        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            data={
                "name_first": "Updated",
                "name_last": "Name",
                "game_version": "V5",
                "character_class": "MORTAL",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assert "/character/char-123" in response.headers.get("HX-Redirect", "")

    def test_edit_post_validation_error_rerenders(self, client, mocker) -> None:
        """Verify validation error in edit mode re-renders form with errors."""
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        csrf = get_csrf(client)

        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            data={
                "name_first": "Ab",
                "name_last": "Lovelace",
                "game_version": "V5",
                "character_class": "MORTAL",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "text-error" in body

    def test_edit_post_api_error_shows_general_error(self, client, mocker, fake_vclient) -> None:
        """Verify API error in edit mode shows general error message."""
        from vclient.testing import Routes

        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        _mock_form_options(mocker)

        fake_vclient.set_error(
            Routes.CHARACTERS_UPDATE, status_code=500, params={"character_id": "char-123"}
        )

        csrf = get_csrf(client)

        response = client.post(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id=char-123",
            data={
                "name_first": "Updated",
                "name_last": "Name",
                "game_version": "V5",
                "character_class": "MORTAL",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "alert-error" in body
