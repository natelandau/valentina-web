"""Tests for the authentication guard before_request hooks."""

from __future__ import annotations

from unittest.mock import MagicMock

from vclient.testing import UserFactory

from vweb.lib.global_context import GlobalContext


class TestRequireAuth:
    """Tests for the require_auth before_request hook."""

    def test_unauthenticated_request_redirects_to_index(self, app) -> None:
        """Verify unauthenticated users are redirected to / from protected routes."""
        client = app.test_client()
        response = client.get("/characters/some-id")
        assert response.status_code == 302
        assert response.location == "/"

    def test_index_not_guarded(self, app) -> None:
        """Verify / is accessible without authentication."""
        client = app.test_client()
        response = client.get("/")
        assert response.status_code == 200

    def test_auth_routes_not_guarded(self, app, mocker) -> None:
        """Verify /auth/* routes are not redirected to /."""
        # Mock OAuth to avoid real Discord redirect
        mock_discord = MagicMock()
        mock_discord.authorize_redirect.return_value = MagicMock(status_code=302)
        mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)

        client = app.test_client()
        response = client.get("/auth/discord")
        # Should not redirect to / (it redirects to Discord instead)
        assert response.location != "/"

    def test_pending_approval_accessible_with_session(self, client) -> None:
        """Verify /pending-approval is accessible with an authenticated session."""
        response = client.get("/pending-approval")
        assert response.status_code == 200


class TestUnapprovedRedirect:
    """Tests for UNAPPROVED user redirection in inject_global_context."""

    def test_unapproved_user_redirected_to_pending(self, app, mocker) -> None:
        """Verify UNAPPROVED users are redirected to /pending-approval."""
        # Given an unapproved user in the global context
        unapproved_user = UserFactory.build(id="test-user-id", role="UNAPPROVED")
        unapproved_context = GlobalContext(
            company=MagicMock(),
            users=[unapproved_user],
            campaigns=[],
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=unapproved_context)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"

        # When accessing a protected route
        response = client.get("/characters/some-id")

        # Then redirected to pending-approval
        assert response.status_code == 302
        assert response.location == "/pending-approval"

    def test_unapproved_user_can_access_pending_page(self, app, mocker) -> None:
        """Verify UNAPPROVED users can access /pending-approval without redirect loop."""
        unapproved_user = UserFactory.build(id="test-user-id", role="UNAPPROVED")
        unapproved_context = GlobalContext(
            company=MagicMock(),
            users=[unapproved_user],
            campaigns=[],
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=unapproved_context)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"

        response = client.get("/pending-approval")
        assert response.status_code == 200

    def test_approved_user_can_access_routes(self, client) -> None:
        """Verify approved users are not blocked by the auth guard at /."""
        response = client.get("/")
        # Approved authenticated users are redirected to a campaign page, not blocked
        assert response.status_code in (200, 302)
        assert response.location != "/pending-approval"
