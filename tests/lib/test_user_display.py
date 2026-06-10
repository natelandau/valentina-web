"""Tests for the user_display_name helper."""

from __future__ import annotations

from vclient.models.users import AppleProfile, DiscordProfile, GitHubProfile
from vclient.testing import UserFactory

from vweb.lib.user_display import user_display_name


class TestUserDisplayName:
    """Resolve a human-friendly display name across provider profiles."""

    def test_full_name_preferred(self) -> None:
        """Verify first + last name wins when both are set."""
        user = UserFactory.build(name_first="Ada", name_last="Lovelace", username="ada")

        assert user_display_name(user) == "Ada Lovelace"

    def test_partial_name_used_without_none(self) -> None:
        """Verify a lone first or last name renders without a literal 'None'."""
        first_only = UserFactory.build(name_first="Ada", name_last=None, username="ada")
        last_only = UserFactory.build(name_first=None, name_last="Lovelace", username="ada")

        assert user_display_name(first_only) == "Ada"
        assert user_display_name(last_only) == "Lovelace"

    def test_apple_fullname_fallback(self) -> None:
        """Verify apple_profile.fullname is used when top-level names are missing."""
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="relay-user",
            apple_profile=AppleProfile(id="apple-1", fullname="Ada Lovelace"),
        )

        assert user_display_name(user) == "Ada Lovelace"

    def test_username_fallback(self) -> None:
        """Verify username is the last resort when no names exist anywhere."""
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="ada",
            apple_profile=None,
        )

        assert user_display_name(user) == "ada"

    def test_empty_apple_fullname_skipped(self) -> None:
        """Verify an apple profile without a fullname falls through to username."""
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="ada",
            apple_profile=AppleProfile(id="apple-1", fullname=None),
        )

        assert user_display_name(user) == "ada"

    def test_discord_global_name_fallback(self) -> None:
        """Verify discord global_name is used when top-level names are missing."""
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="xx_gamer_42",
            discord_profile=DiscordProfile(id="d1", username="xx_gamer_42", global_name="Ada L"),
        )

        assert user_display_name(user) == "Ada L"

    def test_github_profile_name_fallback(self) -> None:
        """Verify the github profile display name is used when top-level names are missing."""
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="adacoder",
            github_profile=GitHubProfile(id="g1", login="adacoder", username="Ada Lovelace"),
        )

        assert user_display_name(user) == "Ada Lovelace"

    def test_output_is_html_escaped(self) -> None:
        """Verify attacker-controlled provider names cannot inject markup or attributes."""
        # Given a malicious apple fullname (JinjaX renders without autoescaping)
        user = UserFactory.build(
            name_first=None,
            name_last=None,
            username="eve",
            apple_profile=AppleProfile(id="a1", fullname='Eve" hx-get="/evil><script>'),
        )

        # When resolving the display name
        result = user_display_name(user)

        # Then quotes and angle brackets are escaped
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "Eve" in result
