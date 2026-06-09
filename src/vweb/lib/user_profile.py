"""Display helpers for user profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vclient.models import User


def has_custom_avatar(user: User) -> bool:
    """Report whether the user has uploaded a custom avatar.

    The public ``User`` model exposes only the resolved ``avatar_url`` (custom
    upload then Discord then none) with no custom-avatar flag, so a custom
    avatar is inferred when ``avatar_url`` is set and matches none of the
    provider URLs.
    """
    if not user.avatar_url:
        return False

    provider_urls = {
        profile.avatar_url
        for profile in (user.discord_profile, user.google_profile, user.github_profile)
        if profile is not None and getattr(profile, "avatar_url", None)
    }
    return user.avatar_url not in provider_urls
