"""Auth service for cross-company user lookup and identity resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from vclient import sync_identity_service, sync_user_lookup_service, sync_users_service
from vclient.exceptions import APIError, ServerError, UnprocessableEntityError
from vclient.models.users import (
    DiscordProfileUpdate,
    GitHubProfile,
    GoogleProfile,
    UserUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vclient.constants import IdentityProvider
    from vclient.models import IdentityResolution, UserLookupResult

logger = logging.getLogger(__name__)


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


def identify_in_companies(
    company_ids: Sequence[str],
    *,
    provider: IdentityProvider,
    token: str,
    username: str | None = None,
    email: str | None = None,
) -> dict[str, IdentityResolution]:
    """Resolve a verified provider credential in each company.

    Server-verifies the credential once per company, auto-linking the identity
    onto email-matched users, refreshing the stored provider profile, and
    creating an UNAPPROVED user where none exists. Token- and provider-level
    failures (422 / PROVIDER_UNAVAILABLE) affect every company equally, so they
    propagate for callers to branch on; other per-company failures are logged
    and skipped so one bad company does not block login everywhere else.

    Args:
        company_ids: Companies to resolve the identity in.
        provider: The identity provider that issued the credential.
        token: OIDC ID token (apple/google) or OAuth access token (discord/github).
        username: Display name hint, used only when the API creates a new user.
        email: Email hint, used only when the API creates a new user and the
            provider supplied no email.

    Raises:
        UnprocessableEntityError: If the credential fails verification or a new
            user needs an email the provider did not supply; credential-level
            failures that apply to every company equally.
        ServerError: If the API or the upstream provider is unavailable (5xx).

    Returns:
        dict[str, IdentityResolution]: Successful resolutions keyed by company ID.
    """
    resolutions: dict[str, IdentityResolution] = {}
    for company_id in company_ids:
        try:
            resolutions[company_id] = sync_identity_service(company_id=company_id).identify(
                provider=provider,
                token=token,
                username=username,
                email=email,
            )
        except (httpx.HTTPError, APIError) as exc:
            # 422/5xx are token- or provider-level: failing in one company means
            # failing in all, so surface them instead of logging per company
            if isinstance(exc, (UnprocessableEntityError, ServerError)):
                raise
            logger.exception("identify failed for company %s via %s", company_id, provider)
    return resolutions


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
    sync_users_service(on_behalf_of=user_id, company_id=company_id).update(
        user_id,
        request=UserUpdate(discord_profile=profile),
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
    sync_users_service(on_behalf_of=user_id, company_id=company_id).update(
        user_id,
        request=UserUpdate(github_profile=profile),
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
    sync_users_service(on_behalf_of=user_id, company_id=company_id).update(
        user_id,
        request=UserUpdate(google_profile=profile),
    )
