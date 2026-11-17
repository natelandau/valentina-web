"""Pydantic models for Character API responses and requests."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from vweb.api_client.constants import (
    CharacterClass,
    CharacterInventoryType,
    CharacterStatus,
    CharacterType,
    GameVersion,
)

from .character_trait import CharacterCreateTraitAssign, CharacterTrait, Health, HealthStateSet
from .request_types import Generation, LongText, LongText3, Name3to50, NameMax50
from .shared import Asset, CharacterSpecialty, Note

# -----------------------------------------------------------------------------
# Nested Models
# -----------------------------------------------------------------------------


class VampireAttributes(BaseModel):
    """Vampire-specific character attributes."""

    clan_id: str | None = Field(default=None, description="ID of the vampire clan.")
    clan_name: str | None = Field(default=None, description="Name of the vampire clan.")
    generation: int | None = Field(default=None, description="Vampire generation.")
    sire: str | None = Field(default=None, description="Name of the vampire's sire.")
    bane_name: str | None = Field(default=None, description="Clan bane name.")
    bane_description: str | None = Field(default=None, description="Clan bane description.")
    compulsion_name: str | None = Field(default=None, description="Clan compulsion name.")
    compulsion_description: str | None = Field(
        default=None, description="Clan compulsion description."
    )


class VampireAttributesCreate(BaseModel):
    """Vampire-specific character attributes create request."""

    clan_id: str
    generation: Generation | None = None
    sire: NameMax50 | None = None
    bane_name: NameMax50 | None = None
    bane_description: LongText | None = None
    compulsion_name: NameMax50 | None = None
    compulsion_description: LongText | None = None


class VampireAttributesUpdate(BaseModel):
    """Vampire-specific character attributes update request."""

    clan_id: str | None = None
    generation: Generation | None = None
    sire: NameMax50 | None = None
    bane_name: NameMax50 | None = None
    bane_description: LongText | None = None
    compulsion_name: NameMax50 | None = None
    compulsion_description: LongText | None = None


class WerewolfAttributes(BaseModel):
    """Werewolf-specific character attributes."""

    tribe_id: str | None = Field(default=None, description="ID of the werewolf tribe.")
    tribe_name: str | None = Field(default=None, description="Name of the werewolf tribe.")
    auspice_id: str | None = Field(default=None, description="ID of the werewolf auspice.")
    auspice_name: str | None = Field(default=None, description="Name of the werewolf auspice.")
    pack_name: str | None = Field(default=None, description="Name of the werewolf's pack.")
    total_renown: int = Field(default=0, description="Total renown.")


class WerewolfAttributesCreate(BaseModel):
    """Werewolf-specific character attributes create request."""

    tribe_id: str
    auspice_id: str | None = None
    pack_name: str | None = None


class WerewolfAttributesUpdate(BaseModel):
    """Werewolf-specific character attributes update request."""

    tribe_id: str | None = None
    auspice_id: str | None = None
    pack_name: str | None = None


class MageAttributes(BaseModel):
    """Mage-specific character attributes."""

    sphere: str | None = Field(default=None, description="Primary sphere of magic.")
    tradition: str | None = Field(default=None, description="Mage tradition.")


class HunterAttributes(BaseModel):
    """Hunter-specific character attributes."""

    creed: str | None = Field(default=None, description="Hunter creed.")


class HunterAttributesCreate(BaseModel):
    """Hunter-specific character attributes create request."""

    creed: str | None = None


class HunterAttributesUpdate(BaseModel):
    """Hunter-specific character attributes update request."""

    creed: str | None = None


# -----------------------------------------------------------------------------
# Character Inventory Models
# -----------------------------------------------------------------------------


class InventoryItem(BaseModel):
    """A character inventory item."""

    id: str = Field(..., description="MongoDB document ObjectID.")
    character_id: str = Field(..., description="ID of the character.")
    name: str = Field(..., description="Name of the item.")
    type: CharacterInventoryType = Field(..., description="Type of the item.")
    description: str | None = Field(default=None, description="Description of the item.")
    date_created: datetime = Field(..., description="Timestamp when the item was created.")
    date_modified: datetime = Field(..., description="Timestamp when the item was last modified.")


class InventoryItemCreate(BaseModel):
    """Request body for creating a new character inventory item."""

    name: str = Field(..., description="Name of the item.")
    type: CharacterInventoryType = Field(..., description="Type of the item.")
    description: LongText | None = Field(default=None, description="Description of the item.")


class InventoryItemUpdate(BaseModel):
    """Request body for updating a character inventory item."""

    name: str | None = Field(default=None, description="Name of the item.")
    type: CharacterInventoryType | None = Field(default=None, description="Type of the item.")
    description: LongText | None = Field(default=None, description="Description of the item.")


# -----------------------------------------------------------------------------
# Character Response Model
# -----------------------------------------------------------------------------


class Character(BaseModel):
    """Response model for a character.

    Represents a character entity returned from the API with all properties.
    Characters are player or non-player entities within a campaign.
    """

    id: str = Field(..., description="MongoDB document ObjectID.")
    date_created: datetime
    date_modified: datetime
    date_killed: datetime | None = Field(
        default=None, description="Timestamp when the character was killed."
    )

    # Core fields
    character_class: CharacterClass = Field(..., description="Character class.")
    type: CharacterType = Field(default="PLAYER", description="Character type.")
    game_version: GameVersion = Field(..., description="Game version for character sheet.")
    status: CharacterStatus = Field(default="ALIVE", description="Character status.")
    starting_points: int = Field(default=0, description="Starting experience points.")
    is_temporary: bool = Field(default=False, description="Whether the character is temporary.")

    # Identity
    name_first: str = Field(..., min_length=3, description="Character's first name.")
    name_last: str = Field(..., min_length=3, description="Character's last name.")
    name_nick: str | None = Field(default=None, description="Character's nickname.")
    name: str = Field(..., description="Character's display name.")
    name_full: str = Field(..., description="Character's full name.")

    # Biography
    age: int | None = Field(default=None, description="Character's age.")
    date_of_birth: date | None = Field(
        default=None, description="Character's date of birth (ISO 8601 calendar date)."
    )
    biography: str | None = Field(default=None, description="Character biography.")
    demeanor: str | None = Field(default=None, description="Character's demeanor.")
    nature: str | None = Field(default=None, description="Character's nature.")
    concept_id: str | None = Field(default=None, description="ID of the character concept.")
    concept_name: str | None = Field(default=None, description="Name of the character concept.")

    # Relationships
    user_creator_id: str | None = Field(
        default=None, description="ID of the user who created the character."
    )
    user_player_id: str | None = Field(
        default=None, description="ID of the user who plays the character."
    )
    company_id: str = Field(..., description="ID of the company.")
    campaign_id: str = Field(..., description="ID of the campaign.")

    # Assets and traits
    asset_ids: list[str] = Field(default_factory=list, description="List of asset IDs.")
    character_trait_ids: list[str] = Field(
        default_factory=list, description="List of character trait IDs."
    )
    chapter_ids: list[str] = Field(
        default_factory=list,
        description="Read-only IDs of non-archived chapters this character is associated with.",
    )
    specialties: list[CharacterSpecialty] = Field(
        default_factory=list, description="List of character specialties."
    )

    # Class-specific attributes
    vampire_attributes: VampireAttributes | None = Field(
        default=None, description="Vampire-specific attributes."
    )
    werewolf_attributes: WerewolfAttributes | None = Field(
        default=None, description="Werewolf-specific attributes."
    )
    mage_attributes: MageAttributes | None = Field(
        default=None, description="Mage-specific attributes."
    )
    hunter_attributes: HunterAttributes | None = Field(
        default=None, description="Hunter-specific attributes."
    )

    health: Health | None = Field(
        default=None,
        description="Health track. Always set by API versions that support health.",
    )

    # Child-resource counts
    num_inventory_items: int = Field(
        default=0, description="Number of active inventory items on the character."
    )
    num_notes: int = Field(default=0, description="Number of active notes on the character.")
    num_assets: int = Field(default=0, description="Number of active assets on the character.")


class CharacterDetail(Character):
    """Character response with optional embedded child resources.

    Returned by the single-character endpoint when the ``include`` query parameter
    is used. Absent resources default to ``None``; present resources are full arrays
    of the same DTOs returned by the dedicated child endpoints.
    """

    traits: list[CharacterTrait] | None = Field(
        default=None, description="Embedded character traits, when requested via include."
    )
    inventory: list[InventoryItem] | None = Field(
        default=None, description="Embedded inventory items, when requested via include."
    )
    notes: list[Note] | None = Field(
        default=None, description="Embedded notes, when requested via include."
    )
    assets: list[Asset] | None = Field(
        default=None, description="Embedded assets, when requested via include."
    )


# -----------------------------------------------------------------------------
# Character Request Models
# -----------------------------------------------------------------------------


class CharacterCreate(BaseModel):
    """Request body for creating a new character.

    Used to construct the JSON payload for character creation.
    """

    campaign_id: str = Field(..., description="ID of the campaign this character belongs to.")
    character_class: CharacterClass = Field(..., description="Character class.")
    game_version: GameVersion = Field(..., description="Game version for character sheet.")
    name_first: Name3to50 = Field(..., description="Character's first name.")
    name_last: Name3to50 = Field(..., description="Character's last name.")

    # Optional fields
    type: CharacterType | None = Field(default=None, description="Character type.")
    is_temporary: bool = Field(default=False, description="Whether the character is temporary.")
    name_nick: Name3to50 | None = Field(default=None, description="Character's nickname.")
    age: int | None = Field(default=None, description="Character's age.")
    date_of_birth: date | None = Field(
        default=None, description="Character's date of birth (ISO 8601 calendar date)."
    )
    biography: LongText3 | None = Field(default=None, description="Character biography.")
    demeanor: Name3to50 | None = Field(default=None, description="Character's demeanor.")
    nature: Name3to50 | None = Field(default=None, description="Character's nature.")
    concept_id: str | None = Field(default=None, description="ID of the character concept.")
    user_player_id: str | None = Field(
        default=None, description="ID of the user who will play the character."
    )
    traits: list[CharacterCreateTraitAssign] | None = Field(
        default=None, description="List of traits to assign to the character."
    )
    health: HealthStateSet | None = Field(
        default=None,
        description="Starting health damage. Omit for an unhurt character.",
    )
    vampire_attributes: VampireAttributesCreate | None = Field(
        default=None, description="Vampire-specific attributes."
    )
    werewolf_attributes: WerewolfAttributesCreate | None = Field(
        default=None, description="Werewolf-specific attributes."
    )
    hunter_attributes: HunterAttributesCreate | None = Field(
        default=None, description="Hunter-specific attributes."
    )
    mage_attributes: MageAttributes | None = Field(
        default=None, description="Mage-specific attributes."
    )


class CharacterUpdate(BaseModel):
    """Request body for updating a character.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    character_class: CharacterClass | None = None
    type: CharacterType | None = None
    game_version: GameVersion | None = None
    status: CharacterStatus | None = None
    is_temporary: bool | None = None

    name_first: Name3to50 | None = Field(default=None, description="Character's first name.")
    name_last: Name3to50 | None = Field(default=None, description="Character's last name.")
    name_nick: Name3to50 | None = Field(default=None, description="Character's nickname.")

    age: int | None = None
    date_of_birth: date | None = None
    biography: LongText3 | None = Field(default=None, description="Character biography.")
    demeanor: Name3to50 | None = Field(default=None, description="Character's demeanor.")
    nature: Name3to50 | None = Field(default=None, description="Character's nature.")
    concept_id: str | None = Field(default=None, description="ID of the character concept.")

    user_player_id: str | None = None
    date_killed: datetime | None = None
    vampire_attributes: VampireAttributesUpdate | None = None
    werewolf_attributes: WerewolfAttributesUpdate | None = None
    hunter_attributes: HunterAttributesUpdate | None = None
    mage_attributes: MageAttributes | None = None


__all__ = [
    "Character",
    "CharacterCreate",
    "CharacterDetail",
    "CharacterUpdate",
    "HunterAttributes",
    "HunterAttributesCreate",
    "HunterAttributesUpdate",
    "InventoryItem",
    "InventoryItemCreate",
    "InventoryItemUpdate",
    "MageAttributes",
    "VampireAttributes",
    "VampireAttributesCreate",
    "VampireAttributesUpdate",
    "WerewolfAttributes",
    "WerewolfAttributesCreate",
    "WerewolfAttributesUpdate",
]
