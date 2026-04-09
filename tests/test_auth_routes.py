"""Tests for auth route blueprint."""

from unittest.mock import MagicMock

from vclient.models import UserLookupResult


def _make_lookup_result(**kwargs) -> UserLookupResult:
    """Build a UserLookupResult with sensible defaults."""
    defaults = {
        "company_id": "comp-1",
        "company_name": "Test Company",
        "user_id": "resolved-user-id",
        "role": "PLAYER",
    }
    defaults.update(kwargs)
    return UserLookupResult(**defaults)


class TestDiscordLoginView:
    """Tests for the Discord login redirect route."""

    def test_discord_login_redirects(self, client, mocker):
        """Verify GET /auth/discord triggers an OAuth redirect."""
        # Given a mock OAuth discord client
        mock_redirect_response = MagicMock(
            status_code=302, headers={"Location": "https://discord.com/oauth2/authorize"}
        )
        mock_discord = MagicMock()
        mock_discord.authorize_redirect.return_value = mock_redirect_response
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        # When the login route is hit
        client.get("/auth/discord")

        # Then it delegates to authlib's authorize_redirect
        mock_discord.authorize_redirect.assert_called_once()


class TestDiscordCallbackView:
    """Tests for the Discord OAuth callback route."""

    def test_callback_sets_session_for_approved_user(self, client, mocker):
        """Verify Discord callback sets session and redirects for approved user."""
        # Given a mock OAuth flow returning a valid token and discord profile
        mock_token = {"access_token": "fake-token"}
        mock_discord = MagicMock()
        mock_discord.authorize_access_token.return_value = mock_token
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "123",
            "username": "testuser",
            "email": "test@example.com",
        }
        mock_discord.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        # Given a single approved lookup result
        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_discord_profile")

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then session has user_id and response redirects to /
        with client.session_transaction() as sess:
            assert sess["user_id"] == "resolved-user-id"
            assert sess["company_id"] == "comp-1"
        assert response.status_code == 302
        assert response.location == "/"

    def test_callback_redirects_unapproved_to_pending(self, client, mocker):
        """Verify Discord callback redirects unapproved user to pending approval."""
        # Given a mock OAuth flow
        mock_token = {"access_token": "fake-token"}
        mock_discord = MagicMock()
        mock_discord.authorize_access_token.return_value = mock_token
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "456",
            "username": "newuser",
            "email": "new@example.com",
        }
        mock_discord.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        # Given a single unapproved lookup result
        result = _make_lookup_result(user_id="unapproved-user-id", role="UNAPPROVED")
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then session has user_id and response redirects to pending approval
        with client.session_transaction() as sess:
            assert sess["user_id"] == "unapproved-user-id"
        assert response.status_code == 302
        assert response.location == "/pending-approval"

    def test_callback_sets_session_permanent(self, client, mocker):
        """Verify Discord callback marks session as permanent for long-lived sessions."""
        # Given a mock OAuth flow
        mock_discord = MagicMock()
        mock_discord.authorize_access_token.return_value = {"access_token": "fake"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "789", "username": "u", "email": "e@e.com"}
        mock_discord.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_discord_profile")

        # When the callback is hit
        client.get("/auth/discord/callback")

        # Then the session is marked as permanent
        with client.session_transaction() as sess:
            assert sess.permanent is True

    def test_callback_new_user_redirects_to_select_companies(self, client, mocker):
        """Verify Discord callback redirects new users to company selection."""
        # Given a mock OAuth flow
        mock_discord = MagicMock()
        mock_discord.authorize_access_token.return_value = {"access_token": "fake"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "new", "username": "u", "email": "e@e.com"}
        mock_discord.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        # Given no lookup results (new user)
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[],
        )

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then redirect to select-companies with pending_oauth in session
        assert response.status_code == 302
        assert response.location == "/select-companies"
        with client.session_transaction() as sess:
            assert sess["pending_oauth"]["provider"] == "discord"


