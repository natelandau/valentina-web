"""Integration tests for CharacterAutogenService."""

import pytest
import respx
from respx import MockResponse

from tests.api_client.payloads import wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import Character, ChargenSessionResponse
from vweb.api_client.testing import ChargenSessionResponseFactory


@pytest.fixture
def character_autogen_response_data(character_response_data: dict) -> dict:
    """Return chargen session response data offering two characters."""
    return wire(
        ChargenSessionResponseFactory.build(
            id="session123",
            requires_selection=True,
            characters=[character_response_data, character_response_data],
        )
    )


class TestCharacterAutogenService:
    """Tests for CharacterAutogenService."""

    @respx.mock
    def test_start_chargen_session(
        self, vclient, base_url, character_autogen_response_data
    ) -> None:
        """Verify starting a chargen session returns ChargenSessionResponse."""
        # Given: A mocked endpoint returning ChargenSessionResponse
        route = respx.post(
            f"{base_url}{Endpoints.CHARGEN_START.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=character_autogen_response_data))

        # When: Starting a chargen session
        result = vclient.character_autogen(
            "on-behalf-of-user", company_id="company123"
        ).start_chargen_session(campaign_id="campaign123")

        # Then: The route was called with correct params
        assert route.called
        assert isinstance(result, ChargenSessionResponse)
        assert result.id == "session123"


class TestCharacterAutogenServiceFinalizeChargenSession:
    """Tests for CharacterAutogenService finalize_chargen_session."""

    @respx.mock
    def test_finalize_chargen_session(
        self, vclient, base_url, character_response_data: dict
    ) -> None:
        """Verify finalizing a chargen session returns Character."""
        # Given: A mocked endpoint returning Character
        route = respx.post(
            f"{base_url}{Endpoints.CHARGEN_FINALIZE.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Finalizing a chargen session
        result = vclient.character_autogen(
            "on-behalf-of-user", company_id="company123"
        ).finalize_chargen_session("session123", "char123")

        # Then: The route was called with correct params
        assert route.called
        assert isinstance(result, Character)
        assert result.id == "char123"
        assert result.name_first == "John"
        assert result.name_last == "Doe"
        assert result.character_class == "VAMPIRE"
        assert result.game_version == "V5"


class TestCharacterAutogenerateCharacter:
    """Tests for CharacterAutogenService generate_character."""

    @respx.mock
    def test_generate_character(self, vclient, base_url, character_response_data: dict) -> None:
        """Verify generating a character returns Character."""
        # Given: A mocked endpoint returning Character
        route = respx.post(
            f"{base_url}{Endpoints.AUTOGENERATE.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Generating a character
        result = vclient.character_autogen(
            "on-behalf-of-user", company_id="company123"
        ).generate_character(campaign_id="campaign123", character_type="PLAYER")

        # Then: The route was called with correct params
        assert route.called
        assert isinstance(result, Character)
        assert result.id == "char123"
        assert result.name_first == "John"


class TestCharacterAutogenServiceListSessions:
    """Tests for CharacterAutogenService list_all."""

    @respx.mock
    def test_list_all(self, vclient, base_url, character_autogen_response_data) -> None:
        """Verify listing chargen sessions returns list of ChargenSessionResponse."""
        # Given: A mocked endpoint returning a JSON array
        route = respx.get(
            f"{base_url}{Endpoints.CHARGEN_SESSIONS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(
            return_value=MockResponse(
                200, json=[character_autogen_response_data, character_autogen_response_data]
            )
        )

        # When: Listing all chargen sessions
        result = vclient.character_autogen("on-behalf-of-user", company_id="company123").list_all()

        # Then: The route was called and returned a list
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(r, ChargenSessionResponse) for r in result)
        assert result[0].id == "session123"

    @respx.mock
    def test_list_all_empty(self, vclient, base_url) -> None:
        """Verify listing chargen sessions with no results returns empty list."""
        # Given: A mocked endpoint returning an empty JSON array
        route = respx.get(
            f"{base_url}{Endpoints.CHARGEN_SESSIONS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=[]))

        # When: Listing all chargen sessions
        result = vclient.character_autogen("on-behalf-of-user", company_id="company123").list_all()

        # Then: The route was called and returned an empty list
        assert route.called
        assert result == []


class TestCharacterAutogenServiceGetSession:
    """Tests for CharacterAutogenService get."""

    @respx.mock
    def test_get(self, vclient, base_url, character_autogen_response_data) -> None:
        """Verify getting a chargen session returns ChargenSessionResponse."""
        # Given: A mocked endpoint returning a single session
        route = respx.get(
            f"{base_url}{Endpoints.CHARGEN_SESSION.format(company_id='company123', user_id='user123', campaign_id='campaign123', session_id='session123')}"
        ).mock(return_value=MockResponse(200, json=character_autogen_response_data))

        # When: Getting a specific chargen session
        result = vclient.character_autogen("on-behalf-of-user", company_id="company123").get(
            "session123"
        )

        # Then: The route was called and returned the session
        assert route.called
        assert isinstance(result, ChargenSessionResponse)
        assert result.id == "session123"
        assert result.requires_selection is True
        assert len(result.characters) == 2
