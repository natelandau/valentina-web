"""Response models for the character full sheet endpoint."""

from pydantic import BaseModel, Field

from vweb.api_client.constants import HunterEdgeType

from .character_trait import CharacterTrait
from .characters import Character
from .shared import Trait


class FullSheetTraitSubcategory(BaseModel):
    """A trait subcategory on the full character sheet."""

    id: str
    name: str
    description: str | None = None
    initial_cost: int
    upgrade_cost: int
    show_when_empty: bool
    requires_parent: bool
    pool: str | None = None
    system: str | None = None
    hunter_edge_type: HunterEdgeType | None = None
    character_traits: list[CharacterTrait]
    available_traits: list[Trait] = Field(default_factory=list)


class FullSheetTraitCategory(BaseModel):
    """A trait category on the full character sheet."""

    id: str
    name: str
    description: str | None = None
    initial_cost: int
    upgrade_cost: int
    show_when_empty: bool
    order: int
    subcategories: list[FullSheetTraitSubcategory]
    character_traits: list[CharacterTrait]
    available_traits: list[Trait] = Field(default_factory=list)


class FullSheetTraitSection(BaseModel):
    """A trait section on the full character sheet."""

    id: str
    name: str
    description: str | None = None
    order: int
    show_when_empty: bool
    categories: list[FullSheetTraitCategory]


class CharacterFullSheet(BaseModel):
    """Complete character sheet with all traits organized hierarchically.

    Contains the character data and the full trait hierarchy organized as
    sections > categories > subcategories > character traits.
    """

    character: Character
    sections: list[FullSheetTraitSection]
