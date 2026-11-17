"""Pydantic models for CampaignBook entities."""

from datetime import datetime

from pydantic import BaseModel, Field

from vweb.api_client.models.chapters import CampaignChapter
from vweb.api_client.models.shared import Asset, Note


class CampaignBook(BaseModel):
    """Response model for a campaign book.

    Represents a book within a campaign, containing notes and assets.
    """

    id: str = Field(..., description="MongoDB document ObjectID.")
    date_created: datetime = Field(..., description="Timestamp when the book was created.")
    date_modified: datetime = Field(..., description="Timestamp when the book was last modified.")
    name: str = Field(..., description="Book name (3-50 characters).")
    description: str | None = Field(default=None, description="Book description.")
    asset_ids: list[str] = Field(default_factory=list, description="List of associated asset IDs.")
    character_ids: list[str] = Field(
        default_factory=list,
        description="Read-only union of character IDs across the book's chapters.",
    )
    number: int = Field(..., description="Book number within the campaign.")
    campaign_id: str = Field(..., description="ID of the parent campaign.")
    num_chapters: int = Field(default=0, description="Number of active chapters in the book.")
    num_notes: int = Field(default=0, description="Number of active notes on the book.")
    num_assets: int = Field(default=0, description="Number of active assets on the book.")


class CampaignBookDetail(CampaignBook):
    """Campaign book response with optional embedded child resources.

    Returned by the single-book endpoint when the ``include`` query parameter
    is used. Absent resources default to ``None``; present resources are full arrays
    of the same DTOs returned by the dedicated child endpoints.
    """

    chapters: list[CampaignChapter] | None = Field(
        default=None, description="Embedded chapters, when requested via include."
    )
    notes: list[Note] | None = Field(
        default=None, description="Embedded notes, when requested via include."
    )
    assets: list[Asset] | None = Field(
        default=None, description="Embedded assets, when requested via include."
    )


class BookCreate(BaseModel):
    """Request body for creating a new campaign book.

    Used to construct the JSON payload for book creation.
    """

    name: str = Field(..., min_length=3, max_length=50, description="Book name (3-50 characters).")
    description: str | None = Field(
        default=None, min_length=3, description="Book description (minimum 3 characters)."
    )


class BookUpdate(BaseModel):
    """Request body for updating a campaign book.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    name: str | None = Field(
        default=None, min_length=3, max_length=50, description="New book name (3-50 characters)."
    )
    description: str | None = Field(
        default=None, min_length=3, description="New book description (minimum 3 characters)."
    )


class _BookRenumber(BaseModel):
    """Internal request body for renumbering a campaign book.

    Changes the book's position number within the campaign.
    """

    number: int = Field(..., ge=1, description="New book number (must be >= 1).")


__all__ = [
    "BookCreate",
    "BookUpdate",
    "CampaignBook",
    "CampaignBookDetail",
    "_BookRenumber",
]
