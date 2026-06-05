"""Resolve human-friendly display names for users."""

from __future__ import annotations

from typing import TYPE_CHECKING

from markupsafe import escape

if TYPE_CHECKING:
    from vclient.models.users import User


def user_display_name(user: User) -> str:
    """Resolve the friendliest available display name for a user.

    Registration only populates the top-level name fields for Google sign-ins, so the
    provider profiles are consulted for the human name the other providers supply:
    Apple's single ``fullname`` string, Discord's ``global_name``, and the GitHub /
    Google profile ``username`` fields (which hold the account's display name, not the
    login handle). Guarding every field also prevents templates from rendering a
    literal "None".

    The result is HTML-escaped: provider names are attacker-controlled free text and
    the JinjaX catalog renders without autoescaping, so escaping here keeps every
    template call site (text nodes and attributes like ``hx-confirm``) safe.

    Args:
        user: The user to resolve a display name for.

    Returns:
        str: HTML-safe display name; top-level names first, then the provider-profile
            name, then the username.
    """
    name_parts = [part for part in (user.name_first, user.name_last) if part]
    if name_parts:
        return escape(" ".join(name_parts))

    profile_names = (
        user.apple_profile.fullname if user.apple_profile else None,
        user.discord_profile.global_name if user.discord_profile else None,
        user.github_profile.username if user.github_profile else None,
        user.google_profile.username if user.google_profile else None,
    )
    for profile_name in profile_names:
        if profile_name:
            return escape(profile_name)

    return escape(user.username)
