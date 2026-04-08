"""Tests for auth service user resolution."""

from __future__ import annotations

from vclient.models.users import DiscordProfile, GitHubProfile, GoogleProfile
from vclient.testing import Routes, UserFactory

from vweb.routes.auth.services import (
    resolve_or_create_discord_user,
    resolve_or_create_github_user,
    resolve_or_create_google_user,
)

GOOGLE_DATA = {
    "sub": "google-123",
    "email": "test@example.com",
    "email_verified": True,
    "name": "Test User",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://lh3.googleusercontent.com/a/test",
    "locale": "en",
}

GITHUB_DATA = {
    "id": 12345,
    "login": "testuser",
    "name": "Test User",
    "email": "test@example.com",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "html_url": "https://github.com/testuser",
}

DISCORD_DATA = {
    "id": "discord-123",
    "username": "testuser",
    "global_name": "Test User",
    "email": "test@example.com",
    "verified": True,
    "avatar": "abc123",
    "discriminator": "0",
}


class TestResolveOrCreateUser:
    """Tests for resolve_or_create_discord_user()."""

    def test_resolve_by_discord_profile_id(self, app, fake_vclient) -> None:
        """Verify resolution matches on discord_profile.id."""
        # Given a user whose discord_profile.id matches the OAuth data
        existing = UserFactory.build(
            id="u1",
            discord_profile=DiscordProfile(id="discord-123", username="old-name"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_discord_user(DISCORD_DATA)

        # Then the existing user is returned (after update)
        assert result.id == "u1"

    def test_resolve_by_discord_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on discord_profile.email when no ID match."""
        # Given a user whose discord_profile.email matches but ID does not
        existing = UserFactory.build(
            id="u2",
            discord_profile=DiscordProfile(id="other-id", email="test@example.com"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u2")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_discord_user(DISCORD_DATA)

        # Then the user matched by discord email is returned
        assert result.id == "u2"

    def test_resolve_by_user_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on top-level user email when no discord profile match."""
        # Given a user whose top-level email matches but has no discord profile match
        existing = UserFactory.build(
            id="u3",
            email="test@example.com",
            discord_profile=None,
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u3")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_discord_user(DISCORD_DATA)

        # Then the user matched by email is returned
        assert result.id == "u3"

    def test_register_new_user_when_no_match(self, app, fake_vclient) -> None:
        """Verify a new user is registered when no match found."""
        # Given no existing users match the Discord data
        fake_vclient.set_response(Routes.USERS_LIST, items=[])
        new_user = UserFactory.build(id="new-id", role="UNAPPROVED")
        fake_vclient.set_response(Routes.USERS_REGISTER, model=new_user)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_discord_user(DISCORD_DATA)

        # Then a new user is registered and returned
        assert result.id == "new-id"

    def test_discord_profile_updated_on_login(self, app, fake_vclient, mocker) -> None:
        """Verify the user's discord_profile is updated with fresh data on every login."""
        # Given an existing user matched by discord ID
        existing = UserFactory.build(
            id="u1",
            discord_profile=DiscordProfile(id="discord-123", username="old-name"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        spy = mocker.patch("vweb.routes.auth.services.sync_users_service", wraps=None)
        mock_svc = spy.return_value

        # Re-set list and update on the mock
        mock_svc.list_all.return_value = [existing]
        mock_svc.update.return_value = updated

        with app.test_request_context():
            resolve_or_create_discord_user(DISCORD_DATA)

        # Then the update API is called with fresh discord profile data
        mock_svc.update.assert_called_once()
        call_kwargs = mock_svc.update.call_args
        assert call_kwargs[0][0] == "u1"  # user_id positional arg
        update_request = call_kwargs[1]["request"]
        assert update_request.discord_profile.id == "discord-123"
        assert update_request.discord_profile.username == "testuser"
        assert update_request.discord_profile.global_name == "Test User"
        assert update_request.discord_profile.avatar_id == "abc123"
        assert update_request.discord_profile.email == "test@example.com"
        assert update_request.requesting_user_id == "u1"


class TestResolveOrCreateGitHubUser:
    """Tests for resolve_or_create_github_user()."""

    def test_resolve_by_github_profile_id(self, app, fake_vclient) -> None:
        """Verify resolution matches on github_profile.id."""
        # Given a user whose github_profile.id matches the OAuth data
        existing = UserFactory.build(
            id="u1",
            github_profile=GitHubProfile(id="12345", login="old-login"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_github_user(GITHUB_DATA)

        # Then the existing user is returned (after update)
        assert result.id == "u1"

    def test_resolve_by_github_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on github_profile.email when no ID match."""
        # Given a user whose github_profile.email matches but ID does not
        existing = UserFactory.build(
            id="u2",
            github_profile=GitHubProfile(id="other-id", email="test@example.com"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u2")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_github_user(GITHUB_DATA)

        # Then the user matched by github email is returned
        assert result.id == "u2"

    def test_resolve_by_user_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on top-level user email when no github profile match."""
        # Given a user whose top-level email matches but has no github profile match
        existing = UserFactory.build(
            id="u3",
            email="test@example.com",
            github_profile=None,
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u3")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_github_user(GITHUB_DATA)

        # Then the user matched by email is returned
        assert result.id == "u3"

    def test_register_new_user_when_no_match(self, app, fake_vclient) -> None:
        """Verify a new user is registered when no match found."""
        # Given no existing users match the GitHub data
        fake_vclient.set_response(Routes.USERS_LIST, items=[])
        new_user = UserFactory.build(id="new-id", role="UNAPPROVED")
        fake_vclient.set_response(Routes.USERS_REGISTER, model=new_user)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_github_user(GITHUB_DATA)

        # Then a new user is registered and returned
        assert result.id == "new-id"

    def test_github_profile_updated_on_login(self, app, fake_vclient, mocker) -> None:
        """Verify the user's github_profile is updated with fresh data on every login."""
        # Given an existing user matched by github ID
        existing = UserFactory.build(
            id="u1",
            github_profile=GitHubProfile(id="12345", login="old-login"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        spy = mocker.patch("vweb.routes.auth.services.sync_users_service", wraps=None)
        mock_svc = spy.return_value

        # Re-set list and update on the mock
        mock_svc.list_all.return_value = [existing]
        mock_svc.update.return_value = updated

        with app.test_request_context():
            resolve_or_create_github_user(GITHUB_DATA)

        # Then the update API is called with fresh github profile data
        mock_svc.update.assert_called_once()
        call_kwargs = mock_svc.update.call_args
        assert call_kwargs[0][0] == "u1"
        update_request = call_kwargs[1]["request"]
        assert update_request.github_profile.id == "12345"
        assert update_request.github_profile.login == "testuser"
        assert update_request.github_profile.email == "test@example.com"
        assert update_request.requesting_user_id == "u1"


class TestResolveOrCreateGoogleUser:
    """Tests for resolve_or_create_google_user()."""

    def test_resolve_by_google_profile_id(self, app, fake_vclient) -> None:
        """Verify resolution matches on google_profile.id."""
        # Given a user whose google_profile.id matches the OAuth data
        existing = UserFactory.build(
            id="u1",
            google_profile=GoogleProfile(id="google-123", email="old@example.com"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_google_user(GOOGLE_DATA)

        # Then the existing user is returned (after update)
        assert result.id == "u1"

    def test_resolve_by_google_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on google_profile.email when no ID match."""
        # Given a user whose google_profile.email matches but ID does not
        existing = UserFactory.build(
            id="u2",
            google_profile=GoogleProfile(id="other-id", email="test@example.com"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u2")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_google_user(GOOGLE_DATA)

        # Then the user matched by google email is returned
        assert result.id == "u2"

    def test_resolve_by_user_email(self, app, fake_vclient) -> None:
        """Verify resolution matches on top-level user email when no google profile match."""
        # Given a user whose top-level email matches but has no google profile match
        existing = UserFactory.build(
            id="u3",
            email="test@example.com",
            google_profile=None,
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u3")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_google_user(GOOGLE_DATA)

        # Then the user matched by email is returned
        assert result.id == "u3"

    def test_register_new_user_when_no_match(self, app, fake_vclient) -> None:
        """Verify a new user is registered when no match found."""
        # Given no existing users match the Google data
        fake_vclient.set_response(Routes.USERS_LIST, items=[])
        new_user = UserFactory.build(id="new-id", role="UNAPPROVED")
        fake_vclient.set_response(Routes.USERS_REGISTER, model=new_user)

        # When resolving the user
        with app.test_request_context():
            result = resolve_or_create_google_user(GOOGLE_DATA)

        # Then a new user is registered and returned
        assert result.id == "new-id"

    def test_google_profile_updated_on_login(self, app, fake_vclient, mocker) -> None:
        """Verify the user's google_profile is updated with fresh data on every login."""
        # Given an existing user matched by google ID
        existing = UserFactory.build(
            id="u1",
            google_profile=GoogleProfile(id="google-123", email="old@example.com"),
        )
        fake_vclient.set_response(Routes.USERS_LIST, items=[existing])
        updated = UserFactory.build(id="u1")
        fake_vclient.set_response(Routes.USERS_UPDATE, model=updated)

        # When resolving the user
        spy = mocker.patch("vweb.routes.auth.services.sync_users_service", wraps=None)
        mock_svc = spy.return_value

        # Re-set list and update on the mock
        mock_svc.list_all.return_value = [existing]
        mock_svc.update.return_value = updated

        with app.test_request_context():
            resolve_or_create_google_user(GOOGLE_DATA)

        # Then the update API is called with fresh google profile data
        mock_svc.update.assert_called_once()
        call_kwargs = mock_svc.update.call_args
        assert call_kwargs[0][0] == "u1"
        update_request = call_kwargs[1]["request"]
        assert update_request.google_profile.id == "google-123"
        assert update_request.google_profile.email == "test@example.com"
        assert update_request.google_profile.name_first == "Test"
        assert update_request.google_profile.name_last == "User"
        assert (
            update_request.google_profile.avatar_url == "https://lh3.googleusercontent.com/a/test"
        )
        assert update_request.requesting_user_id == "u1"
