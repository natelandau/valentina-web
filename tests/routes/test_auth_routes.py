"""Tests for the OAuth login routes: provider redirects, callbacks, and logout.

How a callback routes each set of verified memberships (single, multiple, unapproved,
deactivated) is covered in test_auth_routes_multi_company.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from authlib.integrations.base_client.errors import OAuthError

from tests.conftest import get_csrf
from tests.helpers import (
    assert_redirects_to,
    identify_resolving,
    mock_oauth_provider,
    session_flashes,
)
from vweb.api_client.exceptions import (
    ServerError,
    UnprocessableEntityError,
)
from vweb.api_client.models import IdentityResolution
from vweb.api_client.testing import Routes, UserFactory, UserLookupResultFactory

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

PROVIDERS = ["discord", "github", "google", "apple"]


def _hit_callback(client: FlaskClient, provider: str, data: dict | None = None) -> TestResponse:
    """Call a provider callback the way the provider does: Apple POSTs a form, others GET."""
    if provider == "apple":
        return client.post(
            "/auth/apple/callback", data={"code": "abc", "state": "xyz", **(data or {})}
        )
    return client.get(f"/auth/{provider}/callback")


def _mock_discord_login(
    mocker, *, email: str = "victim@example.com", verified: bool = True
) -> None:
    """Patch the Discord OAuth client to return a token and the given profile."""
    mock_oauth_provider(
        mocker,
        "discord",
        token={"access_token": "fake-token"},
        profile={
            "id": "new-discord-id",
            "username": "someone",
            "email": email,
            "verified": verified,
        },
    )


@pytest.mark.parametrize("provider", PROVIDERS)
def test_login_starts_provider_redirect_and_clears_stale_link_mode(
    client: FlaskClient, mocker, provider: str
) -> None:
    """Verify a login starts the provider redirect and drops a leftover link-mode flag.

    A stale flag from an abandoned "connect account" flow would make the shared callback
    link an identity instead of logging in.
    """
    # Given a stale link-mode flag
    with client.session_transaction() as sess:
        sess["oauth_link_mode"] = True
    mock = mock_oauth_provider(mocker, provider)
    mock.authorize_redirect.return_value = "to-provider"

    # When a fresh login is initiated
    client.get(f"/auth/{provider}")

    # Then the provider redirect is issued and the flag is gone
    mock.authorize_redirect.assert_called_once()
    with client.session_transaction() as sess:
        assert "oauth_link_mode" not in sess


class TestCallbackCredentials:
    """Each provider's callback looks up and verifies the user with the right credential."""

    @pytest.mark.parametrize(
        ("provider", "token", "profile", "lookup_query", "credential"),
        [
            (
                "discord",
                {"access_token": "discord-cred"},
                {"id": "d-1", "username": "u", "email": "e@e.com", "verified": True},
                {"discord_id": "d-1"},
                "discord-cred",
            ),
            (
                "github",
                {"access_token": "github-cred"},
                {"id": 123, "login": "u", "email": "e@e.com"},
                {"github_id": "123"},
                "github-cred",
            ),
            (
                "google",
                {
                    "access_token": "google-access",
                    "id_token": "google-oidc",
                    "userinfo": {"sub": "g-1", "email": "e@e.com", "email_verified": True},
                },
                None,
                {"google_id": "g-1"},
                "google-oidc",
            ),
            (
                "apple",
                {"id_token": "apple-oidc", "userinfo": {"sub": "a-1", "email": "e@e.com"}},
                None,
                {"apple_id": "a-1"},
                "apple-oidc",
            ),
        ],
    )
    def test_callback_verifies_provider_credential_and_signs_in(
        self,
        client: FlaskClient,
        mocker,
        fake_vclient,
        *,
        provider: str,
        token: dict,
        profile: dict | None,
        lookup_query: dict,
        credential: str,
    ) -> None:
        """Verify the callback looks up by provider id, verifies the credential, and signs in."""
        # Given a provider login for an existing approved user
        mock_oauth_provider(mocker, provider, token=token, profile=profile)
        fake_vclient.set_response(
            Routes.USERS_LOOKUP, items=[UserLookupResultFactory.build(company_id="comp-1")]
        )
        fake_vclient.set_response(
            Routes.IDENTITY_IDENTIFY,
            model=IdentityResolution(
                resolution="matched",
                user=UserFactory.build(id="resolved-user-id", company_id="comp-1"),
            ),
        )

        # When the provider calls back
        response = _hit_callback(client, provider)

        # Then the lookup used the provider id and the API verified the right credential
        fake_vclient.assert_called(Routes.USERS_LOOKUP, query=lookup_query)
        fake_vclient.assert_called(
            Routes.IDENTITY_IDENTIFY,
            params={"company_id": "comp-1"},
            json_subset={"provider": provider, "token": credential},
            times=1,
        )
        # And the user is signed in with a long-lived session
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "resolved-user-id"
            assert sess["company_id"] == "comp-1"
            assert sess.permanent is True

    def test_github_without_public_email_uses_primary_verified_email(
        self, client: FlaskClient, mocker, fake_vclient
    ) -> None:
        """Verify GitHub falls back to the primary verified address when /user has no email."""
        # Given a GitHub user with no public email and no account matching the GitHub id
        mock_github = mock_oauth_provider(mocker, "github", token={"access_token": "fake-token"})
        user_resp = MagicMock()
        user_resp.json.return_value = {"id": 999, "login": "noemail", "email": None}
        emails_resp = MagicMock()
        emails_resp.json.return_value = [
            {"email": "secondary@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]
        mock_github.get.side_effect = [user_resp, emails_resp]
        fake_vclient.set_response(Routes.USERS_LOOKUP, items=[])

        # When the callback is hit
        client.get("/auth/github/callback")

        # Then the email fallback lookup uses the primary verified address
        fake_vclient.assert_called(
            Routes.USERS_LOOKUP, query={"email": "primary@example.com"}, times=1
        )

    @pytest.mark.parametrize(
        ("provider", "token", "profile", "lookup_query"),
        [
            (
                "discord",
                {"access_token": "fake-token"},
                {"id": "d-1", "username": "u", "email": "victim@example.com", "verified": False},
                {"discord_id": "d-1"},
            ),
            (
                "google",
                {
                    "id_token": "fake-id-token",
                    "userinfo": {
                        "sub": "g-1",
                        "email": "victim@example.com",
                        "email_verified": False,
                    },
                },
                None,
                {"google_id": "g-1"},
            ),
        ],
    )
    def test_unverified_email_is_not_used_for_lookup(
        self,
        client: FlaskClient,
        mocker,
        fake_vclient,
        *,
        provider: str,
        token: dict,
        profile: dict | None,
        lookup_query: dict,
    ) -> None:
        """Verify an unverified provider email never reaches the email lookup fallback."""
        # Given a provider profile whose email is unverified and no user with that provider id
        mock_oauth_provider(mocker, provider, token=token, profile=profile)
        fake_vclient.set_response(Routes.USERS_LOOKUP, items=[])

        # When the callback completes
        client.get(f"/auth/{provider}/callback")

        # Then the lookup searched by provider id and never by email
        fake_vclient.assert_called(Routes.USERS_LOOKUP, query=lookup_query)
        fake_vclient.assert_not_called(Routes.USERS_LOOKUP, query={"email": "victim@example.com"})


class TestNewUserCallback:
    """A login that matches no account keeps the credential for registration."""

    def test_discord_new_user_keeps_credential_for_registration(
        self, client: FlaskClient, mocker
    ) -> None:
        """Verify a new user is sent to company selection with the credential and hints stored."""
        # Given a provider login with no existing accounts
        mock_oauth_provider(
            mocker,
            "discord",
            token={"access_token": "cred-456"},
            profile={"id": "n", "username": "newbie", "email": "n@e.com", "verified": True},
        )
        mocker.patch("vweb.routes.auth.views_oauth.lookup_user_companies", return_value=[])

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then the user picks companies next, and the pending payload carries the credential
        assert response.location == "/select-companies"
        with client.session_transaction() as sess:
            assert sess["pending_oauth"] == {
                "provider": "discord",
                "token": "cred-456",
                "username": "newbie",
                "email": "n@e.com",
            }

    def test_apple_new_user_name_comes_from_form_post(self, client: FlaskClient, mocker) -> None:
        """Verify a new Apple user's name comes from the form POST and the credential is the id_token."""
        # Given an Apple login with no existing accounts
        mock_oauth_provider(
            mocker,
            "apple",
            token={
                "id_token": "fake-id-token",
                "userinfo": {"sub": "apple-new", "email": "new@example.com"},
            },
        )
        mocker.patch("vweb.routes.auth.views_oauth.lookup_user_companies", return_value=[])

        # When Apple POSTs the callback, without a CSRF token, with the first-login name
        response = _hit_callback(
            client, "apple", {"user": '{"name": {"firstName": "Ada", "lastName": "Lovelace"}}'}
        )

        # Then the new user is sent to company selection with the verified id_token cached
        assert response.location == "/select-companies"
        with client.session_transaction() as sess:
            assert sess["pending_oauth"] == {
                "provider": "apple",
                "token": "fake-id-token",
                "username": "Ada Lovelace",
                "email": "new@example.com",
            }


class TestCallbackFailures:
    """A callback that cannot complete the login leaves the visitor signed out."""

    @pytest.fixture
    def logged_out(self, client: FlaskClient) -> FlaskClient:
        """Return the client with an empty session."""
        with client.session_transaction() as sess:
            sess.clear()
        return client

    @pytest.mark.parametrize("provider", PROVIDERS)
    @pytest.mark.parametrize(
        ("link_mode", "expected_location"),
        [(False, "/"), (True, "/profile/test-user-id")],
        ids=["login", "link"],
    )
    def test_cancelled_consent_returns_with_error(
        self,
        client: FlaskClient,
        mocker,
        provider: str,
        *,
        link_mode: bool,
        expected_location: str,
    ) -> None:
        """Verify a cancelled provider consent returns home, or to the profile when linking."""
        # Given the provider reports the user denied access
        with client.session_transaction() as sess:
            sess["oauth_link_mode"] = link_mode
        mock = mock_oauth_provider(mocker, provider, token={})
        mock.authorize_access_token.side_effect = OAuthError(error="access_denied")

        # When the provider calls back
        response = _hit_callback(client, provider)

        # Then the user lands on the right page with an error and link mode is cleared
        assert_redirects_to(response, expected_location)
        assert [category for category, _ in session_flashes(client)] == ["error"]
        with client.session_transaction() as sess:
            assert "oauth_link_mode" not in sess

    @pytest.mark.parametrize(
        ("provider", "token", "profile"),
        [
            ("discord", {"access_token": "t"}, {"id": "d-1", "verified": False}),
            ("github", {"access_token": "t"}, {"id": 1, "email": "e@e.com"}),
            ("google", {"id_token": "t", "userinfo": {"sub": "g-1"}}, None),
            ("apple", {"id_token": "t", "userinfo": {"sub": "a-1"}}, None),
        ],
    )
    def test_api_unreachable_during_lookup(
        self,
        logged_out: FlaskClient,
        mocker,
        provider: str,
        token: dict,
        profile: dict | None,
    ) -> None:
        """Verify an API failure during lookup returns home with an error and no session."""
        mock_oauth_provider(mocker, provider, token=token, profile=profile)
        mocker.patch(
            "vweb.routes.auth.views_oauth.lookup_user_companies",
            side_effect=ServerError("down", 500, {}),
        )

        response = _hit_callback(logged_out, provider)

        assert response.location == "/"
        assert [category for category, _ in session_flashes(logged_out)] == ["error"]
        with logged_out.session_transaction() as sess:
            assert "user_id" not in sess

    @pytest.mark.parametrize(
        "error",
        [
            UnprocessableEntityError("bad", 422, {"code": "TOKEN_VERIFICATION_FAILED"}),
            UnprocessableEntityError("bad", 422, {"code": "EMAIL_REQUIRED"}),
            ServerError("down", 503, {"code": "PROVIDER_UNAVAILABLE"}),
        ],
        ids=["token-verification-failed", "email-required", "provider-unavailable"],
    )
    def test_identify_failure_aborts_login(
        self, logged_out: FlaskClient, mocker, error: Exception
    ) -> None:
        """Verify a rejected credential aborts the login with an error and no session."""
        # Given an account match the API then refuses to verify
        _mock_discord_login(mocker)
        mocker.patch(
            "vweb.routes.auth.views_oauth.lookup_user_companies",
            return_value=[UserLookupResultFactory.build(user_id="other-user")],
        )
        mocker.patch("vweb.routes.auth.views_oauth.identify_in_companies", side_effect=error)

        # When the callback is hit
        response = logged_out.get("/auth/discord/callback")

        # Then login aborts to the index with an error and no session
        assert response.location == "/"
        assert [category for category, _ in session_flashes(logged_out)] == ["error"]
        with logged_out.session_transaction() as sess:
            assert "user_id" not in sess

    def test_no_session_when_identify_resolves_no_company(
        self, logged_out: FlaskClient, mocker
    ) -> None:
        """Verify login aborts when the credential is verified in no matched company."""
        # Given an email lookup match that identify() refuses in every company
        _mock_discord_login(mocker)
        mocker.patch(
            "vweb.routes.auth.views_oauth.lookup_user_companies",
            return_value=[UserLookupResultFactory.build(user_id="email-match-id")],
        )
        mocker.patch("vweb.routes.auth.views_oauth.identify_in_companies", return_value={})

        # When the callback completes
        response = logged_out.get("/auth/discord/callback")

        # Then no user is signed in
        assert response.location == "/"
        assert [category for category, _ in session_flashes(logged_out)] == ["error"]
        with logged_out.session_transaction() as sess:
            assert "user_id" not in sess


def test_session_binds_to_verified_user_not_lookup_match(client: FlaskClient, mocker) -> None:
    """Verify the session binds to the user identify() resolved when it differs from lookup."""
    # Given an email lookup that matched an existing user
    _mock_discord_login(mocker)
    mocker.patch(
        "vweb.routes.auth.views_oauth.lookup_user_companies",
        return_value=[UserLookupResultFactory.build(company_id="comp-1", user_id="email-match-id")],
    )
    # And identify() resolving the credential to a different, newly created user
    created = IdentityResolution(
        resolution="created",
        user=UserFactory.build(id="created-id", role="UNAPPROVED", company_id="comp-1"),
    )
    mocker.patch(
        "vweb.routes.auth.views_oauth.identify_in_companies", return_value={"comp-1": created}
    )

    # When the callback completes
    response = client.get("/auth/discord/callback")

    # Then the session belongs to the verified user, not the email match
    with client.session_transaction() as sess:
        assert sess["user_id"] == "created-id"
    assert response.location == "/pending-approval"


def test_identify_runs_in_every_matched_company(client: FlaskClient, mocker) -> None:
    """Verify login verifies the credential in every company the lookup matched."""
    _mock_discord_login(mocker)
    results = [
        UserLookupResultFactory.build(company_id="c1", user_id="u1"),
        UserLookupResultFactory.build(company_id="c2", user_id="u2", role="ADMIN"),
    ]
    mocker.patch("vweb.routes.auth.views_oauth.lookup_user_companies", return_value=results)
    mock_identify = mocker.patch(
        "vweb.routes.auth.views_oauth.identify_in_companies",
        return_value=identify_resolving(results),
    )

    client.get("/auth/discord/callback")

    mock_identify.assert_called_once_with(["c1", "c2"], provider="discord", token="fake-token")


@pytest.mark.usefixtures("fake_vclient")
def test_logout_clears_session(client: FlaskClient) -> None:
    """Verify POST /auth/logout clears the session and redirects to the index."""
    response = client.post("/auth/logout", headers={"X-CSRFToken": get_csrf(client)})

    assert_redirects_to(response, "/")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
