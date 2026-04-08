"""Global API options cache.

Fetch all enumerations and configuration values from the API's options endpoint
and cache them as typed dataclasses. Shared across all users with a 1-hour TTL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vclient import sync_options_service

from vweb.constants import CACHE_OPTIONS_TTL
from vweb.extensions import cache

_CACHE_OPTIONS_KEY: str = "api_options"


@dataclass(frozen=True)
class CompanyOptions:
    """Company-level permission enumerations."""

    company_permission: list[str] = field(default_factory=list)
    permission_manage_campaign: list[str] = field(default_factory=list)
    permissions_grant_xp: list[str] = field(default_factory=list)
    permissions_free_trait_changes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CharacterOptions:
    """Character-related enumerations for classes, types, and specializations."""

    ability_focus: list[str] = field(default_factory=list)
    autogen_experience_level: list[str] = field(default_factory=list)
    character_class: list[str] = field(default_factory=list)
    character_status: list[str] = field(default_factory=list)
    character_type: list[str] = field(default_factory=list)
    game_version: list[str] = field(default_factory=list)
    hunter_creed: list[str] = field(default_factory=list)
    hunter_edge_type: list[str] = field(default_factory=list)
    inventory_item_type: list[str] = field(default_factory=list)
    specialty_type: list[str] = field(default_factory=list)
    trait_modify_currency: list[str] = field(default_factory=list)
    werewolf_renown: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AutogenOptions:
    """Autogen-related enumerations."""

    autogen_percentile_chance: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UserOptions:
    """User role enumerations."""

    user_role: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GameplayOptions:
    """Gameplay enumerations for dice and roll results."""

    dice_size: list[int] = field(default_factory=list)
    roll_result_type: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssetOptions:
    """Asset type and parent type enumerations."""

    asset_type: list[str] = field(default_factory=list)
    asset_parent_type: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApiOptions:
    """All API enumerations and configuration values.

    Top-level container returned by ``get_options()``. Each field groups
    related enumerations into a typed sub-dataclass.
    """

    companies: CompanyOptions = field(default_factory=CompanyOptions)
    characters: CharacterOptions = field(default_factory=CharacterOptions)
    autogen: AutogenOptions = field(default_factory=AutogenOptions)
    users: UserOptions = field(default_factory=UserOptions)
    gameplay: GameplayOptions = field(default_factory=GameplayOptions)
    assets: AssetOptions = field(default_factory=AssetOptions)


def _parse_options(raw: dict) -> ApiOptions:
    """Parse the raw API response dict into typed dataclasses.

    Maps PascalCase keys from the API to snake_case dataclass fields.

    Args:
        raw: The raw dictionary returned by ``sync_options_service().get_options()``.

    Returns:
        A fully populated ApiOptions instance.
    """
    companies_raw = raw.get("companies", {})
    characters_raw = raw.get("characters", {})
    autogen_raw = raw.get("character_autogeneration", {})
    users_raw = raw.get("users", {})
    gameplay_raw = raw.get("gameplay", {})

    return ApiOptions(
        companies=CompanyOptions(
            company_permission=companies_raw.get("CompanyPermission", []),
            permission_manage_campaign=companies_raw.get("PermissionManageCampaign", []),
            permissions_grant_xp=companies_raw.get("PermissionsGrantXP", []),
            permissions_free_trait_changes=companies_raw.get("PermissionsFreeTraitChanges", []),
        ),
        characters=CharacterOptions(
            ability_focus=characters_raw.get("AbilityFocus", []),
            autogen_experience_level=characters_raw.get("AutoGenExperienceLevel", []),
            character_class=characters_raw.get("CharacterClass", []),
            character_status=characters_raw.get("CharacterStatus", []),
            character_type=characters_raw.get("CharacterType", []),
            game_version=characters_raw.get("GameVersion", []),
            hunter_creed=characters_raw.get("HunterCreed", []),
            hunter_edge_type=characters_raw.get("HunterEdgeType", []),
            inventory_item_type=characters_raw.get("InventoryItemType", []),
            specialty_type=characters_raw.get("SpecialtyType", []),
            trait_modify_currency=characters_raw.get("TraitModifyCurrency", []),
            werewolf_renown=characters_raw.get("WerewolfRenown", []),
        ),
        autogen=AutogenOptions(
            autogen_percentile_chance=autogen_raw.get("CharacterClassPercentileChance", []),
        ),
        users=UserOptions(
            user_role=users_raw.get("UserRole", []),
        ),
        gameplay=GameplayOptions(
            dice_size=gameplay_raw.get("DiceSize", []),
            roll_result_type=gameplay_raw.get("RollResultType", []),
        ),
    )


def get_options() -> ApiOptions:
    """Return all API options, fetching from the API on cache miss.

    Cached with 1-hour TTL. Shared across all users and requests.

    Returns:
        A typed ApiOptions instance containing all enumerations.
    """
    cached: ApiOptions | None = cache.get(_CACHE_OPTIONS_KEY)
    if cached is not None:
        return cached

    raw = sync_options_service().get_options()
    result = _parse_options(raw)
    cache.set(_CACHE_OPTIONS_KEY, result, timeout=CACHE_OPTIONS_TTL)
    return result


def clear_options_cache() -> None:
    """Remove the cached options, forcing a fresh API fetch on next access."""
    cache.delete(_CACHE_OPTIONS_KEY)
