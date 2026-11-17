"""Pydantic models for User API responses and requests."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from vweb.api_client.constants import IdentityProvider, IdentityResolutionType, UserRole
from vweb.api_client.models.characters import Character
from vweb.api_client.models.request_types import LongText3, Name3to50, ProviderToken
from vweb.api_client.models.shared import Asset, Note

# -----------------------------------------------------------------------------
# Nested/Shared Models
# -----------------------------------------------------------------------------


class GoogleProfile(BaseModel):
    """Google profile model."""

    id: str | None = None
    email: str | None = None
    verified_email: bool | None = None
    username: str | None = None
    name_first: str | None = None
    name_last: str | None = None
    avatar_url: str | None = None
    locale: str | None = None


class GitHubProfile(BaseModel):
    """GitHub profile model."""

    id: str | None = None
    login: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    profile_url: str | None = None


class AppleProfile(BaseModel):
    """Apple profile model."""

    id: str | None = None
    email: str | None = None
    fullname: str | None = None


class DiscordProfile(BaseModel):
    """Discord profile information for a user.

    Contains Discord account details for integration with Discord bots.
    All fields are optional as not all users have Discord linked.
    """

    id: str | None = None
    username: str | None = None
    global_name: str | None = None
    avatar_id: str | None = None
    avatar_url: str | None = None
    discriminator: str | None = None
    email: str | None = None
    verified: bool | None = None


class CampaignExperience(BaseModel):
    """Experience points and cool points for a user in a specific campaign.

    Tracks the user's progression within a campaign including current XP available
    for spending, total XP earned, and cool points.
    """

    id: str
    user_id: str
    campaign_id: str
    xp_current: int = 0
    xp_total: int = 0
    cool_points: int = 0


# -----------------------------------------------------------------------------
# User Response Models
# -----------------------------------------------------------------------------


class User(BaseModel):
    """Response model for a user.

    Represents a user entity returned from the API with all properties including
    their role, Discord profile, and campaign experience.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    name_first: str | None = None
    name_last: str | None = None
    username: str
    email: str
    role: UserRole
    company_id: str
    discord_profile: DiscordProfile | None = None
    google_profile: GoogleProfile | None = None
    github_profile: GitHubProfile | None = None
    apple_profile: AppleProfile | None = None
    avatar_url: str | None = None
    """Resolved avatar URL. Precedence: custom uploaded avatar (CloudFront URL),
    then the identity-provider-derived avatar (currently Discord), else ``None``.
    Prefer this over ``discord_profile.avatar_url`` for display."""
    campaign_experience: list[CampaignExperience] = Field(default_factory=list)
    lifetime_xp: int = 0
    lifetime_cool_points: int = 0
    num_quickrolls: int = 0
    num_notes: int = 0
    num_assets: int = 0
    num_characters: int = 0


class UserDetail(User):
    """User response with optional embedded child resources.

    Returned by the single-user endpoint when the ``include`` query parameter
    is used. Absent resources default to ``None``; present resources are full arrays.

    Note: ``assets`` returns assets attached to the user (not assets the user
    uploaded), and ``characters`` returns only characters the user plays.
    """

    quickrolls: list["Quickroll"] | None = Field(
        default=None, description="Embedded quickrolls, when requested via include."
    )
    notes: list[Note] | None = Field(
        default=None, description="Embedded notes attached to the user."
    )
    assets: list[Asset] | None = Field(
        default=None, description="Embedded assets attached to the user."
    )
    characters: list[Character] | None = Field(
        default=None, description="Embedded characters the user plays."
    )


class IdentityResolution(BaseModel):
    """Response model for the identify endpoint.

    Reports the canonical user a verified provider login resolved to and how
    the resolution happened: ``matched`` (existing provider identity),
    ``linked`` (auto-linked by provider-verified email), or ``created``
    (a new UNAPPROVED user was registered).
    """

    resolution: IdentityResolutionType
    user: User


# -----------------------------------------------------------------------------
# User Request Models
# -----------------------------------------------------------------------------


class UserMergeDTO(BaseModel):
    """Merge an UNAPPROVED user into an existing primary user."""

    primary_user_id: str
    secondary_user_id: str


class UserIdentifyDTO(BaseModel):
    """Resolve a verified provider credential to a canonical user.

    ``username`` and ``email`` apply only when the API creates a new user;
    ``email`` is required there only if the provider did not supply one.
    """

    provider: IdentityProvider
    token: ProviderToken
    username: str | None = None
    email: str | None = None


class UserIdentityLinkDTO(BaseModel):
    """Attach an additional verified provider identity to an existing user."""

    provider: IdentityProvider
    token: ProviderToken


class UserCreate(BaseModel):
    """Request body for creating a new user.

    Used to construct the JSON payload for user creation.
    """

    name_first: Name3to50 | None = None
    name_last: Name3to50 | None = None
    username: Name3to50
    email: str
    role: UserRole


class UserUpdate(BaseModel):
    """Request body for updating a user.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    name_first: Name3to50 | None = None
    name_last: Name3to50 | None = None
    username: Name3to50 | None = None
    email: str | None = None
    role: UserRole | None = None


class UserApproveDTO(BaseModel):
    """Approve an unapproved user and assign a role."""

    role: UserRole


# -----------------------------------------------------------------------------
# Quickroll Models
# -----------------------------------------------------------------------------


class Quickroll(BaseModel):
    """Response model for a quickroll.

    Represents a pre-configured dice pool for frequently used trait combinations,
    allowing faster gameplay.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    name: str
    description: str | None = None
    user_id: str
    trait_ids: list[str] = Field(default_factory=list)


UserDetail.model_rebuild()


class QuickrollCreate(BaseModel):
    """Request body for creating a new quickroll.

    Used to construct the JSON payload for quickroll creation.
    """

    name: Name3to50
    description: LongText3 | None = None
    trait_ids: list[str] = Field(default_factory=list)


class QuickrollUpdate(BaseModel):
    """Request body for updating a quickroll.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    name: Name3to50 | None = None
    # The API stores an empty description as null, so "" is how a caller clears it.
    description: Literal[""] | LongText3 | None = None
    trait_ids: list[str] | None = None


# -----------------------------------------------------------------------------
# Experience Models
# -----------------------------------------------------------------------------


class _ExperienceAddRemove(BaseModel):
    """Internal request body for adding or removing experience points.

    Used to construct the JSON payload for XP/CP modifications.
    """

    amount: int = Field(ge=1)
    campaign_id: str


__all__ = [
    "AppleProfile",
    "CampaignExperience",
    "DiscordProfile",
    "GitHubProfile",
    "GoogleProfile",
    "IdentityResolution",
    "Quickroll",
    "QuickrollCreate",
    "QuickrollUpdate",
    "User",
    "UserApproveDTO",
    "UserCreate",
    "UserDetail",
    "UserIdentifyDTO",
    "UserIdentityLinkDTO",
    "UserMergeDTO",
    "UserUpdate",
    "_ExperienceAddRemove",
]
