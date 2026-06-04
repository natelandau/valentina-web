"""Recent dice-roll display cache.

Fetch recent rolls for a scope (campaign/character/user), shape them for display, and
cache for 30 seconds. The key includes the requesting user because the API filters by
``on_behalf_of`` — different users may see different rolls for the same scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import g, session
from vclient import sync_dicerolls_service

from vweb.constants import CACHE_DICEROLLS_TTL
from vweb.lib.cache import base, blueprint

if TYPE_CHECKING:
    from datetime import datetime

    from vclient.models import Character
    from vclient.models.diceroll import RollResultType

_STRATEGY = base.ShortTTL(ttl=CACHE_DICEROLLS_TTL)


def _cache_key(
    *,
    company_id: str,
    requesting_user_id: str,
    campaign_id: str,
    character_id: str,
    user_id: str,
    limit: int,
) -> str:
    # company_id stays readable for tenant-level grouping; the per-user scope filters
    # (most of them optional) are folded into one digest so absent filters cannot
    # produce empty `::` segments and the key length stays bounded.
    return (
        f"dicerolls:{company_id}:"
        f"{base.hash_key(requesting_user_id, campaign_id, character_id, user_id, limit)}"
    )


@dataclass
class DiceRollDisplay:
    """Display-ready representation of a single dice roll."""

    id: str
    character_id: str
    character_name: str
    num_dice: int
    dice_size: int
    trait_names: list[str]
    result_type: RollResultType | None
    result_humanized: str | None
    date_created: datetime
    comment: str | None


def recent(
    campaign_id: str = "",
    *,
    character_id: str = "",
    user_id: str = "",
    limit: int = 25,
) -> list[DiceRollDisplay]:
    """Return recent dice rolls filtered by one or more scopes (30s TTL, per user+scope).

    Fetch up to ``limit`` most-recent rolls matching the provided scopes (combined AND
    on the API side). When the only scope passed is ``campaign_id``, additionally filter
    to PLAYER-character rolls on the API side — keeps the campaign overview free of
    NPC/storyteller noise without burning ``limit`` slots on discarded rolls.

    Args:
        campaign_id: Campaign scope (optional).
        character_id: Character scope (optional).
        user_id: User scope (optional).
        limit: Maximum number of rolls to fetch from the API.

    Returns:
        Display-ready rows in the API's newest-first order.
    """
    company_id = session["company_id"]
    requesting_user_id = g.requesting_user.id
    key = _cache_key(
        company_id=company_id,
        requesting_user_id=requesting_user_id,
        campaign_id=campaign_id,
        character_id=character_id,
        user_id=user_id,
        limit=limit,
    )
    return base.cached_fetch(
        key,
        lambda: _fetch(
            company_id=company_id,
            requesting_user_id=requesting_user_id,
            campaign_id=campaign_id,
            character_id=character_id,
            user_id=user_id,
            limit=limit,
        ),
        _STRATEGY,
    )


def _fetch(
    *,
    company_id: str,
    requesting_user_id: str,
    campaign_id: str,
    character_id: str,
    user_id: str,
    limit: int,
) -> list[DiceRollDisplay]:
    service = sync_dicerolls_service(on_behalf_of=requesting_user_id, company_id=company_id)
    apply_player_filter = bool(campaign_id) and not (character_id or user_id)
    page = service.get_page(
        campaignid=campaign_id or None,
        characterid=character_id or None,
        userid=user_id or None,
        character_type="PLAYER" if apply_player_filter else None,
        limit=limit,
        offset=0,
    )

    ctx = g.global_context
    characters_by_id: dict[str, Character] = {c.id: c for c in ctx.characters}
    all_traits = blueprint.traits()

    displays: list[DiceRollDisplay] = []
    for roll in page.items:
        character = characters_by_id.get(roll.character_id) if roll.character_id else None
        character_name = character.name if character else ""
        character_id_display = character.id if character else (roll.character_id or "")

        trait_names = [all_traits[tid].name for tid in roll.trait_ids if tid in all_traits]

        displays.append(
            DiceRollDisplay(
                id=roll.id,
                character_id=character_id_display,
                character_name=character_name,
                num_dice=roll.num_dice,
                dice_size=roll.dice_size,
                trait_names=trait_names,
                result_type=roll.result.total_result_type if roll.result else None,
                result_humanized=roll.result.total_result_humanized if roll.result else None,
                date_created=roll.date_created,
                comment=roll.comment,
            )
        )
    return displays
