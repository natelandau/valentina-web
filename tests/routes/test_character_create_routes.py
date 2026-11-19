"""Tests for character creation routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import get_csrf, htmx_post
from tests.helpers import assert_shows_error, session_flashes
from vweb.api_client.testing import (
    CharacterFactory,
    ChargenSessionResponseFactory,
    Routes,
)


class TestSelectionPageView:
    """Tests for GET /campaign/<id>/characters/new."""

    def test_renders_selection_page(self, client, use_context, fake_vclient) -> None:
        """Verify the selection page renders for an authenticated user."""
        # Given a campaign in global context
        campaign = use_context(user_role="STORYTELLER").campaigns[0]

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


class TestSingleAutogenFormView:
    """Tests for GET and POST /campaign/<id>/characters/new/single-autogen."""

    def test_renders_form_for_storyteller(self, client, use_context, fake_vclient) -> None:
        """Verify the single autogen form renders for privileged users."""
        # Given a privileged user
        campaign = use_context(user_role="STORYTELLER").campaigns[0]

        # When requesting the form
        response = client.get(f"/campaign/{campaign.id}/characters/new/single-autogen")

        # Then the form fragment renders with the character type field
        assert response.status_code == 200
        assert 'name="character_type"' in response.get_data(as_text=True)

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_returns_403_for_non_privileged(
        self, client, use_context, fake_vclient, method
    ) -> None:
        """Verify a PLAYER can neither open nor submit single autogen."""
        # Given a PLAYER user
        campaign = use_context(user_role="PLAYER").campaigns[0]
        csrf = get_csrf(client)

        # When requesting the form
        response = getattr(client, method)(
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            data={"character_type": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned and nothing is generated
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CHARACTERS_AUTOGENERATE)

    def test_generates_character_and_redirects(self, client, use_context, fake_vclient) -> None:
        """Verify submitting sends the chosen options to the API and redirects to the character."""
        # Given a privileged user and an API that generates a character
        campaign = use_context(user_role="STORYTELLER").campaigns[0]
        fake_vclient.set_response(
            Routes.CHARACTERS_AUTOGENERATE, model=CharacterFactory.build(id="new-char-id")
        )

        # When submitting the form with a class and a blank experience level
        response = htmx_post(
            client,
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            {"character_type": "NPC", "character_class": "VAMPIRE", "experience_level": ""},
        )

        # Then only the filled-in options are sent and the user goes to the new character
        fake_vclient.assert_called(
            Routes.CHARACTERS_AUTOGENERATE,
            query={"campaign_id": campaign.id},
            json={"character_type": "NPC", "character_class": "VAMPIRE"},
            times=1,
        )
        assert "/character/new-char-id" in response.headers.get("HX-Redirect", "")

    def test_returns_form_with_errors_on_missing_type(
        self, client, use_context, fake_vclient
    ) -> None:
        """Verify a missing character_type re-renders the form without calling the API."""
        # Given a privileged user
        campaign = use_context(user_role="STORYTELLER").campaigns[0]

        # When submitting without character_type
        response = htmx_post(client, f"/campaign/{campaign.id}/characters/new/single-autogen")

        # Then the form shows an error and nothing is generated
        assert response.status_code == 200
        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.CHARACTERS_AUTOGENERATE)

    @pytest.mark.parametrize(
        ("status_code", "detail_shown"),
        [(400, True), (500, False)],
        ids=["user-error-shows-detail", "server-error-hides-detail"],
    )
    def test_api_error_rerenders_form(
        self, client, use_context, fake_vclient, status_code, detail_shown
    ) -> None:
        """Verify a failed generation shows an error, exposing the API's reason only for user errors."""
        # Given a privileged user and a generation call that fails
        campaign = use_context(user_role="STORYTELLER").campaigns[0]
        fake_vclient.set_error(
            Routes.CHARACTERS_AUTOGENERATE, status_code=status_code, detail="api reason text"
        )

        # When submitting the form
        response = htmx_post(
            client,
            f"/campaign/{campaign.id}/characters/new/single-autogen",
            {"character_type": "PLAYER"},
        )

        # Then the form shows an error, with the API's detail only for a user error
        assert_shows_error(response)
        assert ("api reason text" in response.get_data(as_text=True)) is detail_shown
        assert "HX-Redirect" not in response.headers


