"""Filtering and option-building for the campaign character list.

Visibility + sort is handled by the shared ``lib.api.get_visible_characters_for_campaign``
helper; this module only deals with the user-supplied filter dimensions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vclient.models import Character


def filter_characters(
    characters: list[Character],
    *,
    player_id: str | None = None,
    character_class: str | None = None,
    type_filter: str | None = None,
) -> list[Character]:
    """Apply optional player/class/type filters to an already-visible character list.

    A falsy filter value means "no filter for this dimension."

    Args:
        characters: The source list (already filtered by visibility).
        player_id: Only include characters owned by this user id, if set.
        character_class: Only include characters of this class, if set.
        type_filter: Only include characters of this type (PLAYER/STORYTELLER), if set.

    Returns:
        The filtered character list in the same order.
    """
    filtered = characters
    if player_id:
        filtered = [c for c in filtered if c.user_player_id == player_id]
    if character_class:
        filtered = [c for c in filtered if c.character_class == character_class]
    if type_filter:
        filtered = [c for c in filtered if c.type == type_filter]
    return filtered


def build_filter_options(
    characters: list[Character], users_by_id: dict[str, str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Build the (player, class) option lists from the campaign's visible roster.

    Deriving options from the roster (rather than all company users / all
    possible classes) keeps the dropdowns scoped to values that can actually
    match at least one character in this campaign.

    Args:
        characters: The visible character list for the campaign.
        users_by_id: Lookup of user id → username.

    Returns:
        Tuple of (player_options, class_options) where player_options is a list
        of (user_id, username) pairs sorted by username, and class_options is a
        sorted list of distinct character_class strings.
    """
    player_ids: set[str] = set()
    classes: set[str] = set()
    for character in characters:
        if character.user_player_id:
            player_ids.add(character.user_player_id)
        if character.character_class:
            classes.add(character.character_class)

    player_options = sorted(
        ((player_id, users_by_id.get(player_id, "Unknown")) for player_id in player_ids),
        key=lambda pair: pair[1].lower(),
    )
    class_options = sorted(classes)
    return player_options, class_options
