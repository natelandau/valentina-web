"""Integration tests for FakeVClient -- verifies the full stack works."""

import pytest

from vweb.api_client.exceptions import ConflictError, NotFoundError, UnprocessableEntityError
from vweb.api_client.models import (
    Campaign,
    Company,
    CounterTracker,
    Health,
    IdentityResolution,
    PaginatedResponse,
    StainsTracker,
    SystemHealth,
    User,
)
from vweb.api_client.registry import (
    campaigns_service,
    companies_service,
    identity_service,
    system_service,
    users_service,
)
from vweb.api_client.testing import FakeVClient, Routes, StainsTrackerFactory, UserFactory


class TestFakeVClientBasicUsage:
    """FakeVClient should work as a drop-in replacement for VClient."""

    def test_context_manager(self):
        """Verify FakeVClient works as a context manager."""
        # When using FakeVClient as a context manager
        with FakeVClient() as client:
            # Then the client is open inside the block
            assert not client.is_closed

        # Then the client is closed after exiting
        assert client.is_closed

    def test_companies_list_all(self):
        """Verify listing companies returns Company models."""
        with FakeVClient() as client:
            # When listing all companies
            companies = client.companies
            result = companies.list_all()

            # Then the result contains Company instances
            assert isinstance(result, list)
            assert len(result) >= 1
            assert isinstance(result[0], Company)

    def test_factory_function_works(self):
        """Verify factory functions work with FakeVClient as default client."""
        with FakeVClient() as _client:
            # When using a factory function
            result = companies_service().list_all()

            # Then the result contains Company instances
            assert isinstance(result, list)
            assert isinstance(result[0], Company)

    def test_scoped_service_works(self):
        """Verify scoped factory functions work with FakeVClient."""
        with FakeVClient() as _client:
            # When using a scoped factory function
            result = campaigns_service("on-behalf-of-user").list_all()

            # Then the result contains Campaign instances
            assert isinstance(result, list)
            assert isinstance(result[0], Campaign)

    def test_get_page_returns_paginated_response(self):
        """Verify get_page returns a PaginatedResponse with typed items."""
        with FakeVClient() as _client:
            # When getting a page of companies
            result = companies_service().get_page()

            # Then the result is a PaginatedResponse with Company items
            assert isinstance(result, PaginatedResponse)
            assert isinstance(result.items[0], Company)

    def test_get_single_resource(self):
        """Verify fetching a single resource returns the correct model."""
        with FakeVClient() as _client:
            # When fetching system health
            result = system_service().health()

            # Then the result is a SystemHealth instance
            assert isinstance(result, SystemHealth)

    def test_delete_succeeds(self):
        """Verify delete operations complete without error."""
        with FakeVClient() as _client:
            # When deleting a campaign
            campaigns_service("on-behalf-of-user").delete("some-id")

    def test_default_company_id(self):
        """Verify custom default_company_id is preserved."""
        # When creating a FakeVClient with a custom default_company_id
        with FakeVClient(default_company_id="my-company") as client:
            # Then the default_company_id is accessible
            assert client.default_company_id == "my-company"


class TestFakeVClientOverrides:
    """FakeVClient should support route overrides."""

    def test_override_list_endpoint(self):
        """Verify custom route overrides return user-defined data."""
        with FakeVClient() as client:
            from vweb.api_client.endpoints import Endpoints

            # Given a custom route override for users
            client.add_route(
                "GET",
                Endpoints.USERS,
                json={
                    "items": [
                        {
                            "id": "custom-user",
                            "date_created": "2024-01-01T00:00:00Z",
                            "date_modified": "2024-01-01T00:00:00Z",
                            "name_first": "Test",
                            "name_last": "User",
                            "username": "testuser",
                            "email": "test@example.com",
                            "role": "PLAYER",
                            "company_id": "fake-company",
                            "discord_profile": None,
                            "campaign_experience": [],
                            "asset_ids": [],
                        }
                    ],
                    "total": 1,
                    "limit": 10,
                    "offset": 0,
                },
            )

            # When listing users
            result = users_service("on-behalf-of-user").list_all()

            # Then the overridden data is returned
            assert result[0].id == "custom-user"


