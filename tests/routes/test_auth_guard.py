"""Tests for the authentication guard before_request hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from vclient.exceptions import AuthorizationError
from vclient.testing import UserFactory

from vweb.lib.cache.global_context import GlobalContext

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient


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
        mocker.patch("vweb.routes.auth.views_oauth.oauth", discord=mock_discord)

        client = app.test_client()
        response = client.get("/auth/discord")
        # Should not redirect to / (it redirects to Discord instead)
        assert response.location != "/"

    def test_pending_approval_accessible_with_session(self, client) -> None:
        """Verify /pending-approval is accessible with an authenticated session."""
        response = client.get("/pending-approval")
        assert response.status_code == 200

    def test_htmx_request_gets_hx_redirect_instead_of_302(self, app) -> None:
        """Verify htmx requests to protected routes get HX-Redirect, not a 302.

        A 302 under hx-boost would be silently followed by fetch and the landing
        page would be swapped into the boosted region. Returning HX-Redirect lets
        htmx trigger a full browser navigation instead.
        """
        client = app.test_client()
        response = client.get("/characters/some-id", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/"


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
        mocker.patch("vweb.lib.cache.global_context.load", return_value=unapproved_context)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"
            sess["company_id"] = "test-company-id"
            sess["companies"] = {
                "test-company-id": {
                    "user_id": "test-user-id",
                    "company_name": "Test",
                    "role": "UNAPPROVED",
                },
            }

        # When accessing a protected route
        response = client.get("/characters/some-id")

        # Then redirected to pending-approval
        assert response.status_code == 302
        assert response.location == "/pending-approval"

    def test_unapproved_htmx_request_gets_hx_redirect(self, app, mocker) -> None:
        """Verify UNAPPROVED htmx requests get HX-Redirect instead of 302."""
        unapproved_user = UserFactory.build(id="test-user-id", role="UNAPPROVED")
        unapproved_context = GlobalContext(
            company=MagicMock(),
            users=[unapproved_user],
            campaigns=[],
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=unapproved_context)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"
            sess["company_id"] = "test-company-id"
            sess["companies"] = {
                "test-company-id": {
                    "user_id": "test-user-id",
                    "company_name": "Test",
                    "role": "UNAPPROVED",
                },
            }

        response = client.get("/characters/some-id", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/pending-approval"

    def test_unapproved_user_can_access_pending_page(self, app, mocker) -> None:
        """Verify UNAPPROVED users can access /pending-approval without redirect loop."""
        unapproved_user = UserFactory.build(id="test-user-id", role="UNAPPROVED")
        unapproved_context = GlobalContext(
            company=MagicMock(),
            users=[unapproved_user],
            campaigns=[],
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=unapproved_context)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"
            sess["company_id"] = "test-company-id"
            sess["companies"] = {
                "test-company-id": {
                    "user_id": "test-user-id",
                    "company_name": "Test",
                    "role": "UNAPPROVED",
                },
            }

        response = client.get("/pending-approval")
        assert response.status_code == 200

    def test_approved_user_can_access_routes(self, client) -> None:
        """Verify approved users are not blocked by the auth guard at /."""
        response = client.get("/")
        # Approved authenticated users are redirected to a campaign page, not blocked
        assert response.status_code in (200, 302)
        assert response.location != "/pending-approval"


class TestApiRefusedMember:
    """Tests for session users the API refuses to act for (403 on the context load)."""

    @staticmethod
    def _client_with_session_role(app: Flask, role: str) -> FlaskClient:
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "test-user-id"
            sess["company_id"] = "test-company-id"
            sess["companies"] = {
                "test-company-id": {
                    "user_id": "test-user-id",
                    "company_name": "Test",
                    "role": role,
                },
            }
        return client

    def test_unapproved_user_is_sent_to_pending_approval(self, app, mocker) -> None:
        """Verify an UNAPPROVED session user goes to /pending-approval instead of a 500."""
        # Given the API refuses to load context for the user
        mocker.patch(
            "vweb.lib.cache.global_context.load",
            side_effect=AuthorizationError("User has not been approved yet", status_code=403),
        )
        client = self._client_with_session_role(app, "UNAPPROVED")

        # When visiting the index
        response = client.get("/")

        # Then the user is redirected to pending-approval and keeps the session
        assert response.status_code == 302
        assert response.location == "/pending-approval"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "test-user-id"

    def test_refused_active_session_user_is_signed_out(self, app, mocker) -> None:
        """Verify a session user deactivated after login is signed out with a message."""
        # Given a session that still says PLAYER but an API that refuses the user
        mocker.patch(
            "vweb.lib.cache.global_context.load",
            side_effect=AuthorizationError("User account is deactivated", status_code=403),
        )
        client = self._client_with_session_role(app, "PLAYER")

        # When visiting a protected page with htmx
        response = client.get("/characters/some-id", headers={"HX-Request": "true"})

        # Then the session is cleared and htmx navigates to the index
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/"
        with client.session_transaction() as sess:
            assert "user_id" not in sess
            assert any("no longer access" in message for _, message in sess["_flashes"])

    def test_deactivated_user_in_cached_context_is_signed_out(self, app, mocker) -> None:
        """Verify a user listed as DEACTIVATED in a cached context is signed out."""
        # Given a cached context that lists the session user as DEACTIVATED
        deactivated_context = GlobalContext(
            company=MagicMock(),
            users=[UserFactory.build(id="test-user-id", role="DEACTIVATED")],
            campaigns=[],
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=deactivated_context)
        client = self._client_with_session_role(app, "PLAYER")

        # When visiting a protected page
        response = client.get("/characters/some-id")

        # Then the session is cleared and the user lands on the index
        assert response.status_code == 302
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert "user_id" not in sess
