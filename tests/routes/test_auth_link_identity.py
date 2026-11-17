"""Tests for the account-linking (connections) OAuth flow."""

from unittest.mock import MagicMock

from vweb.api_client.testing import Routes


class TestLinkIdentityView:
    """Tests for GET /auth/<provider>/link."""

    def test_link_route_sets_flag_and_redirects_to_provider(self, client, mocker):
        """Verify the link route sets link mode and starts the provider OAuth flow."""
        # Given a mock OAuth github client
        mock_github = MagicMock()
        mock_github.authorize_redirect.return_value = MagicMock(status_code=302)
        mocker.patch("vweb.routes.auth.views_identity.oauth", github=mock_github)

        # When the link route is hit (client fixture is already logged in)
        client.get("/auth/github/link")

        # Then link mode is flagged and the OAuth redirect was issued
        with client.session_transaction() as sess:
            assert sess["oauth_link_mode"] is True
        mock_github.authorize_redirect.assert_called_once()

    def test_link_route_rejects_anonymous_user(self, app, mocker):
        """Verify the link route redirects anonymous visitors to the landing page."""
        # Given a configured provider and a client with no session
        mocker.patch("vweb.routes.auth.views_identity.oauth", github=MagicMock())
        anonymous_client = app.test_client()

        # When the link route is hit
        response = anonymous_client.get("/auth/github/link")

        # Then redirected to index without setting link mode
        assert response.status_code == 302
        assert response.location == "/"
        with anonymous_client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_route_unknown_provider_404s(self, client):
        """Verify an unknown provider returns 404."""
        # When linking an unknown provider
        response = client.get("/auth/myspace/link")

        # Then it 404s
        assert response.status_code == 404

    def test_link_route_unconfigured_provider_404s(self, client):
        """Verify a known provider this deployment did not configure returns 404."""
        # Given the test app registers no real OAuth clients (oauth.discord is absent)
        # When the link route is hit for that provider
        response = client.get("/auth/discord/link")

        # Then it 404s instead of raising AttributeError on oauth.discord
        assert response.status_code == 404

    def test_link_route_apple_sets_flag_and_redirects(self, client, mocker):
        """Verify linking Apple sets link mode and starts the OAuth flow."""
        # Given a mock OAuth apple client
        mock_apple = MagicMock()
        mock_apple.authorize_redirect.return_value = MagicMock(status_code=302)
        mocker.patch("vweb.routes.auth.views_identity.oauth", apple=mock_apple)

        # When the Apple link route is hit
        client.get("/auth/apple/link")

        # Then link mode is flagged and the OAuth redirect was issued (form_post is
        # set at registration, asserted in test_apple_oauth.py)
        with client.session_transaction() as sess:
            assert sess["oauth_link_mode"] is True
        mock_apple.authorize_redirect.assert_called_once()


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
        mocker.patch("vweb.routes.auth.views_oauth.oauth", github=mock_github)
        return mock_github

    def test_link_callback_links_identity_and_redirects_to_profile(
        self, client, mocker, fake_vclient
    ):
        """Verify a link-mode callback attaches the identity and returns to the profile."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then the identity was linked for the active company and cache invalidated
        (request,) = fake_vclient.assert_called(
            Routes.USERS_IDENTITY_LINK,
            params={"company_id": "test-company-id", "user_id": "test-user-id"},
            json={"provider": "github", "token": "gh-cred"},
            times=1,
        )
        assert request.headers["on-behalf-of"] == "test-user-id"
        mock_cache_clear.assert_called_once_with("test-company-id", "test-user-id")
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"

        # Then link mode is cleared
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_callback_conflict_flashes_error(self, client, mocker, fake_vclient):
        """Verify IDENTITY_ALREADY_LINKED is reported without breaking the session."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # Given the identity belongs to another user
        fake_vclient.set_error(
            Routes.USERS_IDENTITY_LINK, status_code=409, code="IDENTITY_ALREADY_LINKED"
        )
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected back to the profile, the session user is unchanged, and the
        # cached context is kept
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "test-user-id"
            assert "already linked to a different user" in str(sess["_flashes"])
        mock_cache_clear.assert_not_called()

    def test_link_callback_verification_failure_flashes_error(self, client, mocker, fake_vclient):
        """Verify TOKEN_VERIFICATION_FAILED during linking redirects to the profile."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # Given token verification fails
        fake_vclient.set_error(
            Routes.USERS_IDENTITY_LINK, status_code=422, code="TOKEN_VERIFICATION_FAILED"
        )

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected back to the profile with a verification error
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert "Could not verify your Github login" in str(sess["_flashes"])

    def test_link_callback_cancelled_oauth_redirects_to_profile(self, client, mocker):
        """Verify cancelling the provider consent screen returns to the profile."""
        from authlib.integrations.base_client.errors import OAuthError

        # Given a link-mode session where the provider raises an OAuth error
        self._arm_link_mode(client)
        mock_github = MagicMock()
        mock_github.authorize_access_token.side_effect = OAuthError(error="access_denied")
        mocker.patch("vweb.routes.auth.views_oauth.oauth", github=mock_github)

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then redirected to the profile with link mode cleared
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_callback_does_not_run_login_flow(self, client, mocker, fake_vclient):
        """Verify link mode skips lookup and identify entirely."""
        # Given a link-mode session and a mock OAuth flow
        self._arm_link_mode(client)
        self._mock_github_oauth(mocker)

        # When the callback is hit
        client.get("/auth/github/callback")

        # Then the identity was linked and the login lookup and identify never ran
        fake_vclient.assert_called(Routes.USERS_IDENTITY_LINK, times=1)
        fake_vclient.assert_not_called(Routes.USERS_LOOKUP)
        fake_vclient.assert_not_called(Routes.IDENTITY_IDENTIFY)

    def test_link_callback_apple_uses_id_token(self, client, mocker, fake_vclient):
        """Verify the Apple link callback (a form POST) links with the OIDC id_token."""
        # Given a link-mode session and an Apple OAuth flow returning an id_token
        self._arm_link_mode(client)
        mock_apple = MagicMock()
        mock_apple.authorize_access_token.return_value = {
            "id_token": "apple-id-tok",
            "userinfo": {"sub": "a1", "email": "e@e.com"},
        }
        mocker.patch("vweb.routes.auth.views_oauth.oauth", apple=mock_apple)
        mocker.patch(
            "vweb.routes.auth.views_oauth.build_apple_client_secret", return_value="secret"
        )
        mocker.patch("vweb.routes.auth.views_identity.cache.global_context.clear")

        # When the callback is POSTed
        response = client.post("/auth/apple/callback", data={"code": "abc", "state": "xyz"})

        # Then the identity was linked with the id_token and routed back to the profile
        fake_vclient.assert_called(
            Routes.USERS_IDENTITY_LINK,
            params={"user_id": "test-user-id"},
            json={"provider": "apple", "token": "apple-id-tok"},
            times=1,
        )
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    def test_link_callback_google_uses_id_token(self, client, mocker, fake_vclient):
        """Verify the Google link callback links with the OIDC id_token, not the access token."""
        # Given a link-mode session and a Google OAuth flow returning both token types
        self._arm_link_mode(client)
        mock_google = MagicMock()
        mock_google.authorize_access_token.return_value = {
            "access_token": "google-access-tok",
            "id_token": "google-id-tok",
            "userinfo": {"sub": "g1", "name": "u", "email": "e@e.com"},
        }
        mocker.patch("vweb.routes.auth.views_oauth.oauth", google=mock_google)
        mocker.patch("vweb.routes.auth.views_identity.cache.global_context.clear")

        # When the callback is hit
        response = client.get("/auth/google/callback")

        # Then the identity was linked with the id_token and routed back to the profile
        fake_vclient.assert_called(
            Routes.USERS_IDENTITY_LINK,
            params={"user_id": "test-user-id"},
            json={"provider": "google", "token": "google-id-tok"},
            times=1,
        )
        assert response.status_code == 302
        assert response.location == "/profile/test-user-id"
