"""Tests for user profile display helpers."""

from __future__ import annotations

from vclient.models.users import DiscordProfile
from vclient.testing import UserFactory

from vweb.lib.user_profile import has_custom_avatar


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
