"""Every Valentina API route the client calls, stated once.

A ``RouteSpec`` names a route's HTTP method, path template, response style, and
response model. Services build requests and parse responses from it, and
``FakeVClient`` serves fake responses from the same specs, so the two cannot
disagree about a route.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    _TRACKER_ADAPTER,
    Asset,
    AuditLog,
    AuditLogDetail,
    BulkAssignTraitResponse,
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
    Health,
    IdentityResolution,
    InventoryItem,
    NewCompanyResponse,
    Note,
    Quickroll,
    RollStatistics,
    SheetSection,
    SystemHealth,
    Tracker,
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
from vweb.api_client.models.users import CampaignExperience

type HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class ResponseStyle(StrEnum):
    """Shape of a route's response body."""

    PAGINATED = "paginated"
    SINGLE = "single"
    LIST = "list"
    NO_CONTENT = "no_content"
    RAW_JSON = "raw_json"


PAGINATED = ResponseStyle.PAGINATED
SINGLE = ResponseStyle.SINGLE
LIST = ResponseStyle.LIST
NO_CONTENT = ResponseStyle.NO_CONTENT
RAW_JSON = ResponseStyle.RAW_JSON


@dataclass(frozen=True, slots=True)
class RouteSpec[M: BaseModel]:
    """Describe one API route: how to call it and how to read its response.

    Attributes:
        method: HTTP method.
        pattern: Path template from ``Endpoints``.
        style: Shape of the response body.
        model_class: Model for each response object, or None for NO_CONTENT and RAW_JSON
            routes. For a route that returns a union, the variant ``FakeVClient`` serves
            by default.
        adapter: Validator for a route whose response is a union of models. When set,
            responses are parsed with it instead of ``model_class``.
    """

    method: HttpMethod
    pattern: str
    style: ResponseStyle
    model_class: type[M] | None = None
    adapter: TypeAdapter[M] | None = None

    def parse(self, data: Any) -> M:
        """Validate one response object into this route's model.

        Args:
            data: A decoded JSON object from the response body.

        Returns:
            The validated model instance.

        Raises:
            TypeError: If the route has no response model.
        """
        if self.adapter is not None:
            return self.adapter.validate_python(data)
        if self.model_class is None:
            msg = f"Route {self.method} {self.pattern} has no response model"
            raise TypeError(msg)
        return self.model_class.model_validate(data)


