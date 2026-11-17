"""Pydantic models for Character Blueprint API responses and requests."""

from datetime import datetime

from pydantic import BaseModel, Field

from vweb.api_client.constants import CharacterClass, GameVersion, WerewolfRenown

from .shared import CharacterSpecialty, NameDescriptionSubDocument


class SheetSection(BaseModel):
    """Response model for a character blueprint section."""

    id: str
    name: str
    description: str | None = None
    character_classes: list[CharacterClass] = Field(default_factory=list)
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)
    show_when_empty: bool
    order: int


class TraitCategory(BaseModel):
    """Response model for a character blueprint category."""

    id: str
    name: str
    description: str | None = None
    character_classes: list[CharacterClass] = Field(default_factory=list)
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)
    sheet_section_id: str
    sheet_section_name: str
    initial_cost: int
    upgrade_cost: int
    count_based_cost_multiplier: int | None = None
    order: int
    show_when_empty: bool


class TraitSubcategory(BaseModel):
    """Response model for a character blueprint subcategory."""

    id: str
    name: str
    description: str | None = None
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)
    character_classes: list[CharacterClass] = Field(default_factory=list)
    show_when_empty: bool
    initial_cost: int
    upgrade_cost: int
    count_based_cost_multiplier: int | None = None
    requires_parent: bool
    pool: str | None = None
    system: str | None = None
    category_id: str
    category_name: str
    sheet_section_id: str
    sheet_section_name: str
    hunter_edge_type: str | None = None


class VampireClan(BaseModel):
    """Response model for a vampire clan."""

    id: str
    name: str
    description: str | None = None
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)

    discipline_ids: list[str] = Field(default_factory=list)
    bane: NameDescriptionSubDocument | None = None
    variant_bane: NameDescriptionSubDocument | None = None
    compulsion: NameDescriptionSubDocument | None = None
    link: str | None = None


class WerewolfAuspice(BaseModel):
    """Response model for a werewolf auspice."""

    id: str
    name: str
    description: str | None = None
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)

    gift_trait_ids: list[str] = Field(default_factory=list)
    link: str | None = None


class WerewolfTribe(BaseModel):
    """Response model for a werewolf tribe."""

    id: str
    name: str
    description: str | None = None
    date_created: datetime
    date_modified: datetime
    game_versions: list[GameVersion] = Field(default_factory=list)

    renown: WerewolfRenown
    patron_spirit: str | None = None
    favor: str | None = None
    ban: str | None = None
    gift_trait_ids: list[str] = Field(default_factory=list)
    link: str | None = None


class CharacterConcept(BaseModel):
    """Character concept model."""

    id: str
    name: str
    description: str
    date_created: datetime
    date_modified: datetime
    examples: list[str]
    max_specialties: int = Field(default=1)
    specialties: list[CharacterSpecialty] = Field(default_factory=list)
    favored_ability_names: list[str] = Field(default_factory=list)