class TestMultiAutogenView:
    """Tests for POST /campaign/<id>/characters/new/multi-autogen."""

    def test_starts_session_and_renders_comparison(self, client, use_context, fake_vclient) -> None:
        """Verify starting a session shows the generated characters to choose from."""
        # Given an API that starts a session with two characters
        campaign = use_context(user_role="PLAYER").campaigns[0]
        characters = [
            CharacterFactory.build(id="gen-1", name_full="Generated One"),
            CharacterFactory.build(id="gen-2", name_full="Generated Two"),
        ]
        fake_vclient.set_response(
            Routes.CHARACTERS_CHARGEN_START,
            model=ChargenSessionResponseFactory.build(id="sess-new", characters=characters),
        )

        # When starting a session
        response = htmx_post(client, f"/campaign/{campaign.id}/characters/new/multi-autogen")

        # Then the session starts for this campaign and both characters can be selected
        fake_vclient.assert_called(
            Routes.CHARACTERS_CHARGEN_START, query={"campaign_id": campaign.id}, times=1
        )
        body = response.get_data(as_text=True)
        assert 'value="sess-new"' in body
        assert "Generated One" in body
        assert "Generated Two" in body

    def test_renders_error_on_api_failure(self, client, use_context, fake_vclient) -> None:
        """Verify an API error is shown inline on the selection cards."""
        # Given an API that refuses to start a session
        campaign = use_context(user_role="PLAYER").campaigns[0]
        fake_vclient.set_error(Routes.CHARACTERS_CHARGEN_START, status_code=400)

        # When starting a session
        response = htmx_post(client, f"/campaign/{campaign.id}/characters/new/multi-autogen")

        # Then the error is shown in the selection cards
        assert response.status_code == 200
        assert_shows_error(response)


class TestMultiAutogenFinalizeView:
    """Tests for POST /campaign/<id>/characters/new/multi-autogen/finalize."""

    def test_finalizes_and_redirects(self, client, use_context, fake_vclient) -> None:
        """Verify finalizing sends the selection to the API and redirects to the new character."""
        # Given an API that finalizes the session
        campaign = use_context(user_role="PLAYER").campaigns[0]
        fake_vclient.set_response(
            Routes.CHARACTERS_CHARGEN_FINALIZE,
            model=CharacterFactory.build(id="selected-char-id"),
        )

        # When finalizing
        response = htmx_post(
            client,
            f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize",
            {"session_id": "sess-1", "selected_character_id": "selected-char-id"},
        )

        # Then the selection reaches the API and the user goes to the new character
        fake_vclient.assert_called(
            Routes.CHARACTERS_CHARGEN_FINALIZE,
            json={"session_id": "sess-1", "selected_character_id": "selected-char-id"},
            times=1,
        )
        assert "/character/selected-char-id" in response.headers.get("HX-Redirect", "")

    @pytest.mark.parametrize(
        "form",
        [
            {"selected_character_id": "char-1"},
            {"session_id": "sess-1"},
        ],
        ids=["no-session", "no-selection"],
    )
    def test_incomplete_form_returns_to_selection(
        self, client, use_context, fake_vclient, form
    ) -> None:
        """Verify a form missing the session or the selection is not sent to the API."""
        # Given a form missing one of the ids
        campaign = use_context(user_role="PLAYER").campaigns[0]

        # When finalizing
        response = htmx_post(
            client, f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize", form
        )

        # Then the user returns to selection with an error and nothing is finalized
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")
        assert [c for c, _ in session_flashes(client)] == ["error"]
        fake_vclient.assert_not_called(Routes.CHARACTERS_CHARGEN_FINALIZE)

    @pytest.mark.parametrize(
        ("error_kwargs", "expected"),
        [
            (
                {
                    "status_code": 400,
                    "invalid_parameters": [{"field": "session_id", "message": "Session expired"}],
                },
                (logging.INFO, None),
            ),
            ({"status_code": 404}, (logging.INFO, None)),
            (
                {
                    "status_code": 400,
                    "invalid_parameters": [
                        {"field": "selected_character_id", "message": "Not in session"}
                    ],
                },
                (None, "Not in session"),
            ),
            ({"status_code": 500}, (logging.ERROR, None)),
        ],
        ids=["expired-session", "archived-character", "other-field-error", "server-error"],
    )
    def test_failure_returns_to_selection(
        self, client, use_context, fake_vclient, caplog, error_kwargs, expected
    ) -> None:
        """Verify a failed finalize returns to selection with one error, logged by severity."""
        log_level, api_message = expected
        # Given an API that rejects the finalize
        campaign = use_context(user_role="PLAYER").campaigns[0]
        fake_vclient.set_error(Routes.CHARACTERS_CHARGEN_FINALIZE, **error_kwargs)

        # When finalizing
        with caplog.at_level(logging.INFO, logger="vweb.routes.character_create.autogen_views"):
            response = htmx_post(
                client,
                f"/campaign/{campaign.id}/characters/new/multi-autogen/finalize",
                {"session_id": "sess-1", "selected_character_id": "char-1"},
            )

        # Then the user returns to selection with a single error flash
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")
        flashes = session_flashes(client)
        assert [category for category, _ in flashes] == ["error"]
        if api_message is not None:
            assert api_message in flashes[0][1]

        # And expected failures stay below warning while server errors are logged as errors
        levels = [r.levelno for r in caplog.records if r.name.endswith("autogen_views")]
        assert levels == ([log_level] if log_level is not None else [])


