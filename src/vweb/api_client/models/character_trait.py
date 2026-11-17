"""Pydantic models for Character Trait API responses and requests."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from vweb.api_client.constants import TrackerAction, TraitModifyCurrency

from .request_types import ExtraHealthLevels, LongText, Name3to50, TraitScore
from .shared import Trait


class CharacterTraitSpecialty(BaseModel):
    """Response model for a specialty on a character trait."""

    id: str
    name: str
    date_created: datetime
    date_modified: datetime


class HealthLevel(BaseModel):
    """One V4 health level and whether it is marked."""

    name: str
    marked: bool | None = Field(
        default=None, description="Whether the level is marked. None only from older API versions."
    )


class CounterTracker(BaseModel):
    """Tracker for a trait whose current value is spent and regained in play, such as Willpower."""

    type: Literal["COUNTER"] = "COUNTER"
    size: int = Field(..., description="Maximum, equal to the trait's value.")
    current: int = Field(..., description="Points currently available.")


class StainsTracker(BaseModel):
    """Tracker for V5 vampire Humanity stains."""

    type: Literal["STAINS"] = "STAINS"
    humanity: int
    stain_capacity: int = Field(..., description="Boxes left for stains, 10 minus Humanity.")
    stains: int


# In-play tracker state for a trait; pydantic picks the variant from ``type``.
Tracker = Annotated[CounterTracker | StainsTracker, Field(discriminator="type")]

_TRACKER_ADAPTER: TypeAdapter[Tracker] = TypeAdapter(Tracker)


class Health(BaseModel):
    """A character's health track: one damage count, plus named levels in V4."""

    type: Literal["DAMAGE"] = "DAMAGE"
    size: int = Field(..., description="Number of boxes on the track.")
    damage: int | None = Field(
        default=None,
        description="Marked boxes. None only from API versions that report typed damage marks.",
    )
    extra_levels: int = Field(
        default=0, description="Health levels added on top of the base track."
    )
    levels: list[HealthLevel] | None = Field(
        default=None, description="Named V4 health levels in track order. None for V5."
    )


class CharacterTrait(BaseModel):
    """Response model for a character trait."""

    id: str
    # The full sheet embeds traits without timestamps
    date_created: datetime | None = None
    date_modified: datetime | None = None
    character_id: str
    value: int
    trait: Trait
    specialties: list[CharacterTraitSpecialty] = Field(
        default_factory=list,
        description=(
            "Active specialties on the trait, oldest first. The company's specialty rules"
            " decide which traits can have them."
        ),
    )
    tracker: Tracker | None = Field(
        default=None,
        description="In-play tracker state, or None when the trait has no tracker for the "
        "character's game version.",
    )


class TrackerStateSet(BaseModel):
    """Request model for setting a trait tracker's full state.

    Set only the field for the tracker's type: ``current`` for counters (required) or
    ``stains`` for stains. Unknown fields raise so a stale key fails instead of being dropped.
    """

    model_config = ConfigDict(extra="forbid")

    current: int | None = Field(default=None, ge=0)
    stains: int | None = Field(default=None, ge=0)


class HealthStateSet(BaseModel):
    """Request model for setting a character's full health state.

    Omitted fields reset to 0. Unknown fields raise so a stale key fails instead of
    silently clearing the track.
    """

    model_config = ConfigDict(extra="forbid")

    extra_levels: ExtraHealthLevels = 0
    damage: int = Field(default=0, ge=0)


class _TrackerAction(BaseModel):
    """Internal request for POST tracker and health action endpoints."""

    action: TrackerAction
    amount: int = Field(default=1, ge=1)


class CharacterCreateTraitAssign(BaseModel):
    """Request model for assigning a character trait to a new character."""

    trait_id: str
    value: TraitScore
    tracker: TrackerStateSet | None = Field(
        default=None,
        description="Starting tracker state. Returns 400 if the trait has no tracker for the "
        "character's game version.",
    )


class CharacterTraitAdd(BaseModel):
    """Request model for adding a character trait to an already created character."""

    trait_id: str
    value: TraitScore
    currency: TraitModifyCurrency


class TraitCreate(BaseModel):
    """Request model for creating a custom character trait.

    Used to construct the JSON payload for character trait creation. The trait is
    always created at a value of ``1``; the supplied ``currency`` pays for that first dot.
    """

    name: Name3to50
    category_id: str
    currency: TraitModifyCurrency
    description: LongText | None = None
    max_value: TraitScore = 5
    min_value: TraitScore = 0
    show_when_zero: bool | None = True
    is_rollable: bool = True
    initial_cost: TraitScore | None = None
    upgrade_cost: TraitScore | None = None

    @model_validator(mode="after")
    def _check_value_range(self) -> Self:
        if self.min_value > self.max_value:
            msg = f"min_value ({self.min_value}) must not exceed max_value ({self.max_value})"
            raise ValueError(msg)
        return self


class CharacterTraitSpecialtyCreate(BaseModel):
    """Request model for adding a specialty to a character trait."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Specialty name (3-50 characters), unique on the trait ignoring case.",
    )
    currency: TraitModifyCurrency = "NO_COST"


class CharacterTraitSpecialtyUpdate(BaseModel):
    """Request model for renaming a specialty."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="New specialty name (3-50 characters), unique on the trait ignoring case.",
    )


class _TraitModify(BaseModel):
    """Internal request for PUT /value endpoint."""

    target_value: TraitScore
    currency: TraitModifyCurrency


class CharacterTraitValueOption(BaseModel):
    """Response model for a value option for a character trait."""

    direction: str
    point_change: int
    can_use_xp: bool
    xp_after: int
    can_use_starting_points: bool
    starting_points_after: int


class CharacterTraitValueOptionsResponse(BaseModel):
    """Response model for the value options for a character trait."""

    name: str
    current_value: int
    trait: Trait
    xp_current: int
    starting_points_current: int
    options: dict[str, CharacterTraitValueOption]


class BulkAssignTraitSuccess(BaseModel):
    """Single successfully assigned trait in a bulk operation."""

    trait_id: str
    character_trait: CharacterTrait


class BulkAssignTraitFailure(BaseModel):
    """Single failed trait assignment in a bulk operation."""

    trait_id: str
    error: str


class BulkAssignTraitResponse(BaseModel):
    """Response for bulk trait assignment."""

    succeeded: list[BulkAssignTraitSuccess]
    failed: list[BulkAssignTraitFailure]


__all__ = [
    "_TRACKER_ADAPTER",
    "BulkAssignTraitFailure",
    "BulkAssignTraitResponse",
    "BulkAssignTraitSuccess",
    "CharacterCreateTraitAssign",
    "CharacterTrait",
    "CharacterTraitAdd",
    "CharacterTraitSpecialty",
    "CharacterTraitSpecialtyCreate",
    "CharacterTraitSpecialtyUpdate",
    "CharacterTraitValueOption",
    "CharacterTraitValueOptionsResponse",
    "CounterTracker",
    "Health",
    "HealthLevel",
    "HealthStateSet",
    "StainsTracker",
    "Tracker",
    "TrackerStateSet",
    "TraitCreate",
    "_TrackerAction",
    "_TraitModify",
]
