"""Tests for character creation service."""

from unittest.mock import MagicMock

import pytest
from flask import Flask

from tests.helpers import make_cache_store_mock
from vweb.api_client.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    ChargenSessionResponseFactory,
    Routes,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)


class TestGenerateSingle:
    """Tests for generate_single()."""

    def test_calls_autogen_with_required_fields_only(self, app: Flask, mocker) -> None:
        """Verify generate_single passes character_type and skips None optionals."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected_character = CharacterFactory.build()
        mock_service.generate_character.return_value = expected_character
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import generate_single

        # When calling with only required fields
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = generate_single(
                campaign_id="c1",
                character_type="PLAYER",
            )

        # Then the service is called with character_type and no optionals
        mock_service.generate_character.assert_called_once_with(
            campaign_id="c1",
            character_type="PLAYER",
            character_class=None,
            experience_level=None,
            skill_focus=None,
            concept_id=None,
            vampire_clan_id=None,
            werewolf_tribe_id=None,
            werewolf_auspice_id=None,
        )
        assert result == expected_character

    def test_passes_all_optional_fields(self, app: Flask, mocker) -> None:
        """Verify generate_single forwards all optional parameters."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected_character = CharacterFactory.build()
        mock_service.generate_character.return_value = expected_character
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import generate_single

        # When calling with all optional fields
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = generate_single(
                campaign_id="c1",
                character_type="NPC",
                character_class="VAMPIRE",
                experience_level="ADVANCED",
                skill_focus="SPECIALIST",
                concept_id="concept-123",
                vampire_clan_id="clan-456",
            )

        # Then all fields are forwarded
        mock_service.generate_character.assert_called_once_with(
            campaign_id="c1",
            character_type="NPC",
            character_class="VAMPIRE",
            experience_level="ADVANCED",
            skill_focus="SPECIALIST",
            concept_id="concept-123",
            vampire_clan_id="clan-456",
            werewolf_tribe_id=None,
            werewolf_auspice_id=None,
        )
        assert result == expected_character


class TestStartSession:
    """Tests for start_session()."""

    def test_starts_chargen_session(self, app: Flask, mocker) -> None:
        """Verify start_session calls the chargen start endpoint."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected_response = ChargenSessionResponseFactory.build()
        mock_service.start_chargen_session.return_value = expected_response
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import start_session

        # When starting a session
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = start_session(campaign_id="c1")

        # Then the session response is returned
        mock_service.start_chargen_session.assert_called_once()
        assert result == expected_response


class TestFinalizeSession:
    """Tests for finalize_session()."""

    def test_finalizes_with_selected_character(self, app: Flask, mocker) -> None:
        """Verify finalize_session passes session_id and selected_character_id."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected_character = CharacterFactory.build()
        mock_service.finalize_chargen_session.return_value = expected_character
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import finalize_session

        # When finalizing
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = finalize_session(
                campaign_id="c1",
                session_id="sess-1",
                selected_character_id="char-2",
            )

        # Then the correct IDs are passed
        mock_service.finalize_chargen_session.assert_called_once_with(
            session_id="sess-1",
            selected_character_id="char-2",
        )
        assert result == expected_character


class TestFetchFormOptions:
    """Tests for fetch_form_options()."""

    def test_returns_all_dropdown_data(self, app, mocker, fake_vclient) -> None:
        """Verify fetch_form_options returns enum lists and blueprint data."""
        # Given mocked blueprint service, base cache store, and options
        make_cache_store_mock(mocker, "vweb.lib.cache.base.cache")

        concepts = CharacterConceptFactory.batch(2)
        clans = VampireClanFactory.batch(3)
        tribes = WerewolfTribeFactory.batch(2)
        auspices = WerewolfAuspiceFactory.batch(2)
        fake_vclient.set_response(Routes.BLUEPRINT_CONCEPTS_LIST, items=concepts)
        fake_vclient.set_response(Routes.BLUEPRINT_VAMPIRE_CLANS_LIST, items=clans)
        fake_vclient.set_response(Routes.BLUEPRINT_WEREWOLF_TRIBES_LIST, items=tribes)
        fake_vclient.set_response(Routes.BLUEPRINT_WEREWOLF_AUSPICES_LIST, items=auspices)

        from vweb.lib.cache.options import ApiOptions, CharacterOptions

        mock_opts = ApiOptions(
            characters=CharacterOptions(
                character_type=["PLAYER", "NPC", "STORYTELLER"],
                character_class=["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                autogen_experience_level=["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                ability_focus=["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
            ),
        )
        mocker.patch("vweb.lib.cache.options.get", return_value=mock_opts)

        from vweb.routes.character_create.autogen_services import fetch_form_options

        # When fetching options
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = fetch_form_options()

        # Then enum lists and blueprint data are returned
        assert result["concepts"] == concepts
        assert result["vampire_clans"] == clans
        assert result["werewolf_tribes"] == tribes
        assert result["werewolf_auspices"] == auspices
        assert len(result["character_classes"]) > 0
        assert len(result["experience_levels"]) > 0
        assert len(result["skill_focuses"]) > 0


class TestListSessions:
    """Tests for list_sessions."""

    def test_returns_sessions_from_api(self, app: Flask, fake_vclient) -> None:
        """Verify list_sessions returns sessions from the API."""
        # Given an API with two chargen sessions in this campaign and one in another
        sessions = ChargenSessionResponseFactory.batch(2, campaign_id="c1")
        other = ChargenSessionResponseFactory.build(campaign_id="c2")
        fake_vclient.set_response(
            Routes.CHARACTERS_CHARGEN_SESSIONS_LIST, items=[sessions[0], other, sessions[1]]
        )

        from vweb.routes.character_create.autogen_services import list_sessions

        # When listing sessions
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = list_sessions(campaign_id="c1")

        # Then only this campaign's sessions are returned
        assert result == sessions

    def test_returns_empty_list_when_no_sessions(self, app: Flask, fake_vclient) -> None:
        """Verify list_sessions returns empty list when no sessions exist."""
        # Given an API with no chargen sessions
        fake_vclient.set_response(Routes.CHARACTERS_CHARGEN_SESSIONS_LIST, items=[])

        from vweb.routes.character_create.autogen_services import list_sessions

        # When listing sessions
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = list_sessions(campaign_id="c1")

        # Then empty list is returned
        assert result == []


class TestGetSession:
    """Tests for get_session."""

    def test_returns_session_from_api(self, app: Flask, mocker) -> None:
        """Verify get_session returns the requested session."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected = ChargenSessionResponseFactory.build(id="sess-123", campaign_id="c1")
        mock_service.get.return_value = expected
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import get_session

        # When getting the session
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"
            result = get_session(campaign_id="c1", session_id="sess-123")

        # Then the session is returned
        assert result.id == "sess-123"
        mock_service.get.assert_called_once_with("sess-123")

    def test_rejects_session_from_another_campaign(self, app: Flask, mocker) -> None:
        """Verify get_session raises NotFoundError for a session in a different campaign."""
        # Given a session that belongs to another campaign
        mock_service = MagicMock()
        mock_service.get.return_value = ChargenSessionResponseFactory.build(
            id="sess-123", campaign_id="c2"
        )
        mocker.patch(
            "vweb.routes.character_create.autogen_services.api_services.character_autogen",
            return_value=mock_service,
        )

        from vweb.api_client.exceptions import NotFoundError
        from vweb.routes.character_create.autogen_services import get_session

        # When getting it under campaign c1
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "u1"

            # Then it is refused as not found
            with pytest.raises(NotFoundError):
                get_session(campaign_id="c1", session_id="sess-123")
