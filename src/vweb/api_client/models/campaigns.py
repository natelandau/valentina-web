"""Pydantic models for Campaign API responses and requests."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from vweb.api_client.models.request_types import LongText, Name3to50

# -----------------------------------------------------------------------------
# Campaign Response Models
# -----------------------------------------------------------------------------


class Campaign(BaseModel):
    """Response model for a campaign.

    Represents a campaign entity returned from the API with all properties.
    Campaigns are containers for characters, books, chapters, and other game content.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    name: str
    description: str | None = None
    in_game_date: date | None = None
    asset_ids: list[str] = Field(default_factory=list)
    desperation: int = 0
    danger: int = 0
    company_id: str
    num_books: int = 0
    num_chapters: int = 0
    num_notes: int = 0
    num_player_characters: int = 0
    num_storyteller_characters: int = 0
    num_npc_characters: int = 0


# -----------------------------------------------------------------------------
# Campaign Request Models
# -----------------------------------------------------------------------------


class CampaignCreate(BaseModel):
    """Request body for creating a new campaign.

    Used to construct the JSON payload for campaign creation.
    """

    name: Name3to50
    description: LongText | None = None
    in_game_date: date | None = None
    desperation: int = Field(default=0, ge=0, le=5)
    danger: int = Field(default=0, ge=0, le=5)


class CampaignUpdate(BaseModel):
    """Request body for updating a campaign.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    name: Name3to50 | None = None
    # An empty string clears the description; None leaves it unchanged
    description: LongText | None = None
    in_game_date: date | None = None
    desperation: Annotated[int, Field(ge=0, le=5)] | None = None
    danger: Annotated[int, Field(ge=0, le=5)] | None = None


__all__ = [
    "Campaign",
    "CampaignCreate",
    "CampaignUpdate",
]
