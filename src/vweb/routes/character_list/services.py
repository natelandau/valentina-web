"""Filtering and option-building for the campaign character list."""

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

    Falsy filter values pass through unchanged.
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
    """Build (player, class) option lists from the campaign's visible roster.

    Deriving options from the roster keeps the dropdowns scoped to values that
    match at least one character in this campaign.

    Returns:
        ``(player_options, class_options)`` — ``player_options`` is a list of
        ``(user_id, username)`` pairs sorted by username; ``class_options`` is a
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
