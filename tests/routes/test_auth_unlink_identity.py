"""Tests for the account-unlinking (connections) flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from vweb.api_client.exceptions import AuthorizationError
from vweb.api_client.models.users import DiscordProfile
from vweb.api_client.testing import (
    AppleProfileFactory,
    GitHubProfileFactory,
    GoogleProfileFactory,
    Routes,
    UserFactory,
)
from vweb.lib.catalog import catalog

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

    from vweb.lib.cache.global_context import GlobalContext

CONNECTIONS_CARD = b'id="connections-card"'


def _post_unlink(client: FlaskClient, provider: str = "github") -> TestResponse:
    """POST the unlink route with a valid CSRF header, as HTMX would."""
    return client.post(f"/auth/{provider}/unlink", headers={"X-CSRFToken": get_csrf(client)})


class TestUnlinkIdentityView:
    """Tests for POST /auth/<provider>/unlink."""

    @pytest.mark.parametrize("provider", ["discord", "github", "google", "apple"])
    def test_unlink_disconnects_identity_and_returns_card(
        self, client: FlaskClient, mocker, fake_vclient, provider: str
    ) -> None:
        """Verify unlinking removes the provider, refreshes the cache, and swaps the card in."""
        # Given an unlink endpoint that succeeds
        fake_vclient.set_response(
            Routes.USERS_IDENTITY_UNLINK, model=UserFactory.build(id="test-user-id")
        )
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the unlink route is hit
        response = _post_unlink(client, provider)

        # Then the identity was unlinked on behalf of the user and the card returned
        (request,) = fake_vclient.assert_called(
            Routes.USERS_IDENTITY_UNLINK,
            params={
                "company_id": "test-company-id",
                "user_id": "test-user-id",
                "provider": provider,
            },
            times=1,
        )
        assert request.headers["on-behalf-of"] == "test-user-id"
        mock_cache_clear.assert_called_once_with("test-company-id", "test-user-id")
        assert response.status_code == 200
        assert CONNECTIONS_CARD in response.data

    @pytest.mark.parametrize(
        ("status_code", "code"),
        [(409, "LAST_IDENTITY"), (404, "IDENTITY_NOT_LINKED"), (403, None), (500, None)],
        ids=["last-identity", "not-linked", "forbidden", "server-error"],
    )
    def test_unlink_failure_returns_unchanged_card(
        self, client: FlaskClient, mocker, fake_vclient, status_code: int, code: str | None
    ) -> None:
        """Verify a refused unlink returns the current card with a message and keeps the cache."""
        # Given the API refuses the unlink
        fake_vclient.set_error(Routes.USERS_IDENTITY_UNLINK, status_code=status_code, code=code)
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the unlink route is hit
        response = _post_unlink(client)

        # Then the card comes back alongside the flash container, and the cache is untouched
        assert response.status_code == 200
        assert CONNECTIONS_CARD in response.data
        assert b'id="flash-messages"' in response.data
        mock_cache_clear.assert_not_called()

    def test_failure_when_user_cannot_load_context_returns_403(
        self, client: FlaskClient, mock_context_load, fake_vclient
    ) -> None:
        """Verify a refused unlink for a user the API no longer serves returns 403."""
        # Given the unlink fails and the API refuses the user's context
        csrf = get_csrf(client)
        fake_vclient.set_error(Routes.USERS_IDENTITY_UNLINK, status_code=409, code="LAST_IDENTITY")
        mock_context_load.side_effect = AuthorizationError("deactivated", status_code=403)

        # When the unlink route is hit
        response = client.post("/auth/github/unlink", headers={"X-CSRFToken": csrf})

        # Then the request is refused
        assert response.status_code == 403

    def test_failure_when_user_missing_from_context_returns_404(
        self, client: FlaskClient, fake_vclient, mock_global_context: GlobalContext
    ) -> None:
        """Verify a refused unlink for a user absent from the company context returns 404."""
        # Given the unlink fails and the context no longer lists the user
        csrf = get_csrf(client)
        fake_vclient.set_error(Routes.USERS_IDENTITY_UNLINK, status_code=409, code="LAST_IDENTITY")
        mock_global_context.users = []

        # When the unlink route is hit
        response = client.post("/auth/github/unlink", headers={"X-CSRFToken": csrf})

        # Then the request 404s
        assert response.status_code == 404

    def test_unlink_rejects_logged_out_user(self, client: FlaskClient, fake_vclient) -> None:
        """Verify an unlink without an active session tells HTMX to go to the landing page."""
        # Given a valid CSRF token but a session with no logged-in user
        csrf = get_csrf(client)
        with client.session_transaction() as sess:
            sess.pop("user_id", None)
            sess.pop("company_id", None)

        # When the unlink route is hit
        response = client.post("/auth/github/unlink", headers={"X-CSRFToken": csrf})

        # Then HTMX is told to redirect to index and nothing reaches the API
        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/"
        fake_vclient.assert_not_called(Routes.USERS_IDENTITY_UNLINK)

    def test_unlink_unknown_provider_404s(self, client: FlaskClient) -> None:
        """Verify an unknown provider returns 404."""
        assert _post_unlink(client, provider="myspace").status_code == 404


class TestConnectionsCardRendering:
    """The connections card offers unlinking only while another sign-in method remains."""

    @pytest.mark.parametrize(
        ("linked", "expected_unlinkable"),
        [
            (["github", "google"], ["github", "google"]),
            (["github", "apple"], ["github", "apple"]),
            (["github"], []),
        ],
        ids=["two-providers", "apple-is-a-provider", "single-provider"],
    )
    def test_unlink_offered_only_with_another_sign_in_method(
        self, app: Flask, linked: list[str], expected_unlinkable: list[str]
    ) -> None:
        """Verify each linked provider can be removed unless it is the only sign-in method."""
        # Given a user linked to the listed providers
        profiles = {
            "discord": DiscordProfile(id="discord-1", username="someone"),
            "github": GitHubProfileFactory.build(),
            "google": GoogleProfileFactory.build(),
            "apple": AppleProfileFactory.build(),
        }
        user = UserFactory.build(
            id="test-user-id",
            discord_profile=profiles["discord"] if "discord" in linked else None,
            github_profile=profiles["github"] if "github" in linked else None,
            google_profile=profiles["google"] if "google" in linked else None,
            apple_profile=profiles["apple"] if "apple" in linked else None,
        )

        # When the card is rendered
        with app.test_request_context():
            html = catalog.render("profile.components.ConnectionsCard", user=user)

        # Then exactly the expected providers offer an unlink action
        unlinkable = [name for name in profiles if f"/auth/{name}/unlink" in html]
        assert unlinkable == expected_unlinkable

    def test_unlinked_apple_offers_connect(self, app: Flask) -> None:
        """Verify Apple offers a connect action when no Apple identity is linked."""
        user = UserFactory.build(
            id="test-user-id",
            github_profile=GitHubProfileFactory.build(),
            google_profile=GoogleProfileFactory.build(),
            discord_profile=None,
            apple_profile=None,
        )

        with app.test_request_context():
            html = catalog.render("profile.components.ConnectionsCard", user=user)

        assert "/auth/apple/link" in html
