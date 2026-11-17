"""Tests for vweb.api_client.services.user_lookup."""

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import AuthenticationError
from vweb.api_client.models import UserLookupResult


@pytest.fixture
def lookup_result_data() -> dict:
    """Return sample user lookup result data."""
    return {
        "company_id": "507f1f77bcf86cd799439011",
        "company_name": "My Game Shop",
        "user_id": "507f1f77bcf86cd799439022",
        "role": "PLAYER",
    }


class TestUserLookupServiceByEmail:
    """Tests for UserLookupService.by_email method."""

    @respx.mock
    def test_by_email(self, vclient, base_url, lookup_result_data):
        """Verify by_email returns list of UserLookupResult."""
        # Given: A mocked lookup endpoint
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"email": "alice@example.com"},
        ).respond(200, json=[lookup_result_data])

        # When: Looking up by email
        results = vclient.user_lookup.by_email("alice@example.com")

        # Then: Returns list of UserLookupResult
        assert route.called
        assert len(results) == 1
        assert isinstance(results[0], UserLookupResult)
        assert results[0].company_id == "507f1f77bcf86cd799439011"
        assert results[0].company_name == "My Game Shop"
        assert results[0].user_id == "507f1f77bcf86cd799439022"
        assert results[0].role == "PLAYER"


class TestUserLookupServiceByDiscordId:
    """Tests for UserLookupService.by_discord_id method."""

    @respx.mock
    def test_by_discord_id(self, vclient, base_url, lookup_result_data):
        """Verify by_discord_id returns list of UserLookupResult."""
        # Given: A mocked lookup endpoint
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"discord_id": "123456789"},
        ).respond(200, json=[lookup_result_data])

        # When: Looking up by Discord ID
        results = vclient.user_lookup.by_discord_id("123456789")

        # Then: Returns list of UserLookupResult
        assert route.called
        assert len(results) == 1
        assert isinstance(results[0], UserLookupResult)


class TestUserLookupServiceByGoogleId:
    """Tests for UserLookupService.by_google_id method."""

    @respx.mock
    def test_by_google_id(self, vclient, base_url, lookup_result_data):
        """Verify by_google_id returns list of UserLookupResult."""
        # Given: A mocked lookup endpoint
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"google_id": "google-abc-123"},
        ).respond(200, json=[lookup_result_data])

        # When: Looking up by Google ID
        results = vclient.user_lookup.by_google_id("google-abc-123")

        # Then: Returns list of UserLookupResult
        assert route.called
        assert len(results) == 1
        assert isinstance(results[0], UserLookupResult)


class TestUserLookupServiceByGithubId:
    """Tests for UserLookupService.by_github_id method."""

    @respx.mock
    def test_by_github_id(self, vclient, base_url, lookup_result_data):
        """Verify by_github_id returns list of UserLookupResult."""
        # Given: A mocked lookup endpoint
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"github_id": "github-xyz-456"},
        ).respond(200, json=[lookup_result_data])

        # When: Looking up by GitHub ID
        results = vclient.user_lookup.by_github_id("github-xyz-456")

        # Then: Returns list of UserLookupResult
        assert route.called
        assert len(results) == 1
        assert isinstance(results[0], UserLookupResult)


class TestUserLookupServiceByAppleId:
    """Tests for UserLookupService.by_apple_id method."""

    @respx.mock
    def test_by_apple_id(self, vclient, base_url, lookup_result_data):
        """Verify by_apple_id returns list of UserLookupResult."""
        # Given: A mocked lookup endpoint
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"apple_id": "001234.abcd5678"},
        ).respond(200, json=[lookup_result_data])

        # When: Looking up by Apple ID
        results = vclient.user_lookup.by_apple_id("001234.abcd5678")

        # Then: Returns list of UserLookupResult
        assert route.called
        assert len(results) == 1
        assert isinstance(results[0], UserLookupResult)


class TestUserLookupServiceEmptyResults:
    """Tests for empty result handling."""

    @respx.mock
    def test_returns_empty_list(self, vclient, base_url):
        """Verify empty array from API returns empty list."""
        # Given: A mocked lookup endpoint returning empty array
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"email": "nobody@example.com"},
        ).respond(200, json=[])

        # When: Looking up a non-existent user
        results = vclient.user_lookup.by_email("nobody@example.com")

        # Then: Returns empty list
        assert route.called
        assert results == []


class TestUserLookupServiceMultipleResults:
    """Tests for multiple result handling."""

    @respx.mock
    def test_multiple_results(self, vclient, base_url):
        """Verify multiple results are parsed correctly."""
        # Given: A mocked lookup endpoint returning multiple results
        response_data = [
            {
                "company_id": "company-1",
                "company_name": "First Shop",
                "user_id": "user-1",
                "role": "PLAYER",
            },
            {
                "company_id": "company-2",
                "company_name": "Second Shop",
                "user_id": "user-2",
                "role": "ADMIN",
            },
        ]
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"email": "multi@example.com"},
        ).respond(200, json=response_data)

        # When: Looking up a user in multiple companies
        results = vclient.user_lookup.by_email("multi@example.com")

        # Then: All results are parsed
        assert route.called
        assert len(results) == 2
        assert results[0].company_name == "First Shop"
        assert results[1].company_name == "Second Shop"


class TestUserLookupServiceErrors:
    """Tests for error handling."""

    @respx.mock
    def test_authentication_error(self, vclient, base_url):
        """Verify 401 raises AuthenticationError."""
        # Given: A mocked lookup endpoint returning 401
        route = respx.get(
            f"{base_url}{Endpoints.USERS_LOOKUP}",
            params={"email": "test@example.com"},
        ).respond(
            401,
            json={
                "type": "about:blank",
                "title": "Authentication Required",
                "status": 401,
                "detail": "Invalid API key",
            },
        )

        # When/Then: AuthenticationError is raised
        with pytest.raises(AuthenticationError):
            vclient.user_lookup.by_email("test@example.com")

        assert route.called
