"""Pydantic models for Diceroll API responses and requests."""

from datetime import datetime

from pydantic import BaseModel, Field

from vweb.api_client.constants import DiceSize, RollResultType


class DiceRollResultSchema(BaseModel):
    """Represent the result of a dice roll."""

    total_result: int | None = None
    total_result_type: RollResultType
    total_result_humanized: str
    total_dice_roll: list[int] = Field(default_factory=list)
    player_roll: list[int] = Field(default_factory=list)
    desperation_roll: list[int] = Field(default_factory=list)
    total_dice_roll_emoji: str
    total_dice_roll_shortcode: str
    player_roll_emoji: str
    player_roll_shortcode: str
    desperation_roll_emoji: str
    desperation_roll_shortcode: str


class Diceroll(BaseModel):
    """Response model for a dice roll."""

    id: str
    date_created: datetime
    date_modified: datetime
    dice_size: DiceSize
    difficulty: int | None = None
    num_dice: int
    num_desperation_dice: int = 0
    dice_modifier: int = 0
    comment: str | None = None
    trait_ids: list[str] = Field(default_factory=list)
    user_id: str | None = None
    character_id: str | None = None
    campaign_id: str | None = None
    company_id: str
    result: DiceRollResultSchema | None = None


class DicerollCreate(BaseModel):
    """Request body for creating a dice roll."""

    dice_size: DiceSize
    difficulty: int | None = None
    num_dice: int
    num_desperation_dice: int = 0
    dice_modifier: int = 0
    comment: str | None = None
    trait_ids: list[str] = Field(default_factory=list)
    character_id: str | None = None
    campaign_id: str | None = None


class _DicerollQuickrollCreate(BaseModel):
    """Internal request body for creating a dice roll using a quickroll template."""

    quickroll_id: str
    character_id: str
    comment: str | None = None
    difficulty: int = 6
    num_desperation_dice: int = 0
    dice_modifier: int = 0


__all__ = [
    "Diceroll",
    "DicerollCreate",
    "_DicerollQuickrollCreate",
]
