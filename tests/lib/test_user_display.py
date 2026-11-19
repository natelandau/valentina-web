"""Tests for the user_display_name helper."""

from __future__ import annotations

from typing import Any

import pytest

from vweb.api_client.models.users import AppleProfile, DiscordProfile, GitHubProfile
from vweb.api_client.testing import UserFactory
from vweb.lib.user_display import user_display_name


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param({"name_first": "Ada", "name_last": "Lovelace"}, "Ada Lovelace", id="full"),
        pytest.param({"name_first": "Ada"}, "Ada", id="first-only"),
        pytest.param({"name_last": "Lovelace"}, "Lovelace", id="last-only"),
        pytest.param(
            {"apple_profile": AppleProfile(id="a1", fullname="Ada Apple")},
            "Ada Apple",
            id="apple",
        ),
        pytest.param(
            {"apple_profile": AppleProfile(id="a1", fullname=None)}, "ada", id="empty-apple"
        ),
        pytest.param(
            {"discord_profile": DiscordProfile(id="d1", username="x", global_name="Ada D")},
            "Ada D",
            id="discord",
        ),
        pytest.param(
            {"github_profile": GitHubProfile(id="g1", login="x", username="Ada G")},
            "Ada G",
            id="github",
        ),
        pytest.param({}, "ada", id="username"),
    ],
)
def test_display_name_fallback(fields: dict[str, Any], expected: str) -> None:
    """Verify the name chain: top-level names, then provider profiles, then username."""
    base: dict[str, Any] = {
        "name_first": None,
        "name_last": None,
        "username": "ada",
        "apple_profile": None,
        "discord_profile": None,
        "github_profile": None,
    }
    user = UserFactory.build(**(base | fields))

    assert user_display_name(user) == expected


def test_output_is_html_escaped() -> None:
    """Verify attacker-controlled provider names cannot inject markup or attributes."""
    user = UserFactory.build(
        name_first=None,
        name_last=None,
        username="eve",
        discord_profile=None,
        github_profile=None,
        apple_profile=AppleProfile(id="a1", fullname='Eve" hx-get="/evil><script>'),
    )

    result = user_display_name(user)

    assert '"' not in result
    assert "<" not in result
    assert ">" not in result
    assert "Eve" in result
