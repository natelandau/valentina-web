"""Polyfactory model factories for every API client response model."""

from typing import Any

from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.field_meta import FieldMeta
from pydantic import BaseModel

from vweb.api_client.models import (
    AppleProfile,
    Asset,
    AuditLog,
    AuditLogDetail,
    BulkAssignTraitFailure,
    BulkAssignTraitResponse,
    BulkAssignTraitSuccess,
    Campaign,
    CampaignBook,
    CampaignBookDetail,
    CampaignChapter,
    CampaignChapterDetail,
    Character,
    CharacterConcept,
    CharacterDetail,
    CharacterFullSheet,
    CharacterTrait,
    CharacterTraitValueOptionsResponse,
    Company,
    CompanyPermissions,
    CounterTracker,
    Diceroll,
    DictionaryTerm,
    FullSheetTraitCategory,
    FullSheetTraitSection,
    FullSheetTraitSubcategory,
    GitHubProfile,
    GoogleProfile,
    Health,
    HealthLevel,
    IdentityResolution,
    InventoryItem,
    NewCompanyResponse,
    Note,
    Quickroll,
    RollStatistics,
    SheetSection,
    StainsTracker,
    SystemHealth,
    Trait,
    TraitCategory,
    TraitSubcategory,
    User,
    UserDetail,
    UserLookupResult,
    VampireClan,
    WerewolfAuspice,
    WerewolfTribe,
)
from vweb.api_client.models.character_autogen import ChargenSessionResponse
from vweb.api_client.models.companies import CompanySettings
from vweb.api_client.models.users import CampaignExperience


class _GeneratedFieldsFactory[T: BaseModel](ModelFactory[T]):
    """Factory that uses model defaults except for the fields named in ``__generated_fields__``.

    ``__use_defaults__`` otherwise wins over a declared ``Use`` or ``PostGenerated`` for any
    field that has a default.
    """

    __is_base_factory__ = True
    __use_defaults__ = True
    __generated_fields__: frozenset[str] = frozenset()

    @classmethod
    def should_use_default_value(cls, field_meta: FieldMeta) -> bool:
        """Use the model default unless the field is listed in ``__generated_fields__``."""
        if field_meta.name in cls.__generated_fields__:
            return False
        return super().should_use_default_value(field_meta)


class AuditLogFactory(ModelFactory[AuditLog]):
    __model__ = AuditLog
    __use_defaults__ = True


class AuditLogDetailFactory(ModelFactory[AuditLogDetail]):
    __model__ = AuditLogDetail
    __use_defaults__ = True


class AppleProfileFactory(ModelFactory[AppleProfile]):
    __model__ = AppleProfile
    __use_defaults__ = True


class AssetFactory(ModelFactory[Asset]):
    __model__ = Asset
    __use_defaults__ = True


class BulkAssignTraitFailureFactory(ModelFactory[BulkAssignTraitFailure]):
    __model__ = BulkAssignTraitFailure
    __use_defaults__ = True


class BulkAssignTraitResponseFactory(ModelFactory[BulkAssignTraitResponse]):
    __model__ = BulkAssignTraitResponse
    __use_defaults__ = True


class BulkAssignTraitSuccessFactory(ModelFactory[BulkAssignTraitSuccess]):
    __model__ = BulkAssignTraitSuccess
    __use_defaults__ = True


class CampaignFactory(ModelFactory[Campaign]):
    __model__ = Campaign
    __use_defaults__ = True


class CampaignBookFactory(ModelFactory[CampaignBook]):
    __model__ = CampaignBook
    __use_defaults__ = True


class CampaignBookDetailFactory(ModelFactory[CampaignBookDetail]):
    __model__ = CampaignBookDetail
    __use_defaults__ = True


class CampaignChapterFactory(ModelFactory[CampaignChapter]):
    __model__ = CampaignChapter
    __use_defaults__ = True


class CampaignChapterDetailFactory(ModelFactory[CampaignChapterDetail]):
    __model__ = CampaignChapterDetail
    __use_defaults__ = True


class CampaignExperienceFactory(ModelFactory[CampaignExperience]):
    __model__ = CampaignExperience
    __use_defaults__ = True


def _build_health() -> Health:
    """Return a fake health track."""
    return HealthFactory.build()


class CharacterFactory(_GeneratedFieldsFactory[Character]):
    __model__ = Character
    __generated_fields__ = frozenset({"health"})
    # The API always sends health; the model default of None only covers older APIs.
    health = Use(_build_health)
    # A random type changes who may edit the character, so tests choose it on purpose
    type = "PLAYER"


class CharacterDetailFactory(_GeneratedFieldsFactory[CharacterDetail]):
    __model__ = CharacterDetail
    __generated_fields__ = frozenset({"health"})
    health = Use(_build_health)
    type = "PLAYER"