class TestIdentityRoutes:
    """FakeVClient should serve the identity resolution routes."""

    def test_identify_default_response(self):
        """Verify the identify route returns a factory-built IdentityResolution."""
        with FakeVClient():
            # When identifying a provider login with no overrides
            result = identity_service(company_id="company123").identify(
                provider="apple",
                token="fake-token",
            )

            # Then a valid IdentityResolution is returned
            assert isinstance(result, IdentityResolution)
            assert result.resolution in {"matched", "linked", "created"}

    def test_identify_set_response(self):
        """Verify set_response overrides the identify route."""
        with FakeVClient() as client:
            # Given an overridden identify response
            user = UserFactory.build()
            override = IdentityResolution(resolution="created", user=user)
            client.set_response(Routes.IDENTITY_IDENTIFY, model=override)

            # When identifying a provider login
            result = identity_service(company_id="company123").identify(
                provider="google",
                token="fake-token",
            )

            # Then the override is returned
            assert result.resolution == "created"
            assert result.user.id == user.id

    def test_identify_set_error(self):
        """Verify set_error simulates a 422 verification failure."""
        with FakeVClient() as client:
            # Given the identify route configured to fail verification
            client.set_error(
                Routes.IDENTITY_IDENTIFY,
                status_code=422,
                detail="bad token",
                code="TOKEN_VERIFICATION_FAILED",
            )

            # When/Then identifying raises UnprocessableEntityError with the code
            with pytest.raises(UnprocessableEntityError) as exc_info:
                identity_service(company_id="company123").identify(
                    provider="apple",
                    token="expired",
                )
            assert exc_info.value.code == "TOKEN_VERIFICATION_FAILED"

    def test_link_identity_default_response(self):
        """Verify the link route returns a factory-built User."""
        with FakeVClient():
            # When linking an identity with no overrides
            result = users_service("user123", company_id="company123").link_identity(
                "user123",
                provider="discord",
                token="fake-token",
            )

            # Then a valid User is returned
            assert isinstance(result, User)

    def test_link_identity_set_error_conflict(self):
        """Verify set_error simulates an identity conflict."""
        with FakeVClient() as client:
            # Given the link route configured to conflict
            client.set_error(
                Routes.USERS_IDENTITY_LINK,
                status_code=409,
                detail="already linked",
                code="IDENTITY_ALREADY_LINKED",
            )

            # When/Then linking raises ConflictError with the code
            with pytest.raises(ConflictError) as exc_info:
                users_service("user123", company_id="company123").link_identity(
                    "user123",
                    provider="apple",
                    token="fake-token",
                )
            assert exc_info.value.code == "IDENTITY_ALREADY_LINKED"

    def test_set_error_headers_populate_conflict_retry_after(self):
        """Verify a faked in-progress 409 carries Retry-After into ConflictError."""
        with FakeVClient(auto_retry_rate_limit=False) as client:
            # Given the link route faked as an in-progress conflict with Retry-After
            client.set_error(
                Routes.USERS_IDENTITY_LINK,
                status_code=409,
                code="IDEMPOTENCY_IN_PROGRESS",
                headers={"Retry-After": "1"},
            )

            # When linking an identity
            with pytest.raises(ConflictError) as exc_info:
                users_service("user123", company_id="company123").link_identity(
                    "user123",
                    provider="apple",
                    token="fake-token",
                )

            # Then the exception exposes retry_after
            assert exc_info.value.retry_after == 1
            assert exc_info.value.is_idempotency_in_progress is True

    def test_unlink_identity_default_response(self):
        """Verify the unlink route returns a factory-built User."""
        with FakeVClient():
            # When unlinking an identity with no overrides
            result = users_service("user123", company_id="company123").unlink_identity(
                "user123",
                provider="discord",
            )

            # Then a valid User is returned
            assert isinstance(result, User)

    def test_unlink_identity_set_error_last_identity(self):
        """Verify set_error simulates removing the last remaining identity."""
        with FakeVClient() as client:
            # Given the unlink route configured to conflict
            client.set_error(
                Routes.USERS_IDENTITY_UNLINK,
                status_code=409,
                detail="cannot remove last identity",
                code="LAST_IDENTITY",
            )

            # When/Then unlinking raises ConflictError with the code
            with pytest.raises(ConflictError) as exc_info:
                users_service("user123", company_id="company123").unlink_identity(
                    "user123",
                    provider="apple",
                )
            assert exc_info.value.code == "LAST_IDENTITY"


class TestFakeVClientAvatar:
    """FakeVClient should serve the user avatar routes."""

    def test_upload_avatar_default_response(self):
        """Verify the avatar upload route returns a factory-built User."""
        with FakeVClient():
            # When uploading an avatar with no overrides
            result = users_service("user123", company_id="company123").upload_avatar(
                "user123",
                filename="pic.png",
                content=b"img",
            )

            # Then a valid User is returned
            assert isinstance(result, User)

    def test_delete_avatar_default_response(self):
        """Verify the avatar delete route returns a factory-built User."""
        with FakeVClient():
            # When removing an avatar with no overrides
            result = users_service("user123", company_id="company123").delete_avatar(
                "user123",
            )

            # Then a valid User is returned
            assert isinstance(result, User)

    def test_delete_avatar_set_error_not_found(self):
        """Verify set_error simulates a missing user on avatar delete."""
        with FakeVClient() as client:
            # Given the avatar delete route configured to 404
            client.set_error(
                Routes.USERS_AVATAR_DELETE,
                status_code=404,
                detail="User not found",
            )

            # When/Then deleting raises NotFoundError
            with pytest.raises(NotFoundError):
                users_service("user123", company_id="company123").delete_avatar("user123")


class TestTrackerAndHealthRoutes:
    """FakeVClient should serve tracker and health routes."""

    def test_tracker_default_route(self):
        """Verify the default tracker route returns a CounterTracker."""
        with FakeVClient() as client:
            # When getting a tracker with no override
            result = client.character_traits("ch1", "user1", company_id="co1").get_tracker("ct1")

            # Then a CounterTracker is returned
            assert isinstance(result, CounterTracker)

    def test_tracker_override_with_other_variant(self):
        """Verify any tracker variant can override a tracker route."""
        with FakeVClient() as client:
            # Given the action route returns a stains tracker
            stains = StainsTrackerFactory.build()
            client.set_response(Routes.CHARACTER_TRAITS_TRACKER_ACTION, model=stains)

            # When adding a stain
            result = client.character_traits("ch1", "user1", company_id="co1").apply_tracker_action(
                "ct1", "add_stain"
            )

            # Then the stains tracker is returned
            assert isinstance(result, StainsTracker)
            assert result.stains == stains.stains

    def test_health_default_route(self):
        """Verify the default health route returns Health."""
        with FakeVClient() as client:
            # When getting health with no override
            result = client.characters("user1", company_id="co1").get_health("ch1")

            # Then Health is returned
            assert isinstance(result, Health)

    def test_health_error(self):
        """Verify set_error on a health route raises the mapped exception."""
        with FakeVClient() as client:
            # Given the health route returns 404
            client.set_error(Routes.CHARACTERS_HEALTH_GET, status_code=404)

            # When/Then getting health raises NotFoundError
            with pytest.raises(NotFoundError):
                client.characters("user1", company_id="co1").get_health("ch1")
