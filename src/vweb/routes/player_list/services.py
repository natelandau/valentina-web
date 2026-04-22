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
    """Apply optional role and has-characters filters to a player list.

    Falsy filter values pass through unchanged. ``has_characters`` only applies
    when set to ``HAS_CHARACTERS_YES`` or ``HAS_CHARACTERS_NO``.
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