class TestAddCharacterButtonIntegration:
    """Tests for the Add Character button on the campaign page."""

    def test_campaign_page_has_add_character_link(self, client, use_context) -> None:
        """Verify the campaign page links to the character creation page."""
        # Given a campaign with a privileged user
        campaign = use_context(user_role="STORYTELLER").campaigns[0]

        # When visiting the campaign page
        response = client.get(f"/campaign/{campaign.id}")

        # Then the page contains a link to the character creation page
        assert f"/campaign/{campaign.id}/characters/new" in response.get_data(as_text=True)


class TestPendingSessionsOnSelectionCards:
    """Tests for pending sessions display on selection cards."""

    def test_lists_only_unexpired_sessions(self, client, use_context, fake_vclient) -> None:
        """Verify expired sessions are not offered for resuming."""
        # Given one expired and one active session in the campaign
        campaign = use_context(user_role="STORYTELLER").campaigns[0]
        expired = ChargenSessionResponseFactory.build(
            campaign_id=campaign.id,
            expires_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
        active = ChargenSessionResponseFactory.build(
            campaign_id=campaign.id,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        fake_vclient.set_response(Routes.CHARACTERS_CHARGEN_SESSIONS_LIST, items=[expired, active])

        # When requesting the selection cards
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then only the active session appears
        body = response.get_data(as_text=True)
        assert active.id in body
        assert expired.id not in body

    def test_renders_when_sessions_cannot_be_listed(
        self, client, use_context, fake_vclient
    ) -> None:
        """Verify the selection cards still render when listing sessions fails."""
        # Given an API that fails to list sessions
        campaign = use_context(user_role="STORYTELLER").campaigns[0]
        fake_vclient.set_error(Routes.CHARACTERS_CHARGEN_SESSIONS_LIST, status_code=500)

        # When requesting the selection cards
        response = client.get(f"/campaign/{campaign.id}/characters/new/cards")

        # Then the cards render with the creation options still reachable
        assert response.status_code == 200
        assert f"/campaign/{campaign.id}/characters/new/multi-autogen" in response.get_data(
            as_text=True
        )


class TestResumeSessionView:
    """Tests for GET /campaign/<id>/characters/new/multi-autogen/session/<sid>/resume."""

    def test_renders_comparison_for_valid_session(self, client, use_context, fake_vclient) -> None:
        """Verify resuming a session shows its characters to choose from."""
        # Given a session in this campaign
        campaign = use_context(user_role="PLAYER").campaigns[0]
        fake_vclient.set_response(
            Routes.CHARACTERS_CHARGEN_SESSION_GET,
            model=ChargenSessionResponseFactory.build(
                id="sess-abc",
                campaign_id=campaign.id,
                characters=[CharacterFactory.build(name_full="Resumed Choice")],
                expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
            ),
        )

        # When resuming the session
        response = client.get(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/session/sess-abc/resume",
            headers={"HX-Request": "true"},
        )

        # Then the comparison view shows the session's character
        body = response.get_data(as_text=True)
        assert 'value="sess-abc"' in body
        assert "Resumed Choice" in body

    def test_redirects_on_expired_session(self, client, use_context, fake_vclient) -> None:
        """Verify a missing session redirects to the selection page."""
        # Given an API that no longer has the session
        campaign = use_context(user_role="PLAYER").campaigns[0]
        fake_vclient.set_error(Routes.CHARACTERS_CHARGEN_SESSION_GET, status_code=404)

        # When resuming the session
        response = client.get(
            f"/campaign/{campaign.id}/characters/new/multi-autogen/session/sess-abc/resume",
            headers={"HX-Request": "true"},
        )

        # Then user is redirected to the selection page
        assert f"/campaign/{campaign.id}/characters/new" in response.headers.get("HX-Redirect", "")
