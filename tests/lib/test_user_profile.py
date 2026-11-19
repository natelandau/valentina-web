"""Tests for user profile display helpers."""

from __future__ import annotations

from typing import Any

import pytest

from vweb.api_client.models.users import DiscordProfile, GitHubProfile
from vweb.api_client.testing import UserFactory
from vweb.lib.user_profile import has_custom_avatar, user_avatar_url

_DISCORD = DiscordProfile(id="d1", avatar_url="https://discord/avatar.png")
_GITHUB = GitHubProfile(id="g1", avatar_url="https://github/avatar.png")
_CUSTOM = "https://cdn.example.com/custom.webp"


def _user(avatar_url: str | None, **profiles: Any):  # noqa: ANN202
    defaults: dict[str, Any] = {
        "discord_profile": None,
        "github_profile": None,
        "google_profile": None,
    }
    return UserFactory.build(avatar_url=avatar_url, **(defaults | profiles))


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        pytest.param(_user(_CUSTOM, discord_profile=_DISCORD), True, id="uploaded"),
        pytest.param(
            _user("https://discord/avatar.png", discord_profile=_DISCORD), False, id="provider"
        ),
        pytest.param(_user(None), False, id="none"),
    ],
)
def test_has_custom_avatar(user, *, expected: bool) -> None:
    """Verify an avatar counts as custom only when it matches no provider's avatar."""
    assert has_custom_avatar(user) is expected


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        pytest.param(_user(_CUSTOM, github_profile=_GITHUB), _CUSTOM, id="resolved-wins"),
        pytest.param(_user(None, github_profile=_GITHUB), _GITHUB.avatar_url, id="github"),
        pytest.param(_user(None), None, id="none"),
    ],
)
def test_user_avatar_url(user, expected: str | None) -> None:
    """Verify the API-resolved avatar wins, then a provider avatar, else None for a placeholder."""
    assert user_avatar_url(user) == expected
