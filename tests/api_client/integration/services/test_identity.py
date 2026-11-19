"""Tests for vweb.api_client.services.identity."""

import json
import typing

import pytest
import respx

from tests.api_client.payloads import endpoint_url, sent_json
from vweb.api_client.constants import IdentityResolutionType
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import UserIdentifyDTO

COMPANY_ID = "company123"


@pytest.fixture
def identify_url(base_url) -> str:
    """Return the fully-formatted identify endpoint URL."""
    return endpoint_url(base_url, Endpoints.AUTH_IDENTIFY, company_id=COMPANY_ID)


class TestIdentityServiceIdentify:
    """Tests for IdentityService.identify method."""

    @respx.mock
    @pytest.mark.parametrize("resolution", typing.get_args(IdentityResolutionType))
    def test_identify_with_kwargs(self, vclient, identify_url, user_response_data, resolution):
        """Verify identify sends only the given fields, without acting on behalf of a user."""
        # Given: A mocked identify endpoint
        route = respx.post(identify_url).respond(
            200, json={"resolution": resolution, "user": user_response_data}
        )

        # When: Identifying a provider login
        result = vclient.identity(company_id=COMPANY_ID).identify(
            provider="apple",
            token="eyJraWQi...",
        )

        # Then: Only the provided fields are sent, with no On-Behalf-Of header
        request = route.calls.last.request
        assert json.loads(request.content) == {"provider": "apple", "token": "eyJraWQi..."}
        assert "on-behalf-of" not in request.headers

        # Then: The resolution and embedded user are parsed
        assert result.resolution == resolution
        assert result.user.id == user_response_data["id"]

    @respx.mock
    def test_identify_with_model(self, vclient, identify_url, user_response_data):
        """Verify identifying via a UserIdentifyDTO sends the create-only fields."""
        # Given: A mocked identify endpoint
        route = respx.post(identify_url).respond(
            200, json={"resolution": "created", "user": user_response_data}
        )

        # When: Identifying with an explicit request model
        request = UserIdentifyDTO(
            provider="github",
            token="gho_abc",
            username="octocat",
            email="octo@example.com",
        )
        vclient.identity(company_id=COMPANY_ID).identify(request=request)

        # Then: The optional create fields are sent
        assert sent_json(route) == {
            "provider": "github",
            "token": "gho_abc",
            "username": "octocat",
            "email": "octo@example.com",
        }

    @respx.mock
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"provider": "myspace", "token": "x"}, id="unknown-provider"),
            pytest.param({"provider": "apple"}, id="missing-token"),
        ],
    )
    def test_identify_invalid_input_fails_client_side(self, vclient, kwargs):
        """Verify invalid input raises RequestValidationError before any request."""
        # When/Then: Client-side validation rejects the input
        with pytest.raises(RequestValidationError):
            vclient.identity(company_id=COMPANY_ID).identify(**kwargs)

        assert not respx.calls
