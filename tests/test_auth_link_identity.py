"""Tests for the account-linking (connections) OAuth flow."""

from unittest.mock import MagicMock

from vclient.exceptions import ConflictError, UnprocessableEntityError


class TestLinkIdentityView:
    """Tests for GET /auth/<provider>/link."""

    def test_link_route_sets_flag_and_redirects_to_provider(self, client, mocker):
        """Verify the link route sets link mode and starts the provider OAuth flow."""
        # Given a mock OAuth github client
        mock_github = MagicMock()
        mock_github.authorize_redirect.return_value = MagicMock(status_code=302)
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # When the link route is hit (client fixture is already logged in)
        client.get("/auth/github/link")

        # Then link mode is flagged and the OAuth redirect was issued
        with client.session_transaction() as sess:
            assert sess["oauth_link_mode"] is True
        mock_github.authorize_redirect.assert_called_once()

    def test_link_route_rejects_anonymous_user(self, app, mocker):
        """Verify the link route redirects anonymous visitors to the landing page."""
        # Given a client with no session
        anonymous_client = app.test_client()

        # When the link route is hit
        response = anonymous_client.get("/auth/github/link")

        # Then redirected to index without setting link mode
        assert response.status_code == 302
        assert response.location == "/"
        with anonymous_client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_route_unknown_provider_404s(self, client):
        """Verify an unconfigured provider returns 404."""
        # When linking an unknown provider
        response = client.get("/auth/myspace/link")

        # Then it 404s
        assert response.status_code == 404


class TestLinkModeCallback:
    """Tests for OAuth callbacks in link mode."""

    def _arm_link_mode(self, client) -> None:
        """Flag the session as a link-mode OAuth flow."""
        with client.session_transaction() as sess:
            sess["oauth_link_mode"] = True

    def _mock_github_oauth(self, mocker) -> MagicMock:
        """Mock the GitHub OAuth client returning a valid token."""
        mock_github = MagicMock()
        mock_github.authorize_access_token.return_value = {"access_token": "gh-cred"}
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)
        return mock_github

    def test_link_callback_links_identity_and_redirects_to_profile(self, client, mocker):
        """Verify a link-mode callback attaches the identity and returns to the profile."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # Given a users service that links successfully
        mock_users_svc = MagicMock()
        mocker.patch("vweb.routes.auth.views.sync_users_service", return_value=mock_users_svc)
        mock_cache_clear = mocker.patch("vweb.routes.auth.views.cache.global_context.clear")

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then the identity was linked for the active company and cache invalidated
        mock_users_svc.link_identity.assert_called_once_with(
            "test-user-id", provider="github", token="gh-cred"
        )
        mock_cache_clear.assert_called_once_with("test-company-id", "test-user-id")
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"

        # Then link mode is cleared
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_callback_conflict_flashes_error(self, client, mocker):
        """Verify IDENTITY_ALREADY_LINKED is reported without breaking the session."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # Given the identity belongs to another user
        mock_users_svc = MagicMock()
        mock_users_svc.link_identity.side_effect = ConflictError(
            "conflict", 409, {"code": "IDENTITY_ALREADY_LINKED"}
        )
        mocker.patch("vweb.routes.auth.views.sync_users_service", return_value=mock_users_svc)

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected back to the profile and the session user is unchanged
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "test-user-id"

    def test_link_callback_verification_failure_flashes_error(self, client, mocker):
        """Verify TOKEN_VERIFICATION_FAILED during linking redirects to the profile."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # Given token verification fails
        mock_users_svc = MagicMock()
        mock_users_svc.link_identity.side_effect = UnprocessableEntityError(
            "bad", 422, {"code": "TOKEN_VERIFICATION_FAILED"}
        )
        mocker.patch("vweb.routes.auth.views.sync_users_service", return_value=mock_users_svc)

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected back to the profile
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"

    def test_link_callback_cancelled_oauth_redirects_to_profile(self, client, mocker):
        """Verify cancelling the provider consent screen returns to the profile."""
        from authlib.integrations.base_client.errors import OAuthError

        # Given a link-mode session where the provider raises an OAuth error
        self._arm_link_mode(client)
        mock_github = MagicMock()
        mock_github.authorize_access_token.side_effect = OAuthError(error="access_denied")
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected to the profile with link mode cleared
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_callback_does_not_run_login_flow(self, client, mocker):
        """Verify link mode skips lookup and identify entirely."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)
        mocker.patch("vweb.routes.auth.views.sync_users_service", return_value=MagicMock())
        mock_lookup = mocker.patch("vweb.routes.auth.views.lookup_user_companies")

        # When the callback is hit
        client.get("/auth/github/callback")

        # Then the login lookup never ran
        mock_lookup.assert_not_called()

    def test_link_callback_google_uses_id_token(self, client, mocker):
        """Verify the Google link callback links with the OIDC id_token, not the access token."""
        # Given a link-mode session and a Google OAuth flow returning both token types
        self._arm_link_mode(client)
        mock_google = MagicMock()
        mock_google.authorize_access_token.return_value = {
            "access_token": "google-access-tok",
            "id_token": "google-id-tok",
            "userinfo": {"sub": "g1", "name": "u", "email": "e@e.com"},
        }
        mocker.patch("vweb.routes.auth.views.oauth", google=mock_google)
        mock_users_svc = MagicMock()
        mocker.patch("vweb.routes.auth.views.sync_users_service", return_value=mock_users_svc)
        mocker.patch("vweb.routes.auth.views.cache.global_context.clear")

        # When the callback is hit
        response = client.get("/auth/google/callback")

        # Then the identity was linked with the id_token and routed back to the profile
        mock_users_svc.link_identity.assert_called_once_with(
            "test-user-id", provider="google", token="google-id-tok"
        )
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
