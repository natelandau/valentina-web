"""Shared Pydantic models used across multiple services."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from vweb.api_client.constants import (
    AssetType,
    CharacterClass,
    GameVersion,
    SpecialtyType,
    TrackerType,
    WerewolfRenown,
)
from vweb.api_client.models.request_types import LongText3, Name3to50

# -----------------------------------------------------------------------------
# Utility  Models
# -----------------------------------------------------------------------------


class NameDescriptionSubDocument(BaseModel):
    """Name and description base model. Use this for sub-documents that have a name and description."""

    name: str | None = None
    description: str | None = None


# -----------------------------------------------------------------------------
# Asset Models
# -----------------------------------------------------------------------------


class Asset(BaseModel):
    """Response model for an asset.

    Represents a file asset, including its URL and metadata.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    asset_type: AssetType
    mime_type: str
    original_filename: str
    public_url: str
    uploaded_by_id: str
    company_id: str
    character_id: str | None = None
    campaign_id: str | None = None
    book_id: str | None = None
    chapter_id: str | None = None
    user_parent_id: str | None = None


# -----------------------------------------------------------------------------
# Note Models
# -----------------------------------------------------------------------------


class Note(BaseModel):
    """Response model for a note.

    Represents a note attached to a user, campaign, or other entity.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    title: str
    content: str


class NoteCreate(BaseModel):
    """Request body for creating a new note.

    Used to construct the JSON payload for note creation.
    """

    title: Name3to50
    content: LongText3


class NoteUpdate(BaseModel):
    """Request body for updating a note.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    title: Name3to50 | None = None
    content: LongText3 | None = None


# -----------------------------------------------------------------------------
# Statistics Models
# -----------------------------------------------------------------------------


class RollStatistics(BaseModel):
    """Aggregated dice roll statistics for a user, campaign, or character.

    Contains success rates, critical frequencies, and most-used traits
    for analyzing gameplay patterns.
    """

    botches: int
    successes: int
    failures: int
    criticals: int
    total_rolls: int
    average_difficulty: float | None = None
    average_pool: float | None = None
    top_traits: list[dict[str, Any]] = Field(default_factory=list)
    criticals_percentage: float
    success_percentage: float
    failure_percentage: float
    botch_percentage: float


# -----------------------------------------------------------------------------
# Trait Models
# -----------------------------------------------------------------------------


class GiftAttributes(BaseModel):
    """Werewolf gift-specific attributes embedded on a Trait."""

    renown: WerewolfRenown
    cost: str | None = None
    duration: str | None = None
    minimum_renown: int | None = None
    is_native_gift: bool = False
    tribe_id: str | None = None
    tribe_name: str | None = None
    auspice_id: str | None = None
    auspice_name: str | None = None


class TraitPower(BaseModel):
    """A power a trait grants at a specific dot level.

    Named powers (Disciplines and Thaumaturgy/Necromancy paths) carry a name and usually a
    system. Nameless per-dot descriptors on Attributes and Skills describe what each dot
    rating means and have `name` set to None.
    """

    id: str
    level: int
    name: str | None = None
    description: str | None = None
    system: str | None = None
    link: str | None = None


class Trait(BaseModel):
    """Response model for a trait.

    Represents a trait assigned to a character.
    """

    id: str
    name: str
    description: str | None = None
    date_created: datetime
    date_modified: datetime
    link: str | None = None
    show_when_zero: bool = True
    max_value: int = 5
    min_value: int = 0
    initial_cost: int = 1
    upgrade_cost: int = 2
    count_based_cost_multiplier: int | None = None
    is_rollable: bool = True

    sheet_section_name: str | None = None
    sheet_section_id: str
    category_name: str | None = None
    category_id: str
    # Non-null marks a custom trait owned by that character, which is deleted along with it.
    custom_for_character_id: str | None = None
    subcategory_id: str | None = None
    subcategory_name: str | None = None
    pool: str | None = None
    opposing_pool: str | None = None
    system: str | None = None
    gift_attributes: GiftAttributes | None = None

    # Ordered by level ascending, then name. A single level may grant several powers.
    powers: list[TraitPower] = Field(default_factory=list)

    character_classes: list[CharacterClass] = Field(default_factory=list)
    game_versions: list[GameVersion] = Field(default_factory=list)

    tracker_type_v4: TrackerType | None = Field(
        default=None, description="Tracker this trait has on V4 characters, or None."
    )
    tracker_type_v5: TrackerType | None = Field(
        default=None, description="Tracker this trait has on V5 characters, or None."
    )


class CharacterSpecialty(BaseModel):
    """A character specialty for a trait."""

    name: str
    type: SpecialtyType
    description: str


__all__ = [
    "Asset",
    "CharacterSpecialty",
    "GiftAttributes",
    "NameDescriptionSubDocument",
    "Note",
    "NoteCreate",
    "NoteUpdate",
    "RollStatistics",
    "Trait",
    "TraitPower",
]