class CharacterConceptFactory(ModelFactory[CharacterConcept]):
    __model__ = CharacterConcept
    __use_defaults__ = True


class CharacterFullSheetFactory(ModelFactory[CharacterFullSheet]):
    __model__ = CharacterFullSheet
    __use_defaults__ = True


class CharacterTraitFactory(_GeneratedFieldsFactory[CharacterTrait]):
    __model__ = CharacterTrait
    __generated_fields__ = frozenset({"tracker"})

    @classmethod
    def tracker(cls) -> CounterTracker | StainsTracker | None:
        """Return a random tracker variant, or None for a trait without a tracker."""
        factory = cls.__random__.choice([CounterTrackerFactory, StainsTrackerFactory, None])
        return factory.build() if factory is not None else None


class CharacterTraitValueOptionsResponseFactory(
    ModelFactory[CharacterTraitValueOptionsResponse],
):
    __model__ = CharacterTraitValueOptionsResponse
    __use_defaults__ = True


class ChargenSessionResponseFactory(ModelFactory[ChargenSessionResponse]):
    __model__ = ChargenSessionResponse
    __use_defaults__ = True


def _build_locked_company_settings() -> CompanySettings:
    """Build settings that reserve every permission for storytellers.

    Random permissions would let a player pass role checks through company settings.
    """
    return CompanySettings(
        id="settings-1",
        character_autogen_xp_cost=0,
        character_autogen_num_choices=3,
        character_autogen_starting_points=0,
        permission_manage_campaign="STORYTELLER",
        permission_manage_npc="STORYTELLER",
        permission_grant_xp="STORYTELLER",
        permission_free_trait_changes="STORYTELLER",
        permission_recoup_xp="DENIED",
    )


class CompanyFactory(ModelFactory[Company]):
    __model__ = Company
    __use_defaults__ = True
    settings = Use(_build_locked_company_settings)


class CompanyPermissionsFactory(ModelFactory[CompanyPermissions]):
    __model__ = CompanyPermissions
    __use_defaults__ = True


class DicerollFactory(ModelFactory[Diceroll]):
    __model__ = Diceroll
    __use_defaults__ = True


class DictionaryTermFactory(ModelFactory[DictionaryTerm]):
    __model__ = DictionaryTerm
    __use_defaults__ = True


class FullSheetTraitCategoryFactory(ModelFactory[FullSheetTraitCategory]):
    __model__ = FullSheetTraitCategory
    __use_defaults__ = True


class FullSheetTraitSectionFactory(ModelFactory[FullSheetTraitSection]):
    __model__ = FullSheetTraitSection
    __use_defaults__ = True


class FullSheetTraitSubcategoryFactory(ModelFactory[FullSheetTraitSubcategory]):
    __model__ = FullSheetTraitSubcategory
    __use_defaults__ = True


class GitHubProfileFactory(ModelFactory[GitHubProfile]):
    __model__ = GitHubProfile
    __use_defaults__ = True


class GoogleProfileFactory(ModelFactory[GoogleProfile]):
    __model__ = GoogleProfile
    __use_defaults__ = True


class IdentityResolutionFactory(ModelFactory[IdentityResolution]):
    __model__ = IdentityResolution
    __use_defaults__ = True


class InventoryItemFactory(ModelFactory[InventoryItem]):
    __model__ = InventoryItem
    __use_defaults__ = True


class NewCompanyResponseFactory(ModelFactory[NewCompanyResponse]):
    __model__ = NewCompanyResponse
    __use_defaults__ = True


class NoteFactory(ModelFactory[Note]):
    __model__ = Note
    __use_defaults__ = True


class QuickrollFactory(ModelFactory[Quickroll]):
    __model__ = Quickroll
    __use_defaults__ = True


class RollStatisticsFactory(ModelFactory[RollStatistics]):
    __model__ = RollStatistics
    __use_defaults__ = True


class SheetSectionFactory(ModelFactory[SheetSection]):
    __model__ = SheetSection
    __use_defaults__ = True


class SystemHealthFactory(ModelFactory[SystemHealth]):
    __model__ = SystemHealth
    __use_defaults__ = True


class TraitCategoryFactory(ModelFactory[TraitCategory]):
    __model__ = TraitCategory
    __use_defaults__ = True


class TraitSubcategoryFactory(ModelFactory[TraitSubcategory]):
    __model__ = TraitSubcategory
    __use_defaults__ = True


class TraitFactory(ModelFactory[Trait]):
    __model__ = Trait
    __use_defaults__ = True


class UserFactory(ModelFactory[User]):
    __model__ = User
    __use_defaults__ = True
    role = "PLAYER"


class UserLookupResultFactory(ModelFactory[UserLookupResult]):
    __model__ = UserLookupResult
    __use_defaults__ = True
    role = "PLAYER"


