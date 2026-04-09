"""Tests for character creation service."""

from unittest.mock import MagicMock

from flask import Flask
from vclient.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    ChargenSessionResponseFactory,
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
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import generate_single

        # When calling with only required fields
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = generate_single(
                user_id="u1",
                campaign_id="c1",
                character_type="PLAYER",
            )

        # Then the service is called with character_type and no optionals
        mock_service.generate_character.assert_called_once_with(
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
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import generate_single

        # When calling with all optional fields
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = generate_single(
                user_id="u1",
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
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import start_session

        # When starting a session
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = start_session(user_id="u1", campaign_id="c1")

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
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import finalize_session

        # When finalizing
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = finalize_session(
                user_id="u1",
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

    def test_returns_all_dropdown_data(self, app, mocker) -> None:
        """Verify fetch_form_options returns enum lists and blueprint data."""
        # Given mocked blueprint service, cache, and options
        mock_bp_service = MagicMock()
        concepts = CharacterConceptFactory.batch(2)
        clans = VampireClanFactory.batch(3)
        tribes = WerewolfTribeFactory.batch(2)
        auspices = WerewolfAuspiceFactory.batch(2)
        mock_bp_service.list_all_concepts.return_value = concepts
        mock_bp_service.list_all_vampire_clans.return_value = clans
        mock_bp_service.list_all_werewolf_tribes.return_value = tribes
        mock_bp_service.list_all_werewolf_auspices.return_value = auspices
        mocker.patch(
            "vweb.routes.character_create.autogen_services.sync_character_blueprint_service",
            return_value=mock_bp_service,
        )
        mocker.patch("vweb.routes.character_create.autogen_services.cache.get", return_value=None)
        mocker.patch("vweb.routes.character_create.autogen_services.cache.set")

        from vweb.lib.options_cache import ApiOptions, CharacterOptions

        mock_opts = ApiOptions(
            characters=CharacterOptions(
                character_type=["PLAYER", "NPC", "STORYTELLER", "DEVELOPER"],
                character_class=["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                autogen_experience_level=["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                ability_focus=["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
            ),
        )
        mocker.patch(
            "vweb.routes.character_create.autogen_services.get_options", return_value=mock_opts
        )

        from vweb.routes.character_create.autogen_services import fetch_form_options

        # When fetching options
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
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

    def test_returns_sessions_from_api(self, app: Flask, mocker) -> None:
        """Verify list_sessions returns sessions from the API."""
        # Given a mocked autogen service with two sessions
        mock_service = MagicMock()
        sessions = ChargenSessionResponseFactory.batch(2)
        mock_service.list_all.return_value = sessions
        mocker.patch(
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import list_sessions

        # When listing sessions
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = list_sessions(user_id="u1", campaign_id="c1")

        # Then both sessions are returned
        assert len(result) == 2
        mock_service.list_all.assert_called_once()

    def test_returns_empty_list_when_no_sessions(self, app: Flask, mocker) -> None:
        """Verify list_sessions returns empty list when no sessions exist."""
        # Given a mocked autogen service with no sessions
        mock_service = MagicMock()
        mock_service.list_all.return_value = []
        mocker.patch(
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import list_sessions

        # When listing sessions
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = list_sessions(user_id="u1", campaign_id="c1")

        # Then empty list is returned
        assert result == []


class TestGetSession:
    """Tests for get_session."""

    def test_returns_session_from_api(self, app: Flask, mocker) -> None:
        """Verify get_session returns the requested session."""
        # Given a mocked autogen service
        mock_service = MagicMock()
        expected = ChargenSessionResponseFactory.build(id="sess-123")
        mock_service.get.return_value = expected
        mocker.patch(
            "vweb.routes.character_create.autogen_services.sync_character_autogen_service",
            return_value=mock_service,
        )

        from vweb.routes.character_create.autogen_services import get_session

        # When getting the session
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            result = get_session(user_id="u1", campaign_id="c1", session_id="sess-123")

        # Then the session is returned
        assert result.id == "sess-123"
        mock_service.get.assert_called_once_with("sess-123")
