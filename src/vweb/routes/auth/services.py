"""Auth service for cross-company user lookup and profile updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient import sync_user_lookup_service, sync_users_service
from vclient.models.users import (
    DiscordProfileUpdate,
    GitHubProfile,
    GoogleProfile,
    UserUpdate,
)

if TYPE_CHECKING:
    from vclient.models import UserLookupResult


_PROVIDER_LOOKUP_METHODS = {
    "discord": "by_discord_id",
    "github": "by_github_id",
    "google": "by_google_id",
}


def lookup_user_companies(
    *,
    provider: str,
    provider_id: str,
    email: str,
) -> list[UserLookupResult]:
    """Search for a user across all companies by provider ID, falling back to email."""
    svc = sync_user_lookup_service()
    method_name = _PROVIDER_LOOKUP_METHODS[provider]
    results = getattr(svc, method_name)(provider_id)
    if not results and email:
        results = svc.by_email(email)
    return results


def build_companies_mapping(results: list[UserLookupResult]) -> dict[str, dict[str, str]]:
    """Build session companies mapping from lookup results."""
    return {
        r.company_id: {
            "user_id": r.user_id,
            "company_name": r.company_name,
            "role": r.role,
        }
        for r in results
    }


def update_discord_profile(company_id: str, user_id: str, discord_data: dict) -> None:
    """Update a user's Discord profile after login."""
    profile = DiscordProfileUpdate(
        id=discord_data.get("id"),
        username=discord_data.get("username"),
        global_name=discord_data.get("global_name"),
        avatar_id=discord_data.get("avatar"),
        discriminator=discord_data.get("discriminator"),
        email=discord_data.get("email"),
        verified=discord_data.get("verified"),
    )
    sync_users_service(company_id=company_id).update(
        user_id,
        request=UserUpdate(discord_profile=profile, requesting_user_id=user_id),
    )


def update_github_profile(company_id: str, user_id: str, github_data: dict) -> None:
    """Update a user's GitHub profile after login."""
    profile = GitHubProfile(
        id=str(github_data.get("id", "")),
        login=github_data.get("login"),
        username=github_data.get("name"),
        avatar_url=github_data.get("avatar_url"),
        email=github_data.get("email"),
        profile_url=github_data.get("html_url"),
    )
    sync_users_service(company_id=company_id).update(
        user_id,
        request=UserUpdate(github_profile=profile, requesting_user_id=user_id),
    )


def update_google_profile(company_id: str, user_id: str, google_data: dict) -> None:
    """Update a user's Google profile after login."""
    profile = GoogleProfile(
        id=google_data.get("sub", ""),
        email=google_data.get("email"),
        verified_email=google_data.get("email_verified"),
        username=google_data.get("name"),
        name_first=google_data.get("given_name"),
        name_last=google_data.get("family_name"),
        avatar_url=google_data.get("picture"),
        locale=google_data.get("locale"),
    )
    sync_users_service(company_id=company_id).update(
        user_id,
        request=UserUpdate(google_profile=profile, requesting_user_id=user_id),
    )
