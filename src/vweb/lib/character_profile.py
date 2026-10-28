"""Shared helpers for reading and editing a character's profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vclient.exceptions import (
    APIError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RequestValidationError,
    ValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from vclient.models import CharacterFullSheet, CharacterTrait

# NotFoundError included so a stale page acting on an already-deleted trait
# (or missing character) surfaces a flash instead of a 500.
TRAIT_API_ERRORS: tuple[type[APIError], ...] = (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
    RequestValidationError,
)


def iter_character_traits(full_sheet: CharacterFullSheet) -> Iterator[CharacterTrait]:
    """Yield every character trait on a sheet in display order.

    Category traits come before their subcategory traits, so callers that
    keep the first match see the same trait the sheet shows first.
    """
    for section in full_sheet.sections:
        for category in section.categories:
            yield from category.character_traits
            for subcategory in category.subcategories:
                yield from subcategory.character_traits


def find_character_trait(
    full_sheet: CharacterFullSheet, character_trait_id: str
) -> CharacterTrait | None:
    """Find a character trait by id in a full sheet's categories and subcategories."""
    return next(
        (
            character_trait
            for character_trait in iter_character_traits(full_sheet)
            if character_trait.id == character_trait_id
        ),
        None,
    )
