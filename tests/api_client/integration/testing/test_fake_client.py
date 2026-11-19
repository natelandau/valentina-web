"""Integration tests for FakeVClient -- verifies the full stack works."""

from collections.abc import Callable

import pytest

from tests.api_client.payloads import page
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import ConflictError
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


def test_context_manager():
    """Verify FakeVClient is open inside a with block and closed after it."""
    # When using FakeVClient as a context manager
    with FakeVClient() as client:
        # Then the client is open inside the block
        assert not client.is_closed

    # Then the client is closed after exiting
    assert client.is_closed


def _first(result: list) -> object:
    return result[0]


@pytest.mark.parametrize(
    ("call", "expected_type"),
    [
        (lambda client: _first(client.companies.list_all()), Company),
        (lambda _: _first(companies_service().list_all()), Company),
        (lambda _: _first(campaigns_service("on-behalf-of-user").list_all()), Campaign),
        (lambda _: companies_service().get_page(), PaginatedResponse),
        (lambda _: system_service().health(), SystemHealth),
        (lambda _: campaigns_service("on-behalf-of-user").delete("some-id"), type(None)),
        (
            lambda _: identity_service(company_id="company123").identify(
                provider="apple", token="fake-token"
            ),
            IdentityResolution,
        ),
        (
            lambda _: users_service("user123", company_id="company123").link_identity(
                "user123", provider="discord", token="fake-token"
            ),
            User,
        ),
        (
            lambda _: users_service("user123", company_id="company123").unlink_identity(
                "user123", provider="discord"
            ),
            User,
        ),
        (
            lambda _: users_service("user123", company_id="company123").upload_avatar(
                "user123", filename="pic.png", content=b"img"
            ),
            User,
        ),
        (
            lambda _: users_service("user123", company_id="company123").delete_avatar("user123"),
            User,
        ),
        (
            lambda client: client.character_traits("ch1", "user1", company_id="co1").get_tracker(
                "ct1"
            ),
            CounterTracker,
        ),
        (lambda client: client.characters("user1", company_id="co1").get_health("ch1"), Health),
    ],
    ids=[
        "client-property-list",
        "registry-list",
        "scoped-registry-list",
        "get-page",
        "single-resource",
        "delete",
        "identify",
        "link-identity",
        "unlink-identity",
        "upload-avatar",
        "delete-avatar",
        "tracker",
        "health",
    ],
)
def test_default_responses_parse(call: Callable[[FakeVClient], object], expected_type: type):
    """Verify every kind of route answers with a parseable default when nothing is overridden."""
    with FakeVClient() as client:
        # When calling the service with no overrides
        result = call(client)

        # Then the client parses the fake's default into the expected model
        assert isinstance(result, expected_type)


def test_add_route_overrides_default():
    """Verify a raw add_route override is what the service returns."""
    with FakeVClient() as client:
        # Given a custom route override for users
        client.add_route("GET", Endpoints.USERS, json=page(UserFactory.build(id="custom-user")))

        # When listing users
        result = users_service("on-behalf-of-user").list_all()

        # Then the overridden data is returned
        assert result[0].id == "custom-user"


def test_set_error_headers_populate_conflict_retry_after():
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


def test_tracker_override_with_other_variant():
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