class TestGitHubLoginView:
    """Tests for the GitHub login redirect route."""

    def test_github_login_redirects(self, client, mocker):
        """Verify GET /auth/github triggers an OAuth redirect."""
        # Given a mock OAuth github client
        mock_redirect_response = MagicMock(
            status_code=302, headers={"Location": "https://github.com/login/oauth/authorize"}
        )
        mock_github = MagicMock()
        mock_github.authorize_redirect.return_value = mock_redirect_response
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # When the login route is hit
        client.get("/auth/github")

        # Then it delegates to authlib's authorize_redirect
        mock_github.authorize_redirect.assert_called_once()


class TestGitHubCallbackView:
    """Tests for the GitHub OAuth callback route."""

    def test_callback_sets_session_for_approved_user(self, client, mocker):
        """Verify GitHub callback sets session and redirects for approved user."""
        # Given a mock OAuth flow returning a valid token and github profile
        mock_token = {"access_token": "fake-token"}
        mock_github = MagicMock()
        mock_github.authorize_access_token.return_value = mock_token
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 123,
            "login": "testuser",
            "email": "test@example.com",
        }
        mock_github.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # Given a single approved lookup result
        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_github_profile")

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then session has user_id and response redirects to /
        with client.session_transaction() as sess:
            assert sess["user_id"] == "resolved-user-id"
        assert response.status_code == 302
        assert response.location == "/"

    def test_callback_redirects_unapproved_to_pending(self, client, mocker):
        """Verify GitHub callback redirects unapproved user to pending approval."""
        # Given a mock OAuth flow
        mock_token = {"access_token": "fake-token"}
        mock_github = MagicMock()
        mock_github.authorize_access_token.return_value = mock_token
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 456,
            "login": "newuser",
            "email": "new@example.com",
        }
        mock_github.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # Given a single unapproved lookup result
        result = _make_lookup_result(user_id="unapproved-user-id", role="UNAPPROVED")
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )

        # When the callback is hit
        response = client.get("/auth/github/callback")

        # Then session has user_id and response redirects to pending approval
        with client.session_transaction() as sess:
            assert sess["user_id"] == "unapproved-user-id"
        assert response.status_code == 302
        assert response.location == "/pending-approval"

    def test_callback_sets_session_permanent(self, client, mocker):
        """Verify GitHub callback marks session as permanent for long-lived sessions."""
        # Given a mock OAuth flow
        mock_github = MagicMock()
        mock_github.authorize_access_token.return_value = {"access_token": "fake"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 789, "login": "u", "email": "e@e.com"}
        mock_github.get.return_value = mock_resp
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_github_profile")

        # When the callback is hit
        client.get("/auth/github/callback")

        # Then the session is marked as permanent
        with client.session_transaction() as sess:
            assert sess.permanent is True

    def test_callback_fetches_email_from_emails_endpoint(self, client, mocker):
        """Verify GitHub callback fetches email from /user/emails when /user returns null."""
        # Given a mock OAuth flow where /user returns null email
        mock_token = {"access_token": "fake-token"}
        mock_github = MagicMock()
        mock_github.authorize_access_token.return_value = mock_token

        user_resp = MagicMock()
        user_resp.json.return_value = {"id": 999, "login": "noemail", "email": None}
        emails_resp = MagicMock()
        emails_resp.json.return_value = [
            {"email": "secondary@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]
        mock_github.get.side_effect = [user_resp, emails_resp]
        mocker.patch("vweb.routes.auth.views.oauth", github=mock_github)

        # Given a single approved lookup result
        result = _make_lookup_result()
        mock_lookup = mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_github_profile")

        # When the callback is hit
        client.get("/auth/github/callback")

        # Then lookup is called with the primary verified email populated
        call_kwargs = mock_lookup.call_args[1]
        assert call_kwargs["email"] == "primary@example.com"


class TestGoogleLoginView:
    """Tests for the Google login redirect route."""

    def test_google_login_redirects(self, client, mocker):
        """Verify GET /auth/google triggers an OAuth redirect."""
        # Given a mock OAuth google client
        mock_redirect_response = MagicMock(
            status_code=302,
            headers={"Location": "https://accounts.google.com/o/oauth2/v2/auth"},
        )
        mock_google = MagicMock()
        mock_google.authorize_redirect.return_value = mock_redirect_response
        mocker.patch("vweb.routes.auth.views.oauth", google=mock_google)

        # When the login route is hit
        client.get("/auth/google")

        # Then it delegates to authlib's authorize_redirect
        mock_google.authorize_redirect.assert_called_once()


class TestGoogleCallbackView:
    """Tests for the Google OAuth callback route."""

    def test_callback_sets_session_for_approved_user(self, client, mocker):
        """Verify Google callback sets session and redirects for approved user."""
        # Given a mock OAuth flow returning a token with embedded userinfo
        mock_token = {
            "access_token": "fake-token",
            "userinfo": {
                "sub": "123",
                "name": "Test User",
                "email": "test@example.com",
            },
        }
        mock_google = MagicMock()
        mock_google.authorize_access_token.return_value = mock_token
        mocker.patch("vweb.routes.auth.views.oauth", google=mock_google)

        # Given a single approved lookup result
        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_google_profile")

        # When the callback is hit
        response = client.get("/auth/google/callback")

        # Then session has user_id and response redirects to /
        with client.session_transaction() as sess:
            assert sess["user_id"] == "resolved-user-id"
        assert response.status_code == 302
        assert response.location == "/"

    def test_callback_redirects_unapproved_to_pending(self, client, mocker):
        """Verify Google callback redirects unapproved user to pending approval."""
        # Given a mock OAuth flow returning a token with embedded userinfo
        mock_token = {
            "access_token": "fake-token",
            "userinfo": {
                "sub": "456",
                "name": "New User",
                "email": "new@example.com",
            },
        }
        mock_google = MagicMock()
        mock_google.authorize_access_token.return_value = mock_token
        mocker.patch("vweb.routes.auth.views.oauth", google=mock_google)

        # Given a single unapproved lookup result
        result = _make_lookup_result(user_id="unapproved-user-id", role="UNAPPROVED")
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )

        # When the callback is hit
        response = client.get("/auth/google/callback")

        # Then session has user_id and response redirects to pending approval
        with client.session_transaction() as sess:
            assert sess["user_id"] == "unapproved-user-id"
        assert response.status_code == 302
        assert response.location == "/pending-approval"

    def test_callback_sets_session_permanent(self, client, mocker):
        """Verify Google callback marks session as permanent for long-lived sessions."""
        # Given a mock OAuth flow returning a token with embedded userinfo
        mock_google = MagicMock()
        mock_google.authorize_access_token.return_value = {
            "access_token": "fake",
            "userinfo": {"sub": "789", "name": "u", "email": "e@e.com"},
        }
        mocker.patch("vweb.routes.auth.views.oauth", google=mock_google)

        result = _make_lookup_result()
        mocker.patch(
            "vweb.routes.auth.views.lookup_user_companies",
            return_value=[result],
        )
        mocker.patch("vweb.routes.auth.views.update_google_profile")

        # When the callback is hit
        client.get("/auth/google/callback")

        # Then the session is marked as permanent
        with client.session_transaction() as sess:
            assert sess.permanent is True


class TestLogoutView:
    """Tests for the logout route."""

    def test_logout_clears_session(self, client, mocker):
        """Verify POST /auth/logout clears session and redirects to index."""
        # Given a session with a user_id
        with client.session_transaction() as sess:
            assert sess.get("user_id") is not None

        # Given a valid CSRF token (mock profile API call triggered by get_csrf)
        mock_svc = MagicMock()
        mock_svc.get_statistics.return_value = MagicMock()
        mocker.patch("vweb.routes.profile.views.sync_users_service", return_value=mock_svc)

        from tests.conftest import get_csrf

        csrf_token = get_csrf(client)

        # When the logout endpoint is hit
        response = client.post(
            "/auth/logout",
            headers={"X-CSRFToken": csrf_token},
        )

        # Then the session is cleared and response redirects to /
        with client.session_transaction() as sess:
            assert "user_id" not in sess
        assert response.status_code == 302
        assert response.location == "/"


class TestPendingApprovalView:
    """Tests for the pending approval page."""

    def test_pending_approval_renders(self, client):
        """Verify GET /pending-approval returns 200."""
        # When the pending approval page is requested
        response = client.get("/pending-approval")

        # Then it renders successfully
        assert response.status_code == 200
