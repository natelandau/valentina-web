"""Auth service for OAuth user resolution (Discord, GitHub, Google)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import abort, flash, redirect, url_for
from vclient import sync_users_service
from vclient.models.users import (
    DiscordProfileUpdate,
    GitHubProfile,
    GoogleProfile,
    UserRegisterDTO,
    UserUpdate,
)

from vweb.config import get_settings

if TYPE_CHECKING:
    from vclient.models.users import User


def _require_registration_fields(data: dict, fields: list[str], provider: str) -> None:
    """Abort with a flash message if required OAuth fields are missing for registration.

    Args:
        data: The OAuth user info dict.
        fields: Field names that must be truthy.
        provider: Provider name for the error message (e.g. "Discord").
    """
    if any(not data.get(f) for f in fields):
        flash(
            f"Could not register your account: {provider} {' and '.join(fields)} are required.",
            "error",
        )
        abort(redirect(url_for("index.index")))


def _build_discord_profile(discord_data: dict) -> DiscordProfileUpdate:
    """Build a DiscordProfile from raw Discord OAuth data.

    Args:
        discord_data: The user info dict from Discord's /users/@me endpoint.

    Returns:
        A populated DiscordProfile model instance.
    """
    return DiscordProfileUpdate(
        id=discord_data.get("id"),
        username=discord_data.get("username"),
        global_name=discord_data.get("global_name"),
        avatar_id=discord_data.get("avatar"),
        discriminator=discord_data.get("discriminator"),
        email=discord_data.get("email"),
        verified=discord_data.get("verified"),
    )


def _find_existing_user_by_provider(
    users: list[User],
    *,
    profile_attr: str,
    provider_id: str,
    provider_email: str,
) -> User | None:
    """Search for an existing user matching OAuth provider data.

    Applies a 3-step resolution strategy in priority order:
    1. Match the provider profile's ID
    2. Match the provider profile's email
    3. Match the user's top-level email

    Args:
        users: All users from the API.
        profile_attr: User attribute name for the provider profile
            (e.g. "discord_profile").
        provider_id: The provider's unique user ID.
        provider_email: The email from the provider.

    Returns:
        The matched user, or None if no match is found.
    """
    email_match: User | None = None
    top_email_match: User | None = None

    for user in users:
        profile = getattr(user, profile_attr, None)

        if profile and profile.id == provider_id:
            return user

        if email_match is None and provider_email and profile and profile.email == provider_email:
            email_match = user

        if top_email_match is None and provider_email and user.email == provider_email:
            top_email_match = user

    return email_match or top_email_match


def resolve_or_create_discord_user(discord_data: dict) -> User:
    """Resolve an existing user or create a new one from Discord OAuth data.

    Implements 4-step user resolution: match by discord profile ID, discord profile
    email, user email, or create a new UNAPPROVED user. On every successful login,
    the user's discord_profile is updated with the latest Discord data.

    Args:
        discord_data: The user info dict from Discord's /users/@me endpoint.

    Returns:
        The resolved or newly created user.
    """
    settings = get_settings()
    svc = sync_users_service(company_id=settings.api.default_company_id)
    profile = _build_discord_profile(discord_data)

    all_users: list[User] = svc.list_all()
    matched = _find_existing_user_by_provider(
        all_users,
        profile_attr="discord_profile",
        provider_id=discord_data.get("id", ""),
        provider_email=discord_data.get("email", ""),
    )

    if matched:
        return svc.update(
            matched.id,
            request=UserUpdate(
                discord_profile=profile,
                requesting_user_id=matched.id,
            ),
        )

    _require_registration_fields(discord_data, ["username", "email"], "Discord")

    return svc.register(
        request=UserRegisterDTO(
            username=discord_data["username"],
            email=discord_data["email"],
            discord_profile=profile,
        ),
    )


def _build_github_profile(github_data: dict) -> GitHubProfile:
    """Build a GitHubProfile from raw GitHub OAuth data.

    Args:
        github_data: The user info dict from GitHub's /user endpoint.

    Returns:
        A populated GitHubProfile model instance.
    """
    return GitHubProfile(
        id=str(github_data.get("id", "")),
        login=github_data.get("login"),
        username=github_data.get("name"),
        avatar_url=github_data.get("avatar_url"),
        email=github_data.get("email"),
        profile_url=github_data.get("html_url"),
    )


def resolve_or_create_github_user(github_data: dict) -> User:
    """Resolve an existing user or create a new one from GitHub OAuth data.

    Implements 4-step user resolution: match by github profile ID, github profile
    email, user email, or create a new UNAPPROVED user. On every successful login,
    the user's github_profile is updated with the latest GitHub data.

    Args:
        github_data: The user info dict from GitHub's /user endpoint.

    Returns:
        The resolved or newly created user.
    """
    settings = get_settings()
    svc = sync_users_service(company_id=settings.api.default_company_id)
    profile = _build_github_profile(github_data)

    all_users: list[User] = svc.list_all()
    matched = _find_existing_user_by_provider(
        all_users,
        profile_attr="github_profile",
        provider_id=str(github_data.get("id", "")),
        provider_email=github_data.get("email", "") or "",
    )

    if matched:
        return svc.update(
            matched.id,
            request=UserUpdate(
                github_profile=profile,
                requesting_user_id=matched.id,
            ),
        )

    _require_registration_fields(github_data, ["login", "email"], "GitHub")

    return svc.register(
        request=UserRegisterDTO(
            username=github_data["login"],
            email=github_data["email"],
            github_profile=profile,
        ),
    )


def _build_google_profile(google_data: dict) -> GoogleProfile:
    """Build a GoogleProfile from raw Google OAuth userinfo data.

    Args:
        google_data: The user info dict from Google's userinfo endpoint.

    Returns:
        A populated GoogleProfile model instance.
    """
    return GoogleProfile(
        id=google_data.get("sub", ""),
        email=google_data.get("email"),
        verified_email=google_data.get("email_verified"),
        username=google_data.get("name"),
        name_first=google_data.get("given_name"),
        name_last=google_data.get("family_name"),
        avatar_url=google_data.get("picture"),
        locale=google_data.get("locale"),
    )


def resolve_or_create_google_user(google_data: dict) -> User:
    """Resolve an existing user or create a new one from Google OAuth data.

    Implements 4-step user resolution: match by google profile ID, google profile
    email, user email, or create a new UNAPPROVED user. On every successful login,
    the user's google_profile is updated with the latest Google data.

    Args:
        google_data: The user info dict from Google's userinfo endpoint.

    Returns:
        The resolved or newly created user.
    """
    settings = get_settings()
    svc = sync_users_service(company_id=settings.api.default_company_id)
    profile = _build_google_profile(google_data)

    all_users: list[User] = svc.list_all()
    matched = _find_existing_user_by_provider(
        all_users,
        profile_attr="google_profile",
        provider_id=google_data.get("sub", ""),
        provider_email=google_data.get("email", "") or "",
    )

    if matched:
        return svc.update(
            matched.id,
            request=UserUpdate(
                google_profile=profile,
                requesting_user_id=matched.id,
            ),
        )

    _require_registration_fields(google_data, ["name", "email"], "Google")

    return svc.register(
        request=UserRegisterDTO(
            username=google_data["name"],
            email=google_data["email"],
            google_profile=profile,
            name_first=google_data.get("given_name") or None,
            name_last=google_data.get("family_name") or None,
        ),
    )
