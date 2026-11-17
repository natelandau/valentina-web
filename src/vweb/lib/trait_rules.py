"""Rules that classify traits by how the API treats them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vweb.api_client.constants import GameVersion, SpecialtyRules
    from vweb.api_client.models import CharacterTrait

DERIVED_V5_TRAIT_NAME: Final = "willpower"
ABILITIES_SECTION_NAME: Final = "abilities"
ATTRIBUTES_SECTION_NAME: Final = "attributes"

# Mirror of the API's specialty rules, which it does not expose per trait.
SPECIALTY_SECTIONS: Final[dict[SpecialtyRules, tuple[str, ...]]] = {
    "FIXED_COST": (ABILITIES_SECTION_NAME,),
    "RATING_BASED": (ATTRIBUTES_SECTION_NAME, ABILITIES_SECTION_NAME),
}
FIXED_COST_MIN_RATING: Final = 1
FIXED_COST_SPECIALTY_COST: Final = 3
SPECIALTY_MIN_RATING: Final = 4
SPECIALTY_FAVORED_MIN_RATING: Final = 3


def is_derived_trait(character_trait: CharacterTrait, game_version: GameVersion) -> bool:
    """Report whether the API computes this trait's value, so it must not be edited.

    V5 Willpower is derived from Composure and Resolve. A custom trait that happens to share
    the name is character-owned and stays editable.

    Args:
        character_trait: The character trait to classify.
        game_version: The game version of the owning character.

    Returns:
        bool: True when the trait is read-only.
    """
    trait = character_trait.trait
    return (
        game_version == "V5"
        and trait.custom_for_character_id is None
        and trait.name.strip().lower() == DERIVED_V5_TRAIT_NAME
    )


def _section_name(character_trait: CharacterTrait) -> str:
    section_name = character_trait.trait.sheet_section_name
    return section_name.strip().lower() if section_name else ""


def specialty_min_rating(
    character_trait: CharacterTrait,
    *,
    rules: SpecialtyRules,
    favored_ability_names: Iterable[str] = (),
) -> int | None:
    """Return the lowest rating at which a trait may hold specialties.

    Under FIXED_COST rules, abilities qualify at one dot. Under RATING_BASED rules, attributes
    and abilities need 4 dots, and a shared ability that the character's concept favors needs 3.
    A custom trait never counts as favored, even when its name matches a favored ability.

    Args:
        character_trait: The character trait to classify.
        rules: The company's specialty rules.
        favored_ability_names: Ability names favored by the character's concept.

    Returns:
        int | None: The minimum rating, or None when the trait's section never takes specialties.
    """
    section = _section_name(character_trait)
    if section not in SPECIALTY_SECTIONS[rules]:
        return None
    if rules == "FIXED_COST":
        return FIXED_COST_MIN_RATING
    trait = character_trait.trait
    if (
        section == ABILITIES_SECTION_NAME
        and trait.custom_for_character_id is None
        and trait.name.strip().casefold() in {n.strip().casefold() for n in favored_ability_names}
    ):
        return SPECIALTY_FAVORED_MIN_RATING
    return SPECIALTY_MIN_RATING


def accepts_specialties(
    character_trait: CharacterTrait,
    *,
    rules: SpecialtyRules,
    favored_ability_names: Iterable[str] = (),
) -> bool:
    """Report whether the trait can take a specialty at its current rating.

    Args:
        character_trait: The character trait to classify.
        rules: The company's specialty rules.
        favored_ability_names: Ability names favored by the character's concept.

    Returns:
        bool: True when specialties can be managed on this trait.
    """
    min_rating = specialty_min_rating(
        character_trait, rules=rules, favored_ability_names=favored_ability_names
    )
    return min_rating is not None and character_trait.value >= min_rating


def specialty_keep_rating(
    character_trait: CharacterTrait,
    *,
    rules: SpecialtyRules,
    favored_ability_names: Iterable[str] = (),
) -> int:
    """Return the lowest rating at which the trait keeps the specialties it has.

    The API deletes and refunds a trait's specialties when its rating drops below this, so
    callers compare a new rating against it to warn before the loss.

    Args:
        character_trait: The character trait to classify.
        rules: The company's specialty rules.
        favored_ability_names: Ability names favored by the character's concept.

    Returns:
        int: The rating, 0 when the trait has no specialties to lose.
    """
    if not character_trait.specialties:
        return 0
    min_rating = specialty_min_rating(
        character_trait, rules=rules, favored_ability_names=favored_ability_names
    )
    # A section the rules no longer allow loses its specialties on any lower rating.
    return min_rating if min_rating is not None else character_trait.value


def next_specialty_cost(character_trait: CharacterTrait, *, rules: SpecialtyRules) -> int:
    """Return what the API charges for the trait's next specialty when costs are on.

    Under FIXED_COST rules every specialty costs the same. Under RATING_BASED rules the first
    specialty on a trait is free and each further one costs the trait's current rating.

    Args:
        character_trait: The trait the specialty is added to.
        rules: The company's specialty rules.

    Returns:
        int: The points charged, before the company's cost setting and currency apply.
    """
    if rules == "FIXED_COST":
        return FIXED_COST_SPECIALTY_COST
    return character_trait.value if character_trait.specialties else 0


def specialty_sections_text(rules: SpecialtyRules) -> str:
    """Name the sheet sections whose traits can take specialties, for user-facing messages."""
    return " and ".join(SPECIALTY_SECTIONS[rules])
