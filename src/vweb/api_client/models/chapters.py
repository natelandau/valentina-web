"""Pydantic models for CampaignChapter entities."""

from datetime import datetime

from pydantic import BaseModel, Field

from vweb.api_client.models.request_types import LongText
from vweb.api_client.models.shared import Asset, Note


class CampaignChapter(BaseModel):
    """Response model for a campaign chapter.

    Represents a chapter within a campaign book, containing notes and assets.
    """

    id: str = Field(..., description="MongoDB document ObjectID.")
    date_created: datetime = Field(..., description="Timestamp when the chapter was created.")
    date_modified: datetime = Field(
        ..., description="Timestamp when the chapter was last modified."
    )
    name: str = Field(..., description="Chapter name (3-50 characters).")
    description: str | None = Field(default=None, description="Chapter description.")
    character_ids: list[str] = Field(
        default_factory=list, description="List of associated character IDs."
    )
    number: int = Field(..., description="Chapter number within the book.")
    book_id: str = Field(..., description="ID of the parent book.")
    num_notes: int = Field(default=0, description="Number of active notes on the chapter.")
    num_assets: int = Field(default=0, description="Number of active assets on the chapter.")


class CampaignChapterDetail(CampaignChapter):
    """Campaign chapter response with optional embedded child resources.

    Returned by the single-chapter endpoint when the ``include`` query parameter
    is used. Absent resources default to ``None``; present resources are full arrays
    of the same DTOs returned by the dedicated child endpoints.
    """

    notes: list[Note] | None = Field(
        default=None, description="Embedded notes, when requested via include."
    )
    assets: list[Asset] | None = Field(
        default=None, description="Embedded assets, when requested via include."
    )


class ChapterCreate(BaseModel):
    """Request body for creating a new campaign chapter."""

    name: str = Field(..., description="Chapter name (3-50 characters).")
    description: LongText | None = Field(default=None, description="Chapter description.")
    character_ids: list[str] | None = Field(
        default=None,
        description="Character IDs to associate. Each must be an active character in the same campaign.",
    )


class ChapterUpdate(BaseModel):
    """Request body for updating a campaign chapter."""

    name: str | None = Field(default=None, description="Chapter name (3-50 characters).")
    description: LongText | None = Field(default=None, description="Chapter description.")
    character_ids: list[str] | None = Field(
        default=None,
        description="Replacement character ID list. Omit to leave unchanged; send [] to clear.",
    )


class _ChapterRenumber(BaseModel):
    """Internal request body for renumbering a campaign chapter."""

    number: int = Field(..., ge=1, description="New chapter number (must be >= 1).")


__all__ = [
    "CampaignChapter",
    "CampaignChapterDetail",
    "ChapterCreate",
    "ChapterUpdate",
    "_ChapterRenumber",
]
