"""Integration tests for CharacterAutogenService."""

import pytest
import respx
from respx import MockResponse

from tests.api_client.payloads import endpoint_url, sent_json, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.testing import ChargenSessionResponseFactory

COMPANY_ID = "company123"


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


@pytest.fixture
def service(vclient):
    """Return a CharacterAutogenService scoped to a company and user."""
    return vclient.character_autogen("on-behalf-of-user", company_id=COMPANY_ID)


class TestCharacterAutogenService:
    """Tests for CharacterAutogenService."""

    @respx.mock
    def test_start_chargen_session(self, service, base_url, character_autogen_response_data):
        """Verify starting a session sends the campaign as a query param and parses the session."""
        # Given: A start endpoint that only matches the campaign query param
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARGEN_START, company_id=COMPANY_ID),
            params={"campaign_id": "campaign123"},
        ).mock(return_value=MockResponse(200, json=character_autogen_response_data))

        # When: Starting a chargen session
        result = service.start_chargen_session(campaign_id="campaign123")

        # Then: The request matched and the session parses
        assert route.called
        assert result.id == "session123"
        assert len(result.characters) == 2

    @respx.mock
    def test_finalize_chargen_session(self, service, base_url, character_response_data):
        """Verify finalizing sends the session and selected character and returns the Character."""
        # Given: A finalize endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARGEN_FINALIZE, company_id=COMPANY_ID)
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Finalizing a chargen session
        result = service.finalize_chargen_session("session123", "char123")

        # Then: The body names the session and the chosen character
        assert sent_json(route) == {
            "session_id": "session123",
            "selected_character_id": "char123",
        }
        assert result.id == "char123"
        assert result.name_first == "John"

    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            pytest.param({}, {"character_type": "PLAYER"}, id="minimal"),
            pytest.param(
                {
                    "character_class": "VAMPIRE",
                    "concept_id": "concept1",
                    "vampire_clan_id": "clan1",
                },
                {
                    "character_type": "PLAYER",
                    "character_class": "VAMPIRE",
                    "concept_id": "concept1",
                    "vampire_clan_id": "clan1",
                },
                id="with-options",
            ),
        ],
    )
    @respx.mock
    def test_generate_character(
        self, service, base_url, character_response_data, kwargs, expected_body
    ):
        """Verify generating sends only the set options and the campaign as a query param."""
        # Given: An autogenerate endpoint that only matches the campaign query param
        route = respx.post(
            endpoint_url(base_url, Endpoints.AUTOGENERATE, company_id=COMPANY_ID),
            params={"campaign_id": "campaign123"},
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Generating a character
        result = service.generate_character(
            campaign_id="campaign123", character_type="PLAYER", **kwargs
        )

        # Then: Unset options are left out of the body
        assert sent_json(route) == expected_body
        assert result.id == "char123"

    @respx.mock
    def test_list_all(self, service, base_url, character_autogen_response_data):
        """Verify listing sessions parses the bare JSON array."""
        # Given: A sessions endpoint returning a JSON array
        respx.get(endpoint_url(base_url, Endpoints.CHARGEN_SESSIONS, company_id=COMPANY_ID)).mock(
            return_value=MockResponse(
                200, json=[character_autogen_response_data, character_autogen_response_data]
            )
        )

        # When: Listing all chargen sessions
        result = service.list_all()

        # Then: Every item parses into a session
        assert [r.id for r in result] == ["session123", "session123"]

    @respx.mock
    def test_get(self, service, base_url, character_autogen_response_data):
        """Verify getting a session requests it by ID and parses it."""
        # Given: A session endpoint
        respx.get(
            endpoint_url(
                base_url, Endpoints.CHARGEN_SESSION, company_id=COMPANY_ID, session_id="session123"
            )
        ).mock(return_value=MockResponse(200, json=character_autogen_response_data))

        # When: Getting a specific chargen session
        result = service.get("session123")

        # Then: The session parses
        assert result.id == "session123"
        assert result.requires_selection is True
