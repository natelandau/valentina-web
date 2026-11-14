"""Stateless helpers for character trait editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from vweb.api_client.constants import MAX_NAME_LENGTH
from vweb.lib.character_profile import iter_character_traits

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vweb.api_client.constants import TraitModifyCurrency
    from vweb.api_client.models import (
        Character,
        CharacterFullSheet,
        CharacterTrait,
        CompanySettings,
        Trait,
    )

SPECIALTY_COST: Final = 3
SPECIALTY_NAME_MIN_LENGTH: Final = 3
SPECIALTY_NAME_MAX_LENGTH: Final = MAX_NAME_LENGTH
_PAID_CURRENCIES: Final = ("XP", "STARTING_POINTS")


def humanize_spend_type(spend_type: TraitModifyCurrency) -> str:
    """Return the spend type as lowercase words, e.g. ``starting points``."""
    return spend_type.lower().replace("_", " ")


def _trait_name_key(name: str) -> str:
    return name.strip().casefold()


def has_trait_named(full_sheet: CharacterFullSheet, name: str) -> bool:
    """Report whether a character's sheet already has a trait with this name, ignoring case."""
    wanted = _trait_name_key(name)
    return any(
        _trait_name_key(character_trait.trait.name) == wanted
        for character_trait in iter_character_traits(full_sheet)
    )


def find_standard_trait_by_name(
    traits: Iterable[Trait], *, name: str, category_id: str, character: Character
) -> Trait | None:
    """Return the standard trait whose name matches a typed name, ignoring case.

    The add-trait dropdowns only list traits for the character's class and game version,
    while the API refuses a custom trait named like any standard trait. Matching here lets
    a typed name attach the existing trait, wherever it lives, instead of failing to create
    a duplicate. When several traits share the name, prefer the one in the category the
    name was typed into, then one in the same sheet section, then one for the character's
    game version, then its class.

    Args:
        traits: The blueprint traits to search.
        name: The name the user typed.
        category_id: The category the name was typed into.
        character: The character the trait is for.

    Returns:
        Trait | None: The best match, or None when no standard trait has that name.
    """
    all_traits = list(traits)
    wanted = _trait_name_key(name)
    matches = [
        t
        for t in all_traits
        if t.custom_for_character_id is None and _trait_name_key(t.name) == wanted
    ]
    if not matches:
        return None
    section_id = next(
        (t.sheet_section_id for t in all_traits if t.category_id == category_id), None
    )
    return min(
        matches,
        key=lambda t: (
            t.category_id != category_id,
            t.sheet_section_id != section_id,
            character.game_version not in t.game_versions,
            character.character_class not in t.character_classes,
        ),
    )


def specialty_cost(
    spend_type: TraitModifyCurrency,
    settings: CompanySettings,
    character_trait: CharacterTrait | None = None,
) -> int:
    """Return the points charged to add a specialty.

    Under THRESHOLD rules the first specialty on a trait is free and each further one costs
    the trait's current rating. Under FLAT rules every specialty costs the same.

    Args:
        spend_type: The currency the specialty is bought with.
        settings: The company settings.
        character_trait: The trait the specialty is added to; required for THRESHOLD pricing.

    Returns:
        int: The points charged, 0 when free.
    """
    if not settings.specialty_xp_cost_enabled or spend_type not in _PAID_CURRENCIES:
        return 0
    if settings.specialty_rules == "THRESHOLD":
        if character_trait is None or not character_trait.specialties:
            return 0
        return character_trait.value
    return SPECIALTY_COST


def specialty_add_label(
    spend_type: TraitModifyCurrency,
    settings: CompanySettings,
    character_trait: CharacterTrait | None = None,
) -> str:
    """Return the add button label, including the cost when one is charged."""
    cost = specialty_cost(spend_type, settings, character_trait)
    if cost == 0:
        return "Add"
    unit = "XP" if spend_type == "XP" else humanize_spend_type(spend_type)
    return f"Add · {cost} {unit}"


def specialty_rules_text(
    character_trait: CharacterTrait, settings: CompanySettings, threshold: int
) -> str:
    """Explain how specialties work on this trait, for the dialog and sheet tooltips.

    Args:
        character_trait: The trait whose specialties are explained.
        settings: The company settings.
        threshold: The rating the trait needs before it can take a specialty.

    Returns:
        str: A short plain-language explanation.
    """
    name = character_trait.trait.name.strip().title()
    text = (
        f"A specialty adds one die to {name} when what you're doing fits it. "
        "The Storyteller decides when it fits."
    )
    if settings.specialty_rules != "THRESHOLD":
        return text
    text += f" {name} can take specialties at {threshold} dots."
    if settings.specialty_xp_cost_enabled:
        text += " Your first specialty is free; each one after costs XP equal to its rating."
    return text


def specialty_help_text(settings: CompanySettings) -> str:
    """Return the dialog help text, noting when XP spent is not refunded."""
    if settings.permission_recoup_xp == "DENIED":
        return "Renaming is free. Removing refunds starting points but not XP."
    if settings.permission_recoup_xp == "WITHIN_SESSION":
        return "Renaming is free. Removing refunds starting points, and XP only within the session."
    return "Renaming is free. Removing refunds whatever was paid for it."


def specialty_name_error(name: str) -> str | None:
    """Return why a specialty name is rejected, or None when it is acceptable.

    Args:
        name: The stripped specialty name submitted by the user.

    Returns:
        str | None: A user-facing message, or None for a valid name.
    """
    if not name:
        return "Specialty name is required"
    if not SPECIALTY_NAME_MIN_LENGTH <= len(name) <= SPECIALTY_NAME_MAX_LENGTH:
        return (
            f"Specialty names must be {SPECIALTY_NAME_MIN_LENGTH} to "
            f"{SPECIALTY_NAME_MAX_LENGTH} characters."
        )
    return None
