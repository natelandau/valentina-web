"""Dice roll service layer for executing rolls via the vclient API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import g, session
from vclient import sync_character_traits_service, sync_dicerolls_service, sync_users_service

if TYPE_CHECKING:
    from vclient.constants import DiceSize
    from vclient.models import Campaign, Character, CharacterTrait, Diceroll, Quickroll


@dataclass
class RollContext:
    """All data needed to render the dice roll modal for a character.

    Bundles the character's traits, the user's quickrolls, and the campaign's
    desperation level so routes can pass a single object to templates.
    """

    character_traits: list[CharacterTrait]
    quickrolls: list[Quickroll]
    campaign_desperation: int = 0


def get_character_traits(*, character: Character) -> list[CharacterTrait]:
    """Fetch the character's traits for server-side dice pool computation used in the dice roll modal.

    Args:
        character: The character whose traits to fetch.

    Returns:
        The character's full list of traits.
    """
    user_id = g.requesting_user.id

    return sync_character_traits_service(
        on_behalf_of=user_id,
        character_id=character.id,
        company_id=session["company_id"],
    ).list_all(is_rollable=True)


def get_roll_context(*, character: Character, campaign: Campaign) -> RollContext:
    """Fetch everything needed to display the dice roll modal for a character.

    Calls the API for both character traits and the requesting user's quickrolls,
    then reads campaign desperation directly from the campaign object.

    Args:
        character: The character for whom the roll context is being built.
        campaign: The campaign the character belongs to, used for desperation level.

    Returns:
        A RollContext containing traits, quickrolls, and desperation.
    """
    user_id = g.requesting_user.id

    traits = get_character_traits(character=character)
    quickrolls = sync_users_service(
        on_behalf_of=user_id, company_id=session["company_id"]
    ).list_all_quickrolls(user_id)

    return RollContext(
        character_traits=traits,
        quickrolls=quickrolls,
        campaign_desperation=campaign.desperation,
    )


def perform_custom_roll(
    *,
    character: Character,
    campaign: Campaign,
    dice_size: DiceSize,
    num_dice: int,
    difficulty: int,
    comment: str | None = None,
) -> Diceroll:
    """Execute a free-form dice roll with explicit dice size and count.

    Use this when the player manually enters the pool size and die type rather
    than selecting traits or a quickroll template.

    Args:
        character: The character performing the roll.
        campaign: The campaign context for the roll.
        dice_size: The size of each die (e.g. 4, 6, 8, 10, 20, 100).
        num_dice: Number of dice in the pool.
        difficulty: The target number to beat on each die.
        comment: Optional narrative context for the roll.

    Returns:
        The resulting Diceroll object from the API.
    """
    from vclient.models import DicerollCreate

    user_id = g.requesting_user.id

    request = DicerollCreate(
        dice_size=dice_size,
        num_dice=num_dice,
        difficulty=difficulty,
        comment=comment,
        character_id=character.id,
        campaign_id=campaign.id,
    )
    return sync_dicerolls_service(on_behalf_of=user_id, company_id=session["company_id"]).create(
        request
    )


def perform_trait_roll(  # noqa: PLR0913
    *,
    character: Character,
    campaign: Campaign,
    character_traits: list[CharacterTrait],
    trait_one_id: str,
    trait_two_id: str | None = None,
    difficulty: int,
    num_desperation_dice: int = 0,
    comment: str | None = None,
) -> Diceroll:
    """Execute a trait-based dice roll, computing the pool server-side from character traits.

    Trait values are resolved from `character_traits` rather than trusting any form input,
    preventing players from manipulating their pool size by submitting arbitrary numbers.
    Always uses d10s to match the World of Darkness system.

    Args:
        character: The character performing the roll.
        campaign: The campaign context for the roll.
        character_traits: The character's full list of traits used for server-side value lookup.
        trait_one_id: The ID of the primary trait contributing to the dice pool.
        trait_two_id: The ID of the secondary trait, if any.
        difficulty: The target number to beat on each die.
        num_desperation_dice: Number of additional desperation dice to add to the pool.
        comment: Optional narrative context for the roll.

    Returns:
        The resulting Diceroll object from the API.

    Raises:
        ValueError: If trait_one_id or trait_two_id is not found in character_traits.
    """
    from vclient.models import DicerollCreate

    user_id = g.requesting_user.id

    trait_map = {ct.trait.id: ct for ct in character_traits}

    char_trait_one = trait_map.get(trait_one_id)
    if char_trait_one is None:
        msg = f"Trait '{trait_one_id}' not found in character traits"
        raise ValueError(msg)

    pool = char_trait_one.value

    trait_ids = [trait_one_id]

    if trait_two_id is not None:
        char_trait_two = trait_map.get(trait_two_id)
        if char_trait_two is None:
            msg = f"Trait '{trait_two_id}' not found in character traits"
            raise ValueError(msg)
        pool += char_trait_two.value
        trait_ids.append(trait_two_id)

    request = DicerollCreate(
        dice_size=10,
        num_dice=pool,
        difficulty=difficulty,
        num_desperation_dice=num_desperation_dice,
        comment=comment,
        character_id=character.id,
        campaign_id=campaign.id,
        trait_ids=trait_ids,
    )
    return sync_dicerolls_service(on_behalf_of=user_id, company_id=session["company_id"]).create(
        request
    )


def perform_quickroll(
    *,
    character: Character,
    quickroll_id: str,
    difficulty: int,
    num_desperation_dice: int = 0,
    comment: str | None = None,
) -> Diceroll:
    """Execute a dice roll using a saved quickroll template.

    Quickrolls store a predefined set of traits so the user can repeat common
    rolls (e.g. "Dexterity + Athletics") without re-selecting traits each time.

    Args:
        character: The character performing the roll.
        quickroll_id: The ID of the quickroll template to use.
        difficulty: The target number to beat on each die.
        num_desperation_dice: Number of additional desperation dice to add to the pool.
        comment: Optional narrative context for the roll.

    Returns:
        The resulting Diceroll object from the API.
    """
    user_id = g.requesting_user.id

    return sync_dicerolls_service(
        on_behalf_of=user_id, company_id=session["company_id"]
    ).create_from_quickroll(
        quickroll_id=quickroll_id,
        character_id=character.id,
        difficulty=difficulty,
        num_desperation_dice=num_desperation_dice,
        comment=comment,
    )
