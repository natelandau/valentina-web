"""Tests for vweb.api_client.services.identity."""

import json
import typing

import pytest
import respx

from vweb.api_client.constants import IdentityResolutionType
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError, UnprocessableEntityError
from vweb.api_client.models import IdentityResolution, User, UserIdentifyDTO

COMPANY_ID = "company123"


@pytest.fixture
def identify_url(base_url) -> str:
    """Return the fully-formatted identify endpoint URL."""
    return f"{base_url}{Endpoints.AUTH_IDENTIFY.format(company_id=COMPANY_ID)}"


class TestIdentityServiceIdentify:
    """Tests for IdentityService.identify method."""

    @respx.mock
    @pytest.mark.parametrize("resolution", typing.get_args(IdentityResolutionType))
    def test_identify_with_kwargs(self, vclient, identify_url, user_response_data, resolution):
        """Verify identifying via kwargs returns an IdentityResolution."""
        # Given: A mocked identify endpoint
        route = respx.post(identify_url).respond(
            200, json={"resolution": resolution, "user": user_response_data}
        )

        # When: Identifying a provider login
        result = vclient.identity(company_id=COMPANY_ID).identify(
            provider="apple",
            token="eyJraWQi...",
        )

        # Then: The resolution and embedded user are returned
        assert route.called
        assert isinstance(result, IdentityResolution)
        assert result.resolution == resolution
        assert isinstance(result.user, User)

        # Then: Only the provided fields are serialized (exclude_none)
        body = json.loads(route.calls.last.request.content)
        assert body == {"provider": "apple", "token": "eyJraWQi..."}

    @respx.mock
    def test_identify_with_model(self, vclient, identify_url, user_response_data):
        """Verify identifying via a UserIdentifyDTO includes create-only fields."""
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
        result = vclient.identity(company_id=COMPANY_ID).identify(request=request)

        # Then: The optional create fields are serialized into the body
        assert route.called
        assert isinstance(result, IdentityResolution)
        body = json.loads(route.calls.last.request.content)
        assert body["provider"] == "github"
        assert body["username"] == "octocat"
        assert body["email"] == "octo@example.com"

    @respx.mock
    def test_identify_verification_failure(self, vclient, identify_url):
        """Verify a 422 response raises UnprocessableEntityError with its code."""
        # Given: The API rejects the provider token
        respx.post(identify_url).respond(
            422,
            json={
                "detail": "Provider token failed verification",
                "code": "TOKEN_VERIFICATION_FAILED",
            },
        )

        # When/Then: The verification failure surfaces with its code
        with pytest.raises(UnprocessableEntityError) as exc_info:
            vclient.identity(company_id=COMPANY_ID).identify(
                provider="apple",
                token="expired",
            )
        assert exc_info.value.code == "TOKEN_VERIFICATION_FAILED"

    @respx.mock
    def test_identify_unknown_provider_fails_client_side(self, vclient):
        """Verify an unsupported provider raises RequestValidationError before any request."""
        # When/Then: Client-side validation rejects the unknown provider
        with pytest.raises(RequestValidationError):
            vclient.identity(company_id=COMPANY_ID).identify(
                provider="myspace",
                token="x",
            )

    @respx.mock
    def test_identify_missing_token_fails_client_side(self, vclient):
        """Verify a missing token raises RequestValidationError before any request."""
        # When/Then: Client-side validation rejects the missing token
        with pytest.raises(RequestValidationError):
            vclient.identity(company_id=COMPANY_ID).identify(provider="apple")

    @respx.mock
    def test_identify_does_not_send_on_behalf_of_header(
        self, vclient, identify_url, user_response_data
    ):
        """Verify the On-Behalf-Of header is absent from identify requests."""
        # Given: A mocked identify endpoint
        route = respx.post(identify_url).respond(
            200, json={"resolution": "created", "user": user_response_data}
        )

        # When: Identifying a provider login
        vclient.identity(company_id=COMPANY_ID).identify(
            provider="google",
            token="id-token",
        )

        # Then: The On-Behalf-Of header is not present
        assert route.called
        request_headers = route.calls.last.request.headers
        assert "on-behalf-of" not in {k.lower() for k in request_headers}
