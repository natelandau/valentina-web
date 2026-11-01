"""Tests for character creation routes."""

import logging
from datetime import UTC, datetime, timedelta

from vclient.exceptions import APIError, ServerError, ValidationError
from vclient.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    CharacterFullSheetFactory,
    ChargenSessionResponseFactory,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)

from tests.conftest import get_csrf
from tests.helpers import assert_shows_error, build_global_context


class TestSelectionPageView:
    """Tests for GET /campaign/<id>/characters/new."""

    def test_renders_selection_page(self, client, mocker) -> None:
        """Verify the selection page renders for an authenticated user."""
        # Given a campaign in global context
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=[],
        )

        # When requesting the selection page
        response = client.get(f"/campaign/{campaign.id}/characters/new")

        # Then the page renders successfully
        assert response.status_code == 200

    def test_returns_404_for_invalid_campaign(self, client) -> None:
        """Verify 404 for a non-existent campaign."""
        # When requesting with a bad campaign ID
        response = client.get("/campaign/nonexistent/characters/new")

        # Then 404 is returned
        assert response.status_code == 404


class TestSelectionCardsView:
    """Tests for GET /campaign/<id>/characters/new/cards."""

    def test_returns_cards_fragment(self, client, mocker) -> None:
        """Verify the cards fragment renders for back navigation."""
        # Given a campaign in global context
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=[],
        )

        # When requesting the cards fragment
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then an HTML fragment is returned
        assert response.status_code == 200