class Routes:
    """Named specs for every API route the client calls.

    Services call routes through these specs. In tests, pass them to
    ``FakeVClient.set_response()`` and ``set_error()`` to override the default fake
    response for a route.

    Example::

        from vweb.api_client.testing import FakeVClient, Routes

        with FakeVClient() as client:
            # Override the campaigns list endpoint
            client.set_response(Routes.CAMPAIGNS_LIST, items=[])

            # Make a specific route return an error
            client.set_error(Routes.CHARACTERS_GET, status_code=404, detail="Not found")
    """

    # Health
    HEALTH_GET = RouteSpec("GET", Endpoints.HEALTH, SINGLE, SystemHealth)

    # Companies
    COMPANIES_LIST = RouteSpec("GET", Endpoints.COMPANIES, PAGINATED, Company)
    COMPANIES_GET = RouteSpec("GET", Endpoints.COMPANY, SINGLE, Company)
    COMPANIES_CREATE = RouteSpec("POST", Endpoints.COMPANIES, SINGLE, NewCompanyResponse)
    COMPANIES_UPDATE = RouteSpec("PATCH", Endpoints.COMPANY, SINGLE, Company)
    COMPANIES_DELETE = RouteSpec("DELETE", Endpoints.COMPANY, NO_CONTENT, None)
    COMPANIES_ACCESS = RouteSpec("POST", Endpoints.COMPANY_ACCESS, SINGLE, CompanyPermissions)
    COMPANIES_STATISTICS = RouteSpec("GET", Endpoints.COMPANY_STATISTICS, SINGLE, RollStatistics)
    COMPANIES_AUDIT_LOGS_LIST = RouteSpec("GET", Endpoints.COMPANY_AUDIT_LOGS, PAGINATED, AuditLog)
    # The same route with ``include=request_details``, which adds request forensics to each entry
    COMPANIES_AUDIT_LOGS_LIST_DETAIL = RouteSpec(
        "GET", Endpoints.COMPANY_AUDIT_LOGS, PAGINATED, AuditLogDetail
    )

    # Users
    USERS_LIST = RouteSpec("GET", Endpoints.USERS, PAGINATED, User)
    USERS_UNAPPROVED_LIST = RouteSpec("GET", Endpoints.USERS_UNAPPROVED_LIST, PAGINATED, User)
    USERS_GET = RouteSpec("GET", Endpoints.USER, SINGLE, UserDetail)
    USERS_CREATE = RouteSpec("POST", Endpoints.USERS, SINGLE, User)
    USERS_UPDATE = RouteSpec("PATCH", Endpoints.USER, SINGLE, User)
    USERS_DELETE = RouteSpec("DELETE", Endpoints.USER, NO_CONTENT, None)
    USERS_APPROVE = RouteSpec("POST", Endpoints.USER_APPROVE, SINGLE, User)
    USERS_DENY = RouteSpec("POST", Endpoints.USER_DENY, NO_CONTENT, None)
    USERS_MERGE = RouteSpec("POST", Endpoints.USER_MERGE, SINGLE, User)
    USERS_IDENTITY_LINK = RouteSpec("POST", Endpoints.USER_IDENTITIES, SINGLE, User)
    USERS_IDENTITY_UNLINK = RouteSpec("DELETE", Endpoints.USER_IDENTITY, SINGLE, User)

    USERS_STATISTICS = RouteSpec("GET", Endpoints.USER_STATISTICS, SINGLE, RollStatistics)
    # User lookup (cross-company)
    USERS_LOOKUP = RouteSpec("GET", Endpoints.USERS_LOOKUP, LIST, UserLookupResult)

    # Identity resolution (no On-Behalf-Of required)
    IDENTITY_IDENTIFY = RouteSpec("POST", Endpoints.AUTH_IDENTIFY, SINGLE, IdentityResolution)

    # User assets
    USERS_ASSETS_LIST = RouteSpec("GET", Endpoints.USER_ASSETS, PAGINATED, Asset)
    USERS_ASSETS_GET = RouteSpec("GET", Endpoints.USER_ASSET, SINGLE, Asset)
    USERS_ASSETS_DELETE = RouteSpec("DELETE", Endpoints.USER_ASSET, NO_CONTENT, None)
    USERS_ASSETS_UPLOAD = RouteSpec("POST", Endpoints.USER_ASSET_UPLOAD, SINGLE, Asset)

    # User avatar
    USERS_AVATAR_UPLOAD = RouteSpec("PUT", Endpoints.USER_AVATAR, SINGLE, User)
    USERS_AVATAR_DELETE = RouteSpec("DELETE", Endpoints.USER_AVATAR, SINGLE, User)

    # User experience
    USERS_EXPERIENCE_GET = RouteSpec(
        "GET", Endpoints.USER_EXPERIENCE_CAMPAIGN, SINGLE, CampaignExperience
    )
    USERS_EXPERIENCE_XP_ADD = RouteSpec(
        "POST", Endpoints.USER_EXPERIENCE_XP_ADD, SINGLE, CampaignExperience
    )
    USERS_EXPERIENCE_XP_REMOVE = RouteSpec(
        "POST", Endpoints.USER_EXPERIENCE_XP_REMOVE, SINGLE, CampaignExperience
    )
    USERS_EXPERIENCE_CP_ADD = RouteSpec(
        "POST", Endpoints.USER_EXPERIENCE_CP_ADD, SINGLE, CampaignExperience
    )

    # User notes
    USERS_NOTES_LIST = RouteSpec("GET", Endpoints.USER_NOTES, PAGINATED, Note)
    USERS_NOTES_GET = RouteSpec("GET", Endpoints.USER_NOTE, SINGLE, Note)
    USERS_NOTES_CREATE = RouteSpec("POST", Endpoints.USER_NOTES, SINGLE, Note)
    USERS_NOTES_UPDATE = RouteSpec("PATCH", Endpoints.USER_NOTE, SINGLE, Note)
    USERS_NOTES_DELETE = RouteSpec("DELETE", Endpoints.USER_NOTE, NO_CONTENT, None)

    # User quickrolls
    USERS_QUICKROLLS_LIST = RouteSpec("GET", Endpoints.USER_QUICKROLLS, PAGINATED, Quickroll)
    USERS_QUICKROLLS_GET = RouteSpec("GET", Endpoints.USER_QUICKROLL, SINGLE, Quickroll)
    USERS_QUICKROLLS_CREATE = RouteSpec("POST", Endpoints.USER_QUICKROLLS, SINGLE, Quickroll)
    USERS_QUICKROLLS_UPDATE = RouteSpec("PATCH", Endpoints.USER_QUICKROLL, SINGLE, Quickroll)
    USERS_QUICKROLLS_DELETE = RouteSpec("DELETE", Endpoints.USER_QUICKROLL, NO_CONTENT, None)

    # Campaigns
    CAMPAIGNS_LIST = RouteSpec("GET", Endpoints.CAMPAIGNS, PAGINATED, Campaign)
    CAMPAIGNS_GET = RouteSpec("GET", Endpoints.CAMPAIGN, SINGLE, Campaign)
    CAMPAIGNS_CREATE = RouteSpec("POST", Endpoints.CAMPAIGNS, SINGLE, Campaign)
    CAMPAIGNS_UPDATE = RouteSpec("PATCH", Endpoints.CAMPAIGN, SINGLE, Campaign)
    CAMPAIGNS_DELETE = RouteSpec("DELETE", Endpoints.CAMPAIGN, NO_CONTENT, None)
    CAMPAIGNS_STATISTICS = RouteSpec("GET", Endpoints.CAMPAIGN_STATISTICS, SINGLE, RollStatistics)

    # Campaign assets
    CAMPAIGNS_ASSETS_LIST = RouteSpec("GET", Endpoints.CAMPAIGN_ASSETS, PAGINATED, Asset)
    CAMPAIGNS_ASSETS_GET = RouteSpec("GET", Endpoints.CAMPAIGN_ASSET, SINGLE, Asset)
    CAMPAIGNS_ASSETS_DELETE = RouteSpec("DELETE", Endpoints.CAMPAIGN_ASSET, NO_CONTENT, None)
    CAMPAIGNS_ASSETS_UPLOAD = RouteSpec("POST", Endpoints.CAMPAIGN_ASSET_UPLOAD, SINGLE, Asset)

    # Campaign notes
    CAMPAIGNS_NOTES_LIST = RouteSpec("GET", Endpoints.CAMPAIGN_NOTES, PAGINATED, Note)
    CAMPAIGNS_NOTES_GET = RouteSpec("GET", Endpoints.CAMPAIGN_NOTE, SINGLE, Note)
    CAMPAIGNS_NOTES_CREATE = RouteSpec("POST", Endpoints.CAMPAIGN_NOTES, SINGLE, Note)
    CAMPAIGNS_NOTES_UPDATE = RouteSpec("PATCH", Endpoints.CAMPAIGN_NOTE, SINGLE, Note)
    CAMPAIGNS_NOTES_DELETE = RouteSpec("DELETE", Endpoints.CAMPAIGN_NOTE, NO_CONTENT, None)

    # Books
    BOOKS_LIST = RouteSpec("GET", Endpoints.CAMPAIGN_BOOKS, PAGINATED, CampaignBook)
    BOOKS_GET = RouteSpec("GET", Endpoints.CAMPAIGN_BOOK, SINGLE, CampaignBookDetail)
    BOOKS_CREATE = RouteSpec("POST", Endpoints.CAMPAIGN_BOOKS, SINGLE, CampaignBook)
    BOOKS_UPDATE = RouteSpec("PATCH", Endpoints.CAMPAIGN_BOOK, SINGLE, CampaignBook)
    BOOKS_DELETE = RouteSpec("DELETE", Endpoints.CAMPAIGN_BOOK, NO_CONTENT, None)
    BOOKS_RENUMBER = RouteSpec("PUT", Endpoints.CAMPAIGN_BOOK_NUMBER, SINGLE, CampaignBook)

    # Book notes
    BOOKS_NOTES_LIST = RouteSpec("GET", Endpoints.BOOK_NOTES, PAGINATED, Note)
    BOOKS_NOTES_GET = RouteSpec("GET", Endpoints.BOOK_NOTE, SINGLE, Note)
    BOOKS_NOTES_CREATE = RouteSpec("POST", Endpoints.BOOK_NOTES, SINGLE, Note)
    BOOKS_NOTES_UPDATE = RouteSpec("PATCH", Endpoints.BOOK_NOTE, SINGLE, Note)
    BOOKS_NOTES_DELETE = RouteSpec("DELETE", Endpoints.BOOK_NOTE, NO_CONTENT, None)

    # Book assets
    BOOKS_ASSETS_LIST = RouteSpec("GET", Endpoints.BOOK_ASSETS, PAGINATED, Asset)
    BOOKS_ASSETS_GET = RouteSpec("GET", Endpoints.BOOK_ASSET, SINGLE, Asset)
    BOOKS_ASSETS_DELETE = RouteSpec("DELETE", Endpoints.BOOK_ASSET, NO_CONTENT, None)
    BOOKS_ASSETS_UPLOAD = RouteSpec("POST", Endpoints.BOOK_ASSET_UPLOAD, SINGLE, Asset)

    # Chapters
    CHAPTERS_LIST = RouteSpec("GET", Endpoints.BOOK_CHAPTERS, PAGINATED, CampaignChapter)
    CHAPTERS_GET = RouteSpec("GET", Endpoints.BOOK_CHAPTER, SINGLE, CampaignChapterDetail)
    CHAPTERS_CREATE = RouteSpec("POST", Endpoints.BOOK_CHAPTERS, SINGLE, CampaignChapter)
    CHAPTERS_UPDATE = RouteSpec("PATCH", Endpoints.BOOK_CHAPTER, SINGLE, CampaignChapter)
    CHAPTERS_DELETE = RouteSpec("DELETE", Endpoints.BOOK_CHAPTER, NO_CONTENT, None)
    CHAPTERS_RENUMBER = RouteSpec("PUT", Endpoints.BOOK_CHAPTER_NUMBER, SINGLE, CampaignChapter)

    # Chapter notes
    CHAPTERS_NOTES_LIST = RouteSpec("GET", Endpoints.BOOK_CHAPTER_NOTES, PAGINATED, Note)
    CHAPTERS_NOTES_GET = RouteSpec("GET", Endpoints.BOOK_CHAPTER_NOTE, SINGLE, Note)
    CHAPTERS_NOTES_CREATE = RouteSpec("POST", Endpoints.BOOK_CHAPTER_NOTES, SINGLE, Note)
    CHAPTERS_NOTES_UPDATE = RouteSpec("PATCH", Endpoints.BOOK_CHAPTER_NOTE, SINGLE, Note)
    CHAPTERS_NOTES_DELETE = RouteSpec("DELETE", Endpoints.BOOK_CHAPTER_NOTE, NO_CONTENT, None)

    # Chapter assets
    CHAPTERS_ASSETS_LIST = RouteSpec("GET", Endpoints.BOOK_CHAPTER_ASSETS, PAGINATED, Asset)
    CHAPTERS_ASSETS_GET = RouteSpec("GET", Endpoints.BOOK_CHAPTER_ASSET, SINGLE, Asset)
    CHAPTERS_ASSETS_DELETE = RouteSpec("DELETE", Endpoints.BOOK_CHAPTER_ASSET, NO_CONTENT, None)
    CHAPTERS_ASSETS_UPLOAD = RouteSpec("POST", Endpoints.BOOK_CHAPTER_ASSET_UPLOAD, SINGLE, Asset)

    # Characters
    CHARACTERS_LIST = RouteSpec("GET", Endpoints.CHARACTERS, PAGINATED, Character)
    CHARACTERS_GET = RouteSpec("GET", Endpoints.CHARACTER, SINGLE, CharacterDetail)
    CHARACTERS_CREATE = RouteSpec("POST", Endpoints.CHARACTERS, SINGLE, Character)
    CHARACTERS_UPDATE = RouteSpec("PATCH", Endpoints.CHARACTER, SINGLE, Character)
    CHARACTERS_DELETE = RouteSpec("DELETE", Endpoints.CHARACTER, NO_CONTENT, None)
    CHARACTERS_STATISTICS = RouteSpec("GET", Endpoints.CHARACTER_STATISTICS, SINGLE, RollStatistics)
    CHARACTERS_FULL_SHEET = RouteSpec(
        "GET", Endpoints.CHARACTER_FULL_SHEET, SINGLE, CharacterFullSheet
    )
    CHARACTERS_FULL_SHEET_CATEGORY = RouteSpec(
        "GET", Endpoints.CHARACTER_FULL_SHEET_CATEGORY, SINGLE, FullSheetTraitCategory
    )

    # Character assets
    CHARACTERS_ASSETS_LIST = RouteSpec("GET", Endpoints.CHARACTER_ASSETS, PAGINATED, Asset)
    CHARACTERS_ASSETS_GET = RouteSpec("GET", Endpoints.CHARACTER_ASSET, SINGLE, Asset)
    CHARACTERS_ASSETS_DELETE = RouteSpec("DELETE", Endpoints.CHARACTER_ASSET, NO_CONTENT, None)
    CHARACTERS_ASSETS_UPLOAD = RouteSpec("POST", Endpoints.CHARACTER_ASSET_UPLOAD, SINGLE, Asset)

    # Character notes
    CHARACTERS_NOTES_LIST = RouteSpec("GET", Endpoints.CHARACTER_NOTES, PAGINATED, Note)
    CHARACTERS_NOTES_GET = RouteSpec("GET", Endpoints.CHARACTER_NOTE, SINGLE, Note)
    CHARACTERS_NOTES_CREATE = RouteSpec("POST", Endpoints.CHARACTER_NOTES, SINGLE, Note)
    CHARACTERS_NOTES_UPDATE = RouteSpec("PATCH", Endpoints.CHARACTER_NOTE, SINGLE, Note)
    CHARACTERS_NOTES_DELETE = RouteSpec("DELETE", Endpoints.CHARACTER_NOTE, NO_CONTENT, None)

    # Character inventory
    CHARACTERS_INVENTORY_LIST = RouteSpec(
        "GET", Endpoints.CHARACTER_INVENTORY, PAGINATED, InventoryItem
    )
    CHARACTERS_INVENTORY_GET = RouteSpec(
        "GET", Endpoints.CHARACTER_INVENTORY_ITEM, SINGLE, InventoryItem
    )
    CHARACTERS_INVENTORY_CREATE = RouteSpec(
        "POST", Endpoints.CHARACTER_INVENTORY, SINGLE, InventoryItem
    )
    CHARACTERS_INVENTORY_UPDATE = RouteSpec(
        "PATCH", Endpoints.CHARACTER_INVENTORY_ITEM, SINGLE, InventoryItem
    )
    CHARACTERS_INVENTORY_DELETE = RouteSpec(
        "DELETE", Endpoints.CHARACTER_INVENTORY_ITEM, NO_CONTENT, None
    )

    # Character health
    CHARACTERS_HEALTH_GET = RouteSpec("GET", Endpoints.CHARACTER_HEALTH, SINGLE, Health)
    CHARACTERS_HEALTH_SET = RouteSpec("PUT", Endpoints.CHARACTER_HEALTH, SINGLE, Health)
    CHARACTERS_HEALTH_ACTION = RouteSpec("POST", Endpoints.CHARACTER_HEALTH_ACTIONS, SINGLE, Health)

    # Character generation
    CHARACTERS_AUTOGENERATE = RouteSpec("POST", Endpoints.AUTOGENERATE, SINGLE, Character)
    CHARACTERS_CHARGEN_START = RouteSpec(
        "POST", Endpoints.CHARGEN_START, SINGLE, ChargenSessionResponse
    )
    CHARACTERS_CHARGEN_FINALIZE = RouteSpec("POST", Endpoints.CHARGEN_FINALIZE, SINGLE, Character)
    CHARACTERS_CHARGEN_SESSIONS_LIST = RouteSpec(
        "GET", Endpoints.CHARGEN_SESSIONS, LIST, ChargenSessionResponse
    )
    CHARACTERS_CHARGEN_SESSION_GET = RouteSpec(
        "GET", Endpoints.CHARGEN_SESSION, SINGLE, ChargenSessionResponse
    )

    # Character traits
    CHARACTER_TRAITS_LIST = RouteSpec("GET", Endpoints.CHARACTER_TRAITS, PAGINATED, CharacterTrait)
    CHARACTER_TRAITS_GET = RouteSpec("GET", Endpoints.CHARACTER_TRAIT, SINGLE, CharacterTrait)
    CHARACTER_TRAITS_DELETE = RouteSpec("DELETE", Endpoints.CHARACTER_TRAIT, NO_CONTENT, None)
    CHARACTER_TRAITS_ASSIGN = RouteSpec(
        "POST", Endpoints.CHARACTER_TRAIT_ASSIGN, SINGLE, CharacterTrait
    )
    CHARACTER_TRAITS_BULK_ASSIGN = RouteSpec(
        "POST", Endpoints.CHARACTER_TRAIT_BULK_ASSIGN, SINGLE, BulkAssignTraitResponse
    )
    CHARACTER_TRAITS_CREATE = RouteSpec(
        "POST", Endpoints.CHARACTER_TRAIT_CREATE, SINGLE, CharacterTrait
    )
    CHARACTER_TRAITS_VALUE_OPTIONS = RouteSpec(
        "GET", Endpoints.CHARACTER_TRAIT_VALUE_OPTIONS, SINGLE, CharacterTraitValueOptionsResponse
    )
    CHARACTER_TRAITS_VALUE_UPDATE = RouteSpec(
        "PUT", Endpoints.CHARACTER_TRAIT_VALUE, SINGLE, CharacterTrait
    )
    CHARACTER_TRAITS_SPECIALTY_ADD = RouteSpec(
        "POST", Endpoints.CHARACTER_TRAIT_SPECIALTIES, SINGLE, CharacterTrait
    )
    CHARACTER_TRAITS_SPECIALTY_UPDATE = RouteSpec(
        "PATCH", Endpoints.CHARACTER_TRAIT_SPECIALTY, SINGLE, CharacterTrait
    )
    CHARACTER_TRAITS_SPECIALTY_DELETE = RouteSpec(
        "DELETE", Endpoints.CHARACTER_TRAIT_SPECIALTY, NO_CONTENT, None
    )
    # Tracker routes return any tracker variant; the default fake response is a CounterTracker.
    CHARACTER_TRAITS_TRACKER_GET = RouteSpec[Tracker](
        "GET", Endpoints.CHARACTER_TRAIT_TRACKER, SINGLE, CounterTracker, _TRACKER_ADAPTER
    )
    CHARACTER_TRAITS_TRACKER_SET = RouteSpec[Tracker](
        "PUT", Endpoints.CHARACTER_TRAIT_TRACKER, SINGLE, CounterTracker, _TRACKER_ADAPTER
    )
    CHARACTER_TRAITS_TRACKER_ACTION = RouteSpec[Tracker](
        "POST", Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS, SINGLE, CounterTracker, _TRACKER_ADAPTER
    )

    # Blueprint sections
    BLUEPRINT_SECTIONS_LIST = RouteSpec(
        "GET", Endpoints.BLUEPRINT_SECTIONS, PAGINATED, SheetSection
    )
    BLUEPRINT_SECTIONS_GET = RouteSpec(
        "GET", Endpoints.BLUEPRINT_SECTION_DETAIL, SINGLE, SheetSection
    )

    # Blueprint categories
    BLUEPRINT_CATEGORIES_LIST = RouteSpec(
        "GET", Endpoints.BLUEPRINT_CATEGORIES, PAGINATED, TraitCategory
    )
    BLUEPRINT_CATEGORIES_GET = RouteSpec(
        "GET", Endpoints.BLUEPRINT_CATEGORY_DETAIL, SINGLE, TraitCategory
    )
    # Blueprint subcategories
    BLUEPRINT_SUBCATEGORIES_LIST = RouteSpec(
        "GET", Endpoints.BLUEPRINT_SUBCATEGORIES, PAGINATED, TraitSubcategory
    )
    BLUEPRINT_SUBCATEGORIES_GET = RouteSpec(
        "GET", Endpoints.BLUEPRINT_SUBCATEGORY_DETAIL, SINGLE, TraitSubcategory
    )

    # Blueprint traits
    BLUEPRINT_TRAITS_LIST = RouteSpec("GET", Endpoints.BLUEPRINT_TRAITS, PAGINATED, Trait)
    BLUEPRINT_TRAITS_GET = RouteSpec("GET", Endpoints.BLUEPRINT_TRAIT_DETAIL, SINGLE, Trait)

    # Blueprint concepts
    BLUEPRINT_CONCEPTS_LIST = RouteSpec("GET", Endpoints.CONCEPTS, PAGINATED, CharacterConcept)
    BLUEPRINT_CONCEPTS_GET = RouteSpec("GET", Endpoints.CONCEPT_DETAIL, SINGLE, CharacterConcept)

    # Blueprint vampire clans
    BLUEPRINT_VAMPIRE_CLANS_LIST = RouteSpec("GET", Endpoints.VAMPIRE_CLANS, PAGINATED, VampireClan)
    BLUEPRINT_VAMPIRE_CLANS_GET = RouteSpec(
        "GET", Endpoints.VAMPIRE_CLAN_DETAIL, SINGLE, VampireClan
    )

    # Blueprint werewolf tribes
    BLUEPRINT_WEREWOLF_TRIBES_LIST = RouteSpec(
        "GET", Endpoints.WEREWOLF_TRIBES, PAGINATED, WerewolfTribe
    )
    BLUEPRINT_WEREWOLF_TRIBES_GET = RouteSpec(
        "GET", Endpoints.WEREWOLF_TRIBE_DETAIL, SINGLE, WerewolfTribe
    )

    # Blueprint werewolf auspices
    BLUEPRINT_WEREWOLF_AUSPICES_LIST = RouteSpec(
        "GET", Endpoints.WEREWOLF_AUSPICES, PAGINATED, WerewolfAuspice
    )
    BLUEPRINT_WEREWOLF_AUSPICES_GET = RouteSpec(
        "GET", Endpoints.WEREWOLF_AUSPICE_DETAIL, SINGLE, WerewolfAuspice
    )

    # Dictionary
    DICTIONARY_LIST = RouteSpec("GET", Endpoints.DICTIONARY_TERMS, PAGINATED, DictionaryTerm)
    DICTIONARY_GET = RouteSpec("GET", Endpoints.DICTIONARY_TERM, SINGLE, DictionaryTerm)
    DICTIONARY_CREATE = RouteSpec("POST", Endpoints.DICTIONARY_TERMS, SINGLE, DictionaryTerm)
    DICTIONARY_UPDATE = RouteSpec("PATCH", Endpoints.DICTIONARY_TERM, SINGLE, DictionaryTerm)
    DICTIONARY_DELETE = RouteSpec("DELETE", Endpoints.DICTIONARY_TERM, NO_CONTENT, None)

    # Dicerolls
    DICEROLLS_LIST = RouteSpec("GET", Endpoints.DICEROLLS, PAGINATED, Diceroll)
    DICEROLLS_GET = RouteSpec("GET", Endpoints.DICEROLL, SINGLE, Diceroll)
    DICEROLLS_CREATE = RouteSpec("POST", Endpoints.DICEROLLS, SINGLE, Diceroll)
    DICEROLLS_QUICKROLL = RouteSpec("POST", Endpoints.DICEROLL_QUICKROLL, SINGLE, Diceroll)

    # Options
    OPTIONS_GET = RouteSpec("GET", Endpoints.OPTIONS, RAW_JSON, None)