class UserDetailFactory(ModelFactory[UserDetail]):
    __model__ = UserDetail
    __use_defaults__ = True
    role = "PLAYER"


class VampireClanFactory(ModelFactory[VampireClan]):
    __model__ = VampireClan
    __use_defaults__ = True


class WerewolfAuspiceFactory(ModelFactory[WerewolfAuspice]):
    __model__ = WerewolfAuspice
    __use_defaults__ = True


class WerewolfTribeFactory(ModelFactory[WerewolfTribe]):
    __model__ = WerewolfTribe
    __use_defaults__ = True


class CounterTrackerFactory(ModelFactory[CounterTracker]):
    __model__ = CounterTracker
    __use_defaults__ = True

    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> CounterTracker:  # noqa: FBT001, FBT002
        """Build a counter whose ``current`` never exceeds its ``size``."""
        size: int = kwargs.get("size", cls.__random__.randint(1, 10))
        kwargs = {"size": size, "current": cls.__random__.randint(0, size), **kwargs}
        return super().build(factory_use_construct, **kwargs)


class HealthFactory(ModelFactory[Health]):
    __model__ = Health
    __use_defaults__ = True

    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Health:  # noqa: FBT001, FBT002
        """Build a V4 or V5 health track whose damage fits it and whose V4 levels match it."""
        size: int = kwargs.get("size", cls.__random__.randint(1, 10))
        damage: int | None = kwargs.get("damage", cls.__random__.randint(0, size))
        levels: list[HealthLevel] | None = kwargs.get("levels")
        if "levels" not in kwargs and cls.__random__.choice((True, False)):
            levels = [
                HealthLevel(name=f"Level {i + 1}", marked=None if damage is None else i < damage)
                for i in range(size)
            ]
        kwargs = {"size": size, "damage": damage, "levels": levels, **kwargs}
        return super().build(factory_use_construct, **kwargs)


class HealthLevelFactory(ModelFactory[HealthLevel]):
    __model__ = HealthLevel
    __use_defaults__ = True

    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> HealthLevel:  # noqa: FBT001, FBT002
        """Build a health level in the current API shape, with ``marked`` set."""
        kwargs = {"marked": cls.__random__.choice((True, False)), **kwargs}
        return super().build(factory_use_construct, **kwargs)


class StainsTrackerFactory(ModelFactory[StainsTracker]):
    __model__ = StainsTracker
    __use_defaults__ = True

    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> StainsTracker:  # noqa: FBT001, FBT002
        """Build a stains tracker whose capacity is 10 minus Humanity and holds its stains."""
        humanity: int = kwargs.get("humanity", cls.__random__.randint(0, 10))
        capacity: int = kwargs.get("stain_capacity", 10 - humanity)
        kwargs = {
            "humanity": humanity,
            "stain_capacity": capacity,
            "stains": cls.__random__.randint(0, capacity),
            **kwargs,
        }
        return super().build(factory_use_construct, **kwargs)


__all__ = [
    "AppleProfileFactory",
    "AssetFactory",
    "AuditLogDetailFactory",
    "AuditLogFactory",
    "BulkAssignTraitFailureFactory",
    "BulkAssignTraitResponseFactory",
    "BulkAssignTraitSuccessFactory",
    "CampaignBookDetailFactory",
    "CampaignBookFactory",
    "CampaignChapterDetailFactory",
    "CampaignChapterFactory",
    "CampaignExperienceFactory",
    "CampaignFactory",
    "CharacterConceptFactory",
    "CharacterDetailFactory",
    "CharacterFactory",
    "CharacterFullSheetFactory",
    "CharacterTraitFactory",
    "CharacterTraitValueOptionsResponseFactory",
    "ChargenSessionResponseFactory",
    "CompanyFactory",
    "CompanyPermissionsFactory",
    "CounterTrackerFactory",
    "DicerollFactory",
    "DictionaryTermFactory",
    "FullSheetTraitCategoryFactory",
    "FullSheetTraitSectionFactory",
    "FullSheetTraitSubcategoryFactory",
    "GitHubProfileFactory",
    "GoogleProfileFactory",
    "HealthFactory",
    "HealthLevelFactory",
    "IdentityResolutionFactory",
    "InventoryItemFactory",
    "NewCompanyResponseFactory",
    "NoteFactory",
    "QuickrollFactory",
    "RollStatisticsFactory",
    "SheetSectionFactory",
    "StainsTrackerFactory",
    "SystemHealthFactory",
    "TraitCategoryFactory",
    "TraitFactory",
    "TraitSubcategoryFactory",
    "UserDetailFactory",
    "UserFactory",
    "UserLookupResultFactory",
    "VampireClanFactory",
    "WerewolfAuspiceFactory",
    "WerewolfTribeFactory",
]
