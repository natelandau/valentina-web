"""Tests for the account-unlinking (connections) flow."""

from werkzeug.test import TestResponse

from tests.conftest import get_csrf
from vweb.api_client.testing import (
    AppleProfileFactory,
    GitHubProfileFactory,
    GoogleProfileFactory,
    Routes,
    UserFactory,
)
from vweb.lib.catalog import catalog


class TestUnlinkIdentityView:
    """Tests for POST /auth/<provider>/unlink."""

    def _post_unlink(self, client, provider: str = "github") -> TestResponse:
        """POST the unlink route with a valid CSRF header, as HTMX would."""
        return client.post(
            f"/auth/{provider}/unlink",
            headers={"X-CSRFToken": get_csrf(client)},
        )

    def test_unlink_disconnects_identity_and_returns_card(self, client, mocker, fake_vclient):
        """Verify unlinking removes the provider, clears cache, and swaps the card in."""
        # Given an unlink endpoint that succeeds
        fake_vclient.set_response(
            Routes.USERS_IDENTITY_UNLINK, model=UserFactory.build(id="test-user-id")
        )
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the unlink route is hit
        response = self._post_unlink(client)

        # Then the identity was unlinked, cache invalidated, and the card returned
        (request,) = fake_vclient.assert_called(
            Routes.USERS_IDENTITY_UNLINK,
            params={
                "company_id": "test-company-id",
                "user_id": "test-user-id",
                "provider": "github",
            },
            times=1,
        )
        assert request.headers["on-behalf-of"] == "test-user-id"
        mock_cache_clear.assert_called_once_with("test-company-id", "test-user-id")
        assert response.status_code == 200
        assert b'id="connections-card"' in response.data

    def test_unlink_last_identity_conflict_returns_card_without_clearing_cache(
        self, client, mocker, fake_vclient
    ):
        """Verify LAST_IDENTITY is reported and the card returns unchanged."""
        # Given the provider is the user's only sign-in method
        fake_vclient.set_error(Routes.USERS_IDENTITY_UNLINK, status_code=409, code="LAST_IDENTITY")
        mock_cache_clear = mocker.patch(
            "vweb.routes.auth.views_identity.cache.global_context.clear"
        )

        # When the unlink route is hit
        response = self._post_unlink(client)

        # Then the card comes back and the cache is left untouched
        assert response.status_code == 200
        assert b'id="connections-card"' in response.data
        assert b"only sign-in method" in response.data
        mock_cache_clear.assert_not_called()

    def test_unlink_not_found_returns_card(self, client, fake_vclient):
        """Verify unlinking a provider that is not connected returns the card."""
        # Given the provider has no linked identity
        fake_vclient.set_error(
            Routes.USERS_IDENTITY_UNLINK, status_code=404, code="IDENTITY_NOT_LINKED"
        )

        # When the unlink route is hit
        response = self._post_unlink(client)

        # Then the card is returned without error
        assert response.status_code == 200
        assert b'id="connections-card"' in response.data
        assert b"is not connected to your account" in response.data

    def test_unlink_authorization_error_returns_card(self, client, fake_vclient):
        """Verify a denied unlink returns the card rather than crashing."""
        # Given the acting user is not permitted to unlink
        fake_vclient.set_error(Routes.USERS_IDENTITY_UNLINK, status_code=403)

        # When the unlink route is hit
        response = self._post_unlink(client)

        # Then the card is returned
        assert response.status_code == 200
        assert b'id="connections-card"' in response.data
        assert b"not allowed to change these connections" in response.data

    def test_unlink_rejects_logged_out_user(self, client):
        """Verify an unlink request without an active session redirects to the landing page."""
        # Given a valid CSRF token but a session with no logged-in user
        csrf = get_csrf(client)
        with client.session_transaction() as sess:
            sess.pop("user_id", None)
            sess.pop("company_id", None)

        # When the unlink route is hit
        response = client.post("/auth/github/unlink", headers={"X-CSRFToken": csrf})

        # Then HTMX is told to redirect to index
        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/"

    def test_unlink_unknown_provider_404s(self, client):
        """Verify an unknown provider returns 404."""
        # When unlinking an unknown provider
        response = self._post_unlink(client, provider="myspace")

        # Then it 404s
        assert response.status_code == 404

    def test_unlink_apple_disconnects_identity_and_returns_card(self, client, mocker, fake_vclient):
        """Verify Apple can be disconnected like the other providers."""
        # Given an unlink endpoint that succeeds
        fake_vclient.set_response(
            Routes.USERS_IDENTITY_UNLINK, model=UserFactory.build(id="test-user-id")
        )
        mocker.patch("vweb.routes.auth.views_identity.cache.global_context.clear")

        # When the Apple unlink route is hit
        response = self._post_unlink(client, provider="apple")

        # Then the Apple identity was unlinked and the card returned
        fake_vclient.assert_called(
            Routes.USERS_IDENTITY_UNLINK,
            params={"user_id": "test-user-id", "provider": "apple"},
            times=1,
        )
        assert response.status_code == 200
        assert b'id="connections-card"' in response.data


class TestConnectionsCardRendering:
    """Tests for the Disconnect button visibility in the connections card."""

    def _render_card(self, app, user) -> str:
        """Render the connections card for a user within an app request context."""
        with app.test_request_context():
            return catalog.render("profile.components.ConnectionsCard", user=user)

    def test_disconnect_button_shown_when_multiple_providers_linked(self, app):
        """Verify a Disconnect button renders for each provider when more than one is linked."""
        # Given a user linked to two providers
        user = UserFactory.build(
            id="test-user-id",
            github_profile=GitHubProfileFactory.build(),
            google_profile=GoogleProfileFactory.build(),
            discord_profile=None,
        )

        # When the card is rendered
        html = self._render_card(app, user)

        # Then both linked providers expose an unlink action
        assert "Disconnect" in html
        assert "/auth/github/unlink" in html
        assert "/auth/google/unlink" in html

    def test_disconnect_button_hidden_when_single_provider_linked(self, app):
        """Verify no Disconnect button renders when only one provider is linked."""
        # Given a user linked to a single provider
        user = UserFactory.build(
            id="test-user-id",
            github_profile=GitHubProfileFactory.build(),
            google_profile=None,
            discord_profile=None,
        )

        # When the card is rendered
        html = self._render_card(app, user)

        # Then the last sign-in method cannot be removed
        assert "Disconnect" not in html
        assert "/unlink" not in html

    def test_apple_is_a_first_class_connection_row(self, app):
        """Verify Apple renders as its own connection with a disconnect action."""
        # Given a user linked to GitHub plus Apple
        user = UserFactory.build(
            id="test-user-id",
            github_profile=GitHubProfileFactory.build(),
            google_profile=None,
            discord_profile=None,
            apple_profile=AppleProfileFactory.build(),
        )

        # When the card is rendered
        html = self._render_card(app, user)

        # Then both providers, including Apple, expose an unlink action
        assert "/auth/github/unlink" in html
        assert "/auth/apple/unlink" in html

    def test_apple_row_shows_connect_when_not_linked(self, app):
        """Verify Apple offers a Connect action when no Apple identity is linked."""
        # Given a user with other providers linked but no Apple identity
        user = UserFactory.build(
            id="test-user-id",
            github_profile=GitHubProfileFactory.build(),
            google_profile=GoogleProfileFactory.build(),
            discord_profile=None,
            apple_profile=None,
        )

        # When the card is rendered
        html = self._render_card(app, user)

        # Then Apple can be connected from the web
        assert "/auth/apple/link" in html
