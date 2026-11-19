"""Tests for the account-linking (connections) OAuth flow.

A cancelled consent screen during linking is covered in test_auth_routes.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import mock_oauth_provider, session_flashes
from vweb.api_client.testing import Routes

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse


class TestLinkIdentityView:
    """Tests for GET /auth/<provider>/link."""

    @pytest.mark.parametrize("provider", ["discord", "github", "google", "apple"])
    def test_sets_link_mode_and_redirects_to_provider(
        self, client: FlaskClient, mocker, provider: str
    ) -> None:
        """Verify the link route flags link mode and starts the provider OAuth flow."""
        mock = mock_oauth_provider(mocker, provider, module="vweb.routes.auth.views_identity")
        mock.authorize_redirect.return_value = "to-provider"

        client.get(f"/auth/{provider}/link")

        with client.session_transaction() as sess:
            assert sess["oauth_link_mode"] is True
        mock.authorize_redirect.assert_called_once()

    @pytest.mark.parametrize("missing", ["user_id", "company_id"])
    def test_rejects_visitor_without_active_membership(
        self, client: FlaskClient, mocker, missing: str
    ) -> None:
        """Verify linking needs a signed-in user and an active company."""
        # Given a configured provider and a session missing the user or company
        mock_github = mock_oauth_provider(
            mocker, "github", module="vweb.routes.auth.views_identity"
        )
        with client.session_transaction() as sess:
            sess.pop(missing)

        # When the link route is hit
        response = client.get("/auth/github/link")

        # Then redirected to index without starting the flow
        assert response.location == "/"
        mock_github.authorize_redirect.assert_not_called()
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    @pytest.mark.parametrize(
        "provider",
        ["myspace", "discord"],
        ids=["unknown-provider", "unconfigured-provider"],
    )
    def test_unavailable_provider_404s(self, client: FlaskClient, provider: str) -> None:
        """Verify unknown providers and ones this deployment did not configure return 404."""
        # The test app registers no real OAuth clients, so discord is unconfigured
        assert client.get(f"/auth/{provider}/link").status_code == 404


def _arm_link_mode(client: FlaskClient) -> None:
    """Flag the session as a link-mode OAuth flow."""
    with client.session_transaction() as sess:
        sess["oauth_link_mode"] = True


def _github_link_callback(client: FlaskClient, mocker) -> TestResponse:
    """Complete a link-mode GitHub callback that returns a valid token."""
    _arm_link_mode(client)
    mock_oauth_provider(mocker, "github", token={"access_token": "gh-cred"})
    return client.get("/auth/github/callback")


class TestLinkModeCallback:
    """Tests for OAuth callbacks in link mode."""

    @pytest.mark.parametrize(
        ("provider", "token", "credential"),
        [
            ("discord", {"access_token": "discord-cred"}, "discord-cred"),
            ("github", {"access_token": "gh-cred"}, "gh-cred"),
            (
                "google",
                {"access_token": "google-access", "id_token": "google-id-tok"},
                "google-id-tok",
            ),
            ("apple", {"id_token": "apple-id-tok"}, "apple-id-tok"),
        ],
    )
    def test_links_identity_with_provider_credential(
        self,
        client: FlaskClient,
        mocker,
        fake_vclient,
        *,
        provider: str,
        token: dict,
        credential: str,
    ) -> None:
        """Verify a link-mode callback links the verified credential and returns to the profile."""
        # Given a link-mode session and a provider returning a token
        _arm_link_mode(client)
        mock_oauth_provider(mocker, provider, token=token)
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the provider calls back (Apple as a form POST)
        if provider == "apple":
            response = client.post("/auth/apple/callback", data={"code": "abc"})
        else:
            response = client.get(f"/auth/{provider}/callback")

        # Then the identity is linked for the active company on behalf of the user
        (request,) = fake_vclient.assert_called(
            Routes.USERS_IDENTITY_LINK,
            params={"company_id": "test-company-id", "user_id": "test-user-id"},
            json={"provider": provider, "token": credential},
            times=1,
        )
        assert request.headers["on-behalf-of"] == "test-user-id"
        # And the login flow never runs
        fake_vclient.assert_not_called(Routes.USERS_LOOKUP)
        fake_vclient.assert_not_called(Routes.IDENTITY_IDENTIFY)
        # And the cached context refreshes and the user returns to their profile
        mock_cache_clear.assert_called_once_with("test-company-id", "test-user-id")
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess
        assert [category for category, _ in session_flashes(client)] == ["success"]

    @pytest.mark.parametrize(
        ("status_code", "code"),
        [
            (409, "IDENTITY_ALREADY_LINKED"),
            (422, "TOKEN_VERIFICATION_FAILED"),
            (503, "PROVIDER_UNAVAILABLE"),
            (503, None),
            (404, None),
        ],
        ids=[
            "already-linked",
            "verification-failed",
            "provider-unavailable",
            "server-error",
            "other-api-error",
        ],
    )
    def test_link_failure_returns_to_profile_with_error(
        self, client: FlaskClient, mocker, fake_vclient, status_code: int, code: str | None
    ) -> None:
        """Verify a failed link keeps the session user and cached context, and reports an error."""
        # Given the API refuses the link
        fake_vclient.set_error(Routes.USERS_IDENTITY_LINK, status_code=status_code, code=code)
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the link-mode callback is hit
        response = _github_link_callback(client, mocker)

        # Then the user returns to their profile, unchanged, with an error
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "test-user-id"
        assert [category for category, _ in session_flashes(client)] == ["error"]
        mock_cache_clear.assert_not_called()

    def test_link_without_session_user_returns_home(
        self, client: FlaskClient, mocker, fake_vclient
    ) -> None:
        """Verify a link-mode callback after the session lost its user links nothing."""
        with client.session_transaction() as sess:
            sess.pop("user_id")

        response = _github_link_callback(client, mocker)

        assert response.location == "/"
        fake_vclient.assert_not_called(Routes.USERS_IDENTITY_LINK)
