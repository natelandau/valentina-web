"""Tests for the authentication guard before_request hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import assert_redirects_to, mock_oauth_provider, session_flashes
from vweb.api_client.exceptions import AuthorizationError

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient, TestResponse

PROTECTED_PATH = "/characters/some-id"


def _client_with_session_role(app: Flask, role: str) -> FlaskClient:
    """Build a client whose session says the user holds `role` in the test company."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
        sess["company_id"] = "test-company-id"
        sess["companies"] = {
            "test-company-id": {"user_id": "test-user-id", "company_name": "Test", "role": role},
        }
    return client


def _assert_sent_to(response: TestResponse, path: str, *, htmx: bool) -> None:
    """Assert a full-page redirect, or an HX-Redirect for htmx so the browser navigates."""
    if htmx:
        # A 302 under hx-boost is followed by fetch and swapped into the page.
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == path
    else:
        assert_redirects_to(response, path)


class TestRequireAuth:
    """Tests for the require_auth before_request hook."""

    @pytest.mark.parametrize("htmx", [False, True], ids=["page", "htmx"])
    def test_unauthenticated_request_sent_to_index(self, app: Flask, *, htmx: bool) -> None:
        """Verify anonymous visitors to a protected route are sent to the landing page."""
        headers = {"HX-Request": "true"} if htmx else {}

        response = app.test_client().get(PROTECTED_PATH, headers=headers)

        _assert_sent_to(response, "/", htmx=htmx)

    def test_index_is_public(self, app: Flask) -> None:
        """Verify / is reachable without authentication."""
        assert app.test_client().get("/").status_code == 200

    def test_auth_routes_are_public(self, app: Flask, mocker) -> None:
        """Verify /auth/* routes are not redirected to the landing page."""
        mock_discord = mock_oauth_provider(mocker, "discord")
        mock_discord.authorize_redirect.return_value = "to-discord"

        response = app.test_client().get("/auth/discord")

        assert response.status_code == 200
        mock_discord.authorize_redirect.assert_called_once()


class TestUnapprovedUser:
    """UNAPPROVED users may only reach /pending-approval."""

    @pytest.mark.parametrize("htmx", [False, True], ids=["page", "htmx"])
    def test_protected_route_sends_to_pending_approval(
        self, app: Flask, use_context, *, htmx: bool
    ) -> None:
        """Verify an UNAPPROVED user is sent to /pending-approval from a protected route."""
        use_context(user_role="UNAPPROVED", campaigns=[])
        client = _client_with_session_role(app, "UNAPPROVED")
        headers = {"HX-Request": "true"} if htmx else {}

        response = client.get(PROTECTED_PATH, headers=headers)

        _assert_sent_to(response, "/pending-approval", htmx=htmx)

    def test_pending_page_is_reachable(self, app: Flask, use_context) -> None:
        """Verify an UNAPPROVED user can load /pending-approval without a redirect loop."""
        use_context(user_role="UNAPPROVED", campaigns=[])
        client = _client_with_session_role(app, "UNAPPROVED")

        assert client.get("/pending-approval").status_code == 200

    def test_api_refusal_keeps_session_and_sends_to_pending(
        self, app: Flask, mock_context_load
    ) -> None:
        """Verify an UNAPPROVED user the API refuses goes to /pending-approval, signed in."""
        mock_context_load.side_effect = AuthorizationError(
            "User has not been approved yet", status_code=403
        )
        client = _client_with_session_role(app, "UNAPPROVED")

        response = client.get("/")

        _assert_sent_to(response, "/pending-approval", htmx=False)
        with client.session_transaction() as sess:
            assert sess["user_id"] == "test-user-id"


class TestRevokedMember:
    """Approved session users who lost access are signed out."""

    def test_api_refusal_signs_out_with_error(self, app: Flask, mock_context_load) -> None:
        """Verify a session user the API now refuses is signed out with an error message."""
        mock_context_load.side_effect = AuthorizationError(
            "User account is deactivated", status_code=403
        )
        client = _client_with_session_role(app, "PLAYER")

        response = client.get(PROTECTED_PATH, headers={"HX-Request": "true"})

        _assert_sent_to(response, "/", htmx=True)
        with client.session_transaction() as sess:
            assert "user_id" not in sess
        assert [cat for cat, _ in session_flashes(client)] == ["error"]

    def test_deactivated_in_cached_context_signs_out(self, app: Flask, use_context) -> None:
        """Verify a user listed as DEACTIVATED in a cached context is signed out."""
        use_context(user_role="DEACTIVATED", campaigns=[])
        client = _client_with_session_role(app, "PLAYER")

        response = client.get(PROTECTED_PATH)

        _assert_sent_to(response, "/", htmx=False)
        with client.session_transaction() as sess:
            assert "user_id" not in sess
