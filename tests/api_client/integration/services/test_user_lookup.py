"""Tests for vweb.api_client.services.user_lookup."""

import pytest
import respx

from tests.api_client.payloads import sent_params
from vweb.api_client.endpoints import Endpoints


class TestUserLookupService:
    """Tests for UserLookupService lookup methods."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "param", "value"),
        [
            pytest.param("by_email", "email", "alice@example.com", id="email"),
            pytest.param("by_discord_id", "discord_id", "123456789", id="discord"),
            pytest.param("by_google_id", "google_id", "google-abc-123", id="google"),
            pytest.param("by_github_id", "github_id", "github-xyz-456", id="github"),
            pytest.param("by_apple_id", "apple_id", "001234.abcd5678", id="apple"),
        ],
    )
    def test_lookup_sends_its_query_param(self, vclient, base_url, method, param, value):
        """Verify each lookup sends only its own query param and returns no matches as []."""
        # Given: A lookup endpoint with no matches
        route = respx.get(f"{base_url}{Endpoints.USERS_LOOKUP}").respond(200, json=[])

        # When: Looking up the user
        results = getattr(vclient.user_lookup, method)(value)

        # Then: Only the lookup's param is sent and the empty result is a list
        assert sent_params(route) == {param: value}
        assert results == []

    @respx.mock
    def test_lookup_parses_every_result(self, vclient, base_url):
        """Verify a user found in several companies returns one result per company."""
        # Given: The lookup endpoint returns two companies
        respx.get(f"{base_url}{Endpoints.USERS_LOOKUP}").respond(
            200,
            json=[
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
            ],
        )

        # When: Looking up a user in multiple companies
        results = vclient.user_lookup.by_email("multi@example.com")

        # Then: Every result is parsed
        assert [(r.company_id, r.company_name, r.user_id, r.role) for r in results] == [
            ("company-1", "First Shop", "user-1", "PLAYER"),
            ("company-2", "Second Shop", "user-2", "ADMIN"),
        ]