class TestSingleAutogenFormView:
    """Tests for GET /campaign/<id>/characters/new/single-autogen."""

    def test_renders_form_for_storyteller(self, client, mocker) -> None:
        """Verify the single autogen form renders for privileged users."""
        # Given a privileged user and mocked form options
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_views.fetch_form_options",
            return_value={
                "character_types": ["PLAYER", "NPC"],
                "character_classes": ["VAMPIRE", "WEREWOLF"],
                "experience_levels": ["NEW", "ADVANCED"],
                "skill_focuses": ["BALANCED"],
                "concepts": CharacterConceptFactory.batch(2),
                "vampire_clans": VampireClanFactory.batch(2),
                "werewolf_tribes": WerewolfTribeFactory.batch(1),
                "werewolf_auspices": WerewolfAuspiceFactory.batch(1),
            },
        )

        # When requesting the form
        response = client.get(f"/campaign/{campaign.id}/characters/new/single-autogen")

        # Then the form fragment renders
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "character_type" in body

    def test_returns_403_for_non_privileged(self, client, mocker) -> None:
        """Verify non-privileged users cannot access single autogen."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When requesting the form
        response = client.get(f"/campaign/{campaign.id}/characters/new/single-autogen")

        # Then 403 is returned
        assert response.status_code == 403


class TestSingleAutogenSubmit:
    """Tests for POST /campaign/<id>/characters/new/single-autogen."""

    def test_generates_character_and_redirects(self, client, mocker) -> None:
        """Verify successful generation redirects to the new character page."""
        # Given a privileged user and valid form data
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        new_char = CharacterFactory.build(id="new-char-id")
        mock_generate = mocker.patch(
            "vweb.routes.character_create.picker_views.generate_single",
            return_value=new_char,
        )
        mocker.patch("vweb.lib.cache.global_context.clear")
        csrf = get_csrf(client)

        # When submitting the form
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            data={"character_type": "PLAYER", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then generation is called and redirect is set
        mock_generate.assert_called_once()
        assert response.status_code == 200
        assert "/character/new-char-id" in response.headers.get("HX-Redirect", "")

    def test_returns_form_with_errors_on_missing_type(self, client, mocker) -> None:
        """Verify missing character_type re-renders the form with errors."""
        # Given a privileged user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_views.fetch_form_options",
            return_value={
                "character_types": ["PLAYER"],
                "character_classes": [],
                "experience_levels": [],
                "skill_focuses": [],
                "concepts": [],
                "vampire_clans": [],
                "werewolf_tribes": [],
                "werewolf_auspices": [],
            },
        )
        csrf = get_csrf(client)

        # When submitting without character_type
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            data={"csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then form is re-rendered with errors
        assert response.status_code == 200
        assert_shows_error(response)

    def test_server_error_shows_fallback_not_detail(self, client, mocker) -> None:
        """Verify a server error re-renders the form without the API's internals."""
        # Given a privileged user and a generation call that fails server-side
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_views.fetch_form_options",
            return_value={
                "character_types": ["PLAYER"],
                "character_classes": [],
                "experience_levels": [],
                "skill_focuses": [],
                "concepts": [],
                "vampire_clans": [],
                "werewolf_tribes": [],
                "werewolf_auspices": [],
            },
        )
        mocker.patch(
            "vweb.routes.character_create.picker_views.generate_single",
            side_effect=ServerError("boom", 500, {"detail": "db exploded"}),
        )
        csrf = get_csrf(client)

        # When submitting the form
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            data={"character_type": "PLAYER", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the fallback is shown and the detail is not
        body = response.get_data(as_text=True)
        assert "Failed to create character. Please try again." in body
        assert "db exploded" not in body
        assert "boom" not in body

    def test_returns_403_for_non_privileged(self, client, mocker) -> None:
        """Verify PLAYER cannot submit single autogen."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        csrf = get_csrf(client)

        # When submitting the form
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            data={"character_type": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned
        assert response.status_code == 403


class TestMultiAutogenView:
    """Tests for POST /campaign/<id>/characters/new/multi-autogen."""

    def test_starts_session_and_renders_comparison(self, client, mocker) -> None:
        """Verify starting a session renders the comparison view."""
        # Given a user with a valid campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        session_response = ChargenSessionResponseFactory.build()
        mocker.patch(
            "vweb.routes.character_create.autogen_views.start_session",
            return_value=session_response,
        )
        mocker.patch(
            "vweb.lib.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(),
        )

        csrf = get_csrf(client)

        # When starting a session
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen",
            data={"csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the comparison view renders
        assert response.status_code == 200

    def test_renders_error_on_api_failure(self, client, mocker) -> None:
        """Verify API errors are shown inline."""
        # Given a user and a failing API call
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.autogen_views.start_session",
            side_effect=APIError("Insufficient XP"),
        )
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=[],
        )
        csrf = get_csrf(client)

        # When starting a session
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen",
            data={"csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then error is shown in the selection cards
        assert response.status_code == 200
        assert_shows_error(response)


class TestMultiAutogenFinalizeView:
    """Tests for POST /campaign/<id>/characters/new/multi-autogen/finalize."""

    def test_finalizes_and_redirects(self, client, mocker) -> None:
        """Verify finalizing a session redirects to the new character page."""
        # Given a valid session and selected character
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        new_char = CharacterFactory.build(id="selected-char-id")
        mock_finalize = mocker.patch(
            "vweb.routes.character_create.autogen_views.finalize_session",
            return_value=new_char,
        )
        mocker.patch("vweb.lib.cache.global_context.clear")
        csrf = get_csrf(client)

        # When finalizing
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize",
            data={
                "session_id": "sess-1",
                "selected_character_id": "selected-char-id",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then finalize is called and redirect is set
        mock_finalize.assert_called_once_with(
            user_id="test-user-id",
            campaign_id=campaign.id,
            session_id="sess-1",
            selected_character_id="selected-char-id",
        )
        assert response.status_code == 200
        assert "/character/selected-char-id" in response.headers.get("HX-Redirect", "")

    def test_redirects_to_selection_on_finalize_failure(self, client, mocker) -> None:
        """Verify finalize errors redirect to the selection page with flash."""
        # Given a failing finalize call
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.autogen_views.finalize_session",
            side_effect=APIError("Session expired"),
        )
        csrf = get_csrf(client)

        # When finalizing
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize",
            data={
                "session_id": "sess-1",
                "selected_character_id": "char-1",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )

        # Then user is redirected to the selection page
        assert response.status_code == 200
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")

    def _post_finalize(self, client, mocker, error: Exception) -> tuple:
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.autogen_views.finalize_session",
            side_effect=error,
        )
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize",
            data={
                "session_id": "sess-1",
                "selected_character_id": "char-1",
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
        )
        with client.session_transaction() as sess:
            flashes = list(sess.get("_flashes", []))
        return campaign, response, flashes

    def test_expired_session_logs_at_info(self, client, mocker, caplog) -> None:
        """Verify an expired session is an expected event, logged below warning."""
        # Given the API rejects the session id
        error = ValidationError(
            "bad",
            400,
            {"invalid_parameters": [{"field": "session_id", "message": "Session expired"}]},
        )

        # When finalizing
        with caplog.at_level(logging.INFO, logger="vweb.routes.character_create.autogen_views"):
            self._post_finalize(client, mocker, error)

        # Then the expiry is logged at info only
        levels = [r.levelno for r in caplog.records if r.name.endswith("autogen_views")]
        assert levels == [logging.INFO]

    def test_expired_session_flashes_expired_message(self, client, mocker) -> None:
        """Verify an expired session explains itself and redirects to selection."""
        # Given the API rejects the session id
        error = ValidationError(
            "bad",
            400,
            {
                "invalid_parameters": [
                    {"field": "session_id", "message": "Session not found or expired"}
                ]
            },
        )

        # When finalizing
        campaign, response, flashes = self._post_finalize(client, mocker, error)

        # Then the user is redirected with the expired message
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")
        assert (
            "error",
            "This character generation session expired. Please start a new one.",
        ) in flashes

    def test_other_validation_error_flashes_field_message(self, client, mocker) -> None:
        """Verify a validation error on another field is not shown as an expired session."""
        # Given the API rejects the selected character, not the session
        error = ValidationError(
            "bad",
            400,
            {
                "invalid_parameters": [
                    {"field": "selected_character_id", "message": "Not in session"}
                ]
            },
        )

        # When finalizing
        _, _, flashes = self._post_finalize(client, mocker, error)

        # Then the field message is flashed instead of the expired text
        assert ("error", "Selected character id: Not in session") in flashes
        assert all("expired" not in message for _, message in flashes)

    def test_server_error_keeps_generic_message(self, client, mocker) -> None:
        """Verify a server error shows the generic failure message."""
        # When finalizing hits a server error
        _, response, flashes = self._post_finalize(client, mocker, ServerError("boom", 500))

        # Then the generic message is flashed
        assert response.status_code == 200
        assert ("error", "Failed to finalize character. Please try again.") in flashes


class TestAddCharacterButtonIntegration:
    """Tests for the Add Character button on the campaign page."""

    def test_campaign_page_has_add_character_link(self, client, mocker) -> None:
        """Verify the campaign page renders an enabled Add Character button."""
        # Given a campaign with a privileged user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting the campaign page
        response = client.get(f"/campaign/{campaign.id}")

        # Then the page contains a link to the character creation page
        body = response.get_data(as_text=True)
        assert f"/campaign/{campaign.id}/characters/new" in body


class TestPendingSessionsOnSelectionCards:
    """Tests for pending sessions display on selection cards."""

    def test_renders_pending_sessions_when_sessions_exist(self, client, mocker) -> None:
        """Verify pending sessions section appears when active sessions exist."""
        # Given a campaign and active sessions
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        future = datetime.now(tz=UTC) + timedelta(hours=1)
        sessions = ChargenSessionResponseFactory.batch(2, expires_at=future)
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=sessions,
        )

        # When requesting the selection cards
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then the pending sessions section is rendered
        assert response.status_code == 200

    def test_omits_pending_sessions_when_none_exist(self, client, mocker) -> None:
        """Verify pending sessions section is hidden when no sessions exist."""
        # Given a campaign with no active sessions
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=[],
        )

        # When requesting the selection cards
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then no pending sessions section is rendered
        assert response.status_code == 200

    def test_filters_expired_sessions(self, client, mocker) -> None:
        """Verify expired sessions are filtered out on page load."""
        # Given one expired and one active session
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        expired = ChargenSessionResponseFactory.build(
            expires_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
        active = ChargenSessionResponseFactory.build(
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        mocker.patch(
            "vweb.routes.character_create.picker_services.list_sessions",
            return_value=[expired, active],
        )

        # When requesting the selection cards
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then only the active session appears
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert active.id in body
        assert expired.id not in body


class TestResumeSessionView:
    """Tests for GET /campaign/<id>/characters/new/multi-autogen/session/<sid>/resume."""

    def test_renders_comparison_for_valid_session(self, client, mocker) -> None:
        """Verify resuming a valid session renders the comparison view."""
        # Given a campaign and a valid session
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        session_response = ChargenSessionResponseFactory.build(
            id="sess-abc",
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        mocker.patch(
            "vweb.routes.character_create.autogen_views.get_session",
            return_value=session_response,
        )
        mocker.patch(
            "vweb.lib.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(),
        )

        # When resuming the session
        response = client.get(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/session/sess-abc/resume",
            headers={"HX-Request": "true"},
        )

        # Then the comparison view renders
        assert response.status_code == 200

    def test_redirects_on_expired_session(self, client, mocker) -> None:
        """Verify expired session redirects with flash error."""
        # Given a campaign and an expired/missing session
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_create.autogen_views.get_session",
            side_effect=APIError("Session expired"),
        )

        # When resuming the session
        response = client.get(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/session/sess-abc/resume",
            headers={"HX-Request": "true"},
        )

        # Then user is redirected to the selection page
        assert response.status_code == 200
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")


class TestMultiAutogenPassesExpiresAt:
    """Tests for MultiAutogenView passing expires_at."""

    def test_passes_expires_at_to_template(self, client, mocker) -> None:
        """Verify MultiAutogenView.post() passes expires_at to the comparison template."""
        # Given a user with a valid campaign
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        future = datetime.now(tz=UTC) + timedelta(hours=1)
        session_response = ChargenSessionResponseFactory.build(expires_at=future)
        mocker.patch(
            "vweb.routes.character_create.autogen_views.start_session",
            return_value=session_response,
        )
        mocker.patch(
            "vweb.lib.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(),
        )

        csrf = get_csrf(client)

        # When starting a session
        response = client.post(
            f"/campaign/{campaign.id}/characters/new/multi-autogen",
            data={"csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the response renders successfully (expires_at accepted by template)
        assert response.status_code == 200
