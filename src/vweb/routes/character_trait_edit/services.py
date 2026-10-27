"""Stateless helpers for character trait editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from vclient.exceptions import (
    APIError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RequestValidationError,
    ValidationError,
)

if TYPE_CHECKING:
    from vclient.constants import TraitModifyCurrency
    from vclient.models import CharacterFullSheet, CharacterTrait, CompanySettings

# NotFoundError included so a stale page acting on an already-deleted trait
# (or missing character) surfaces a flash instead of a 500.
TRAIT_API_ERRORS: tuple[type[APIError], ...] = (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
    RequestValidationError,
)

SPECIALTY_COST: Final = 3
SPECIALTY_NAME_MIN_LENGTH: Final = 3
SPECIALTY_NAME_MAX_LENGTH: Final = 50
_PAID_CURRENCIES: Final = ("XP", "STARTING_POINTS")


def humanize_spend_type(spend_type: TraitModifyCurrency) -> str:
    """Return the spend type as lowercase words, e.g. ``starting points``."""
    return spend_type.lower().replace("_", " ")


def specialty_cost(spend_type: TraitModifyCurrency, settings: CompanySettings) -> int:
    """Return the points charged to add a specialty."""
    if settings.specialty_xp_cost_enabled and spend_type in _PAID_CURRENCIES:
        return SPECIALTY_COST
    return 0


def specialty_add_label(spend_type: TraitModifyCurrency, settings: CompanySettings) -> str:
    """Return the add button label, including the cost when one is charged."""
    if specialty_cost(spend_type, settings) == 0:
        return "Add"
    unit = "XP" if spend_type == "XP" else humanize_spend_type(spend_type)
    return f"Add · {SPECIALTY_COST} {unit}"


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


def find_character_trait(
    full_sheet: CharacterFullSheet, character_trait_id: str
) -> CharacterTrait | None:
    """Find a character trait by id in a full sheet's categories and subcategories."""
    for section in full_sheet.sections:
        for category in section.categories:
            groups = [category.character_traits]
            groups.extend(sub.character_traits for sub in category.subcategories)
            for group in groups:
                for character_trait in group:
                    if character_trait.id == character_trait_id:
                        return character_trait
    return None
