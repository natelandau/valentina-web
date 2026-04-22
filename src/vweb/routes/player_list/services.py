"""Filtering and option-building for the campaign-scoped player list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g

if TYPE_CHECKING:
    from vclient.models import User


HAS_CHARACTERS_YES = "yes"
HAS_CHARACTERS_NO = "no"


def get_all_players() -> list[User]:
    """Return the full company roster sorted A-Z by username (case-insensitive)."""
    return sorted(g.global_context.users, key=lambda user: user.username.lower())


def filter_players(
    users: list[User],
    campaign_id: str,
    *,
    role: str | None = None,
    has_characters: str | None = None,
) -> list[User]:
    """Apply role and has-characters filters to a player list.

    A falsy ``role`` means "any role." ``has_characters`` accepts ``"yes"`` (only
    users with at least one character in the campaign), ``"no"`` (only users
    without), or any other value to skip the filter.

    Args:
        users: The full player list (already sorted).
        campaign_id: Campaign to resolve character ownership against.
        role: Optional role filter (e.g., PLAYER, STORYTELLER, ADMIN).
        has_characters: Optional membership filter — "yes", "no", or None.

    Returns:
        The filtered player list in the same order.
    """
    filtered = users
    if role:
        filtered = [u for u in filtered if u.role == role]
    if has_characters in (HAS_CHARACTERS_YES, HAS_CHARACTERS_NO):
        campaign_characters = g.global_context.characters_by_campaign.get(campaign_id, [])
        owner_ids = {c.user_player_id for c in campaign_characters if c.user_player_id}
        if has_characters == HAS_CHARACTERS_YES:
            filtered = [u for u in filtered if u.id in owner_ids]
        else:
            filtered = [u for u in filtered if u.id not in owner_ids]
    return filtered


def build_filter_options(users: list[User]) -> list[str]:
    """Return the distinct roles present in the roster, sorted."""
    roles = {user.role for user in users if user.role}
    return sorted(roles)
