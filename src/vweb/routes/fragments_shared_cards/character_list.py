"""Filtering and filter-option helpers for the shared character list card.

The shared ``CharacterListCard`` fragment (and its endpoint) narrow an
already-visibility-filtered roster by player, class, and type. These pure
helpers live alongside their sole consumer, the cross-cutting card endpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vweb.lib.jinja import CHARACTER_TYPE_LABELS

if TYPE_CHECKING:
    from vclient.models import Character

# Player-facing character types in display order, shared with CharacterTypeBadge.
CHARACTER_TYPE_ORDER: tuple[str, ...] = ("PLAYER", "NPC", "STORYTELLER")


def filter_characters(
    characters: list[Character],
    *,
    player_id: str | None = None,
    character_class: str | None = None,
    type_filter: str | None = None,
) -> list[Character]:
    """Apply optional player/class/type filters to an already-visible character list.

    Falsy filter values pass through unchanged.

    Args:
        characters: The visibility-filtered roster to narrow.
        player_id: Keep only characters owned by this user id.
        character_class: Keep only characters of this class.
        type_filter: Keep only characters of this type.

    Returns:
        The narrowed list, in the same order as the input.
    """
    filtered = characters
    if player_id:
        filtered = [character for character in filtered if character.user_player_id == player_id]
    if character_class:
        filtered = [
            character for character in filtered if character.character_class == character_class
        ]
    if type_filter:
        filtered = [character for character in filtered if character.type == type_filter]
    return filtered


def build_filter_options(
    characters: list[Character], users_by_id: dict[str, str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Build ``(player, class)`` option lists from the roster the card will show.

    Deriving options from the roster keeps each dropdown scoped to values that
    match at least one character in the current list, which is also what lets the
    card hide a filter when only one value is present.

    Args:
        characters: The roster (pre-filter) the options are derived from.
        users_by_id: Lookup of user id → username for player labels.

    Returns:
        ``(player_options, class_options)``. ``player_options`` is a list of
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


def present_type_options(characters: list[Character]) -> list[tuple[str, str]]:
    """Build ``(value, label)`` type options for the types present in the roster.

    Only labeled player-facing types are returned, in display order, so the
    card can show a type filter exactly when more than one type is present.

    Args:
        characters: The roster (pre-filter) to inspect.

    Returns:
        A list of ``(type_value, label)`` pairs in ``CHARACTER_TYPE_ORDER``.
    """
    present = {character.type for character in characters}
    return [
        (character_type, CHARACTER_TYPE_LABELS[character_type])
        for character_type in CHARACTER_TYPE_ORDER
        if character_type in present
    ]
