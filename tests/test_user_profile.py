"""Tests for user profile display helpers."""

from __future__ import annotations

from vclient.models.users import DiscordProfile, GitHubProfile
from vclient.testing import UserFactory

from vweb.lib.user_profile import has_custom_avatar, user_avatar_url


def test_has_custom_avatar_true_for_uploaded_url() -> None:
    """Verify a resolved URL that matches no provider is treated as custom."""
    # Given a user whose avatar_url differs from the Discord provider URL
    user = UserFactory.build(
        avatar_url="https://cdn.example.com/custom.webp",
        discord_profile=DiscordProfile(id="d1", avatar_url="https://discord/avatar.png"),
        google_profile=None,
        github_profile=None,
    )

    # When checking for a custom avatar
    # Then it is custom
    assert has_custom_avatar(user) is True


def test_has_custom_avatar_false_when_matches_provider() -> None:
    """Verify a resolved URL equal to a provider URL is not custom."""
    # Given a user whose avatar_url is the Discord provider URL
    user = UserFactory.build(
        avatar_url="https://discord/avatar.png",
        discord_profile=DiscordProfile(id="d1", avatar_url="https://discord/avatar.png"),
        google_profile=None,
        github_profile=None,
    )

    # When checking for a custom avatar
    # Then it is not custom
    assert has_custom_avatar(user) is False


def test_has_custom_avatar_false_when_no_avatar() -> None:
    """Verify no avatar_url means no custom avatar."""
    # Given a user with no resolved avatar
    user = UserFactory.build(
        avatar_url=None, discord_profile=None, google_profile=None, github_profile=None
    )

    # When checking for a custom avatar
    # Then it is not custom
    assert has_custom_avatar(user) is False


def test_user_avatar_url_prefers_resolved_url() -> None:
    """Verify the API-resolved avatar_url wins over provider profiles."""
    # Given a user with a resolved avatar_url and a GitHub avatar
    user = UserFactory.build(
        avatar_url="https://cdn.example.com/custom.webp",
        github_profile=GitHubProfile(id="g1", avatar_url="https://github/avatar.png"),
        google_profile=None,
    )

    # When resolving the avatar URL
    # Then the resolved URL is returned
    assert user_avatar_url(user) == "https://cdn.example.com/custom.webp"


def test_user_avatar_url_falls_back_to_github() -> None:
    """Verify the GitHub avatar is used when avatar_url is unset."""
    # Given a user with only a GitHub avatar
    user = UserFactory.build(
        avatar_url=None,
        discord_profile=None,
        github_profile=GitHubProfile(id="g1", avatar_url="https://github/avatar.png"),
        google_profile=None,
    )

    # When resolving the avatar URL
    # Then the GitHub avatar is returned
    assert user_avatar_url(user) == "https://github/avatar.png"


def test_user_avatar_url_none_when_no_avatar() -> None:
    """Verify None is returned when no avatar source exists."""
    # Given a user with no avatar sources
    user = UserFactory.build(
        avatar_url=None, discord_profile=None, github_profile=None, google_profile=None
    )

    # When resolving the avatar URL
    # Then None is returned so callers render a placeholder
    assert user_avatar_url(user) is None
