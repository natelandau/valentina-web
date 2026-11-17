"""API endpoint paths for the Valentina API.

Centralized location for all API endpoint paths to avoid magic strings throughout the codebase.
"""


class Endpoints:
    """Container for all API endpoint paths.

    Use these constants when making API requests to ensure consistency and enable easy refactoring.

    Example:
        response = self._get(Endpoints.COMPANIES)
        response = self._get(Endpoints.COMPANY.format(company_id=company_id))
    """

    _BASE = "/api/v1"

    # System endpoints
    HEALTH = f"{_BASE}/health"

    # User lookup (cross-company, not scoped)
    USERS_LOOKUP = f"{_BASE}/users/lookup"

    # Companies endpoints
    COMPANIES = f"{_BASE}/companies"
    COMPANY = f"{COMPANIES}/{{company_id}}"
    COMPANY_ACCESS = f"{COMPANY}/access"
    COMPANY_STATISTICS = f"{COMPANY}/statistics"
    COMPANY_AUDIT_LOGS = f"{COMPANY}/audit-logs"

    # User endpoints
    USERS = f"{COMPANY}/users"
    USERS_UNAPPROVED_LIST = f"{USERS}/unapproved"
    USER = f"{USERS}/{{user_id}}"
    USER_MERGE = f"{USERS}/merge"
    USER_IDENTITIES = f"{USER}/identities"
    USER_IDENTITY = f"{USER_IDENTITIES}/{{provider}}"
    USER_APPROVE = f"{USER}/approve"
    USER_DENY = f"{USER}/deny"
    USER_STATISTICS = f"{USER}/statistics"
    USER_ASSETS = f"{USER}/assets"
    USER_ASSET = f"{USER_ASSETS}/{{asset_id}}"
    USER_ASSET_UPLOAD = f"{USER_ASSETS}/upload"
    USER_AVATAR = f"{USER}/avatar"
    USER_EXPERIENCE_CAMPAIGN = f"{USER}/experience/{{campaign_id}}"
    USER_EXPERIENCE_XP_ADD = f"{USER}/experience/xp/add"
    USER_EXPERIENCE_XP_REMOVE = f"{USER}/experience/xp/remove"
    USER_EXPERIENCE_CP_ADD = f"{USER}/experience/cp/add"
    USER_NOTES = f"{USER}/notes"
    USER_NOTE = f"{USER_NOTES}/{{note_id}}"
    USER_QUICKROLLS = f"{USER}/quickrolls"
    USER_QUICKROLL = f"{USER_QUICKROLLS}/{{quickroll_id}}"

    # Identity resolution endpoints
    AUTH_IDENTIFY = f"{COMPANY}/auth/identify"

    # Campaign endpoints
    CAMPAIGNS = f"{COMPANY}/campaigns"
    CAMPAIGN = f"{CAMPAIGNS}/{{campaign_id}}"
    CAMPAIGN_STATISTICS = f"{CAMPAIGN}/statistics"
    CAMPAIGN_ASSETS = f"{CAMPAIGN}/assets"
    CAMPAIGN_ASSET = f"{CAMPAIGN_ASSETS}/{{asset_id}}"
    CAMPAIGN_ASSET_UPLOAD = f"{CAMPAIGN_ASSETS}/upload"
    CAMPAIGN_NOTES = f"{CAMPAIGN}/notes"
    CAMPAIGN_NOTE = f"{CAMPAIGN_NOTES}/{{note_id}}"

    # Campaign book endpoints
    CAMPAIGN_BOOKS = f"{CAMPAIGN}/books"
    CAMPAIGN_BOOK = f"{CAMPAIGN_BOOKS}/{{book_id}}"
    CAMPAIGN_BOOK_NUMBER = f"{CAMPAIGN_BOOK}/number"
    BOOK_NOTES = f"{CAMPAIGN_BOOK}/notes"
    BOOK_NOTE = f"{BOOK_NOTES}/{{note_id}}"
    BOOK_ASSETS = f"{CAMPAIGN_BOOK}/assets"
    BOOK_ASSET_UPLOAD = f"{BOOK_ASSETS}/upload"
    BOOK_ASSET = f"{BOOK_ASSETS}/{{asset_id}}"

    # Book chapter endpoints
    BOOK_CHAPTERS = f"{CAMPAIGN_BOOK}/chapters"
    BOOK_CHAPTER = f"{BOOK_CHAPTERS}/{{chapter_id}}"
    BOOK_CHAPTER_NUMBER = f"{BOOK_CHAPTER}/number"
    BOOK_CHAPTER_NOTES = f"{BOOK_CHAPTER}/notes"
    BOOK_CHAPTER_NOTE = f"{BOOK_CHAPTER_NOTES}/{{note_id}}"
    BOOK_CHAPTER_ASSETS = f"{BOOK_CHAPTER}/assets"
    BOOK_CHAPTER_ASSET_UPLOAD = f"{BOOK_CHAPTER_ASSETS}/upload"
    BOOK_CHAPTER_ASSET = f"{BOOK_CHAPTER_ASSETS}/{{asset_id}}"

    # Character endpoints
    CHARACTERS = f"{COMPANY}/characters"
    CHARACTER = f"{CHARACTERS}/{{character_id}}"
    CHARACTER_STATISTICS = f"{CHARACTER}/statistics"
    CHARACTER_FULL_SHEET = f"{CHARACTER}/full-sheet"
    CHARACTER_FULL_SHEET_CATEGORY = f"{CHARACTER_FULL_SHEET}/categories/{{category_id}}"
    CHARACTER_ASSETS = f"{CHARACTER}/assets"
    CHARACTER_ASSET = f"{CHARACTER_ASSETS}/{{asset_id}}"
    CHARACTER_ASSET_UPLOAD = f"{CHARACTER_ASSETS}/upload"
    CHARACTER_NOTES = f"{CHARACTER}/notes"
    CHARACTER_NOTE = f"{CHARACTER_NOTES}/{{note_id}}"
    CHARACTER_INVENTORY = f"{CHARACTER}/inventory"
    CHARACTER_INVENTORY_ITEM = f"{CHARACTER_INVENTORY}/{{item_id}}"
    # Character RNG generation
    AUTOGENERATE = f"{CHARACTERS}/autogenerate"
    CHARGEN_START = f"{CHARACTERS}/chargen/start"
    CHARGEN_FINALIZE = f"{CHARACTERS}/chargen/finalize"
    CHARGEN_SESSIONS = f"{CHARACTERS}/chargen/sessions"
    CHARGEN_SESSION = f"{CHARGEN_SESSIONS}/{{session_id}}"

    # Character trait endpoints
    CHARACTER_TRAITS = f"{CHARACTER}/traits"
    CHARACTER_TRAIT_ASSIGN = f"{CHARACTER_TRAITS}/assign"
    CHARACTER_TRAIT_BULK_ASSIGN = f"{CHARACTER_TRAITS}/bulk-assign"
    CHARACTER_TRAIT_CREATE = f"{CHARACTER_TRAITS}/create"
    CHARACTER_TRAIT = f"{CHARACTER_TRAITS}/{{character_trait_id}}"
    CHARACTER_TRAIT_VALUE_OPTIONS = f"{CHARACTER_TRAIT}/value-options"
    CHARACTER_TRAIT_VALUE = f"{CHARACTER_TRAIT}/value"
    CHARACTER_TRAIT_SPECIALTIES = f"{CHARACTER_TRAIT}/specialties"
    CHARACTER_TRAIT_SPECIALTY = f"{CHARACTER_TRAIT_SPECIALTIES}/{{specialty_id}}"
    CHARACTER_TRAIT_TRACKER = f"{CHARACTER_TRAIT}/tracker"
    CHARACTER_TRAIT_TRACKER_ACTIONS = f"{CHARACTER_TRAIT_TRACKER}/actions"
    CHARACTER_HEALTH = f"{CHARACTER}/health"
    CHARACTER_HEALTH_ACTIONS = f"{CHARACTER_HEALTH}/actions"

    # Character Blueprint endpoints
    BLUEPRINT_BASE = f"{COMPANY}/characterblueprint"
    BLUEPRINT_SECTIONS = f"{BLUEPRINT_BASE}/sections"
    BLUEPRINT_SECTION_DETAIL = f"{BLUEPRINT_SECTIONS}/{{section_id}}"
    BLUEPRINT_CATEGORIES = f"{BLUEPRINT_BASE}/categories"
    BLUEPRINT_CATEGORY_DETAIL = f"{BLUEPRINT_CATEGORIES}/{{category_id}}"
    BLUEPRINT_SUBCATEGORIES = f"{BLUEPRINT_BASE}/subcategories"
    BLUEPRINT_SUBCATEGORY_DETAIL = f"{BLUEPRINT_SUBCATEGORIES}/{{subcategory_id}}"
    BLUEPRINT_TRAITS = f"{BLUEPRINT_BASE}/traits"
    BLUEPRINT_TRAIT_DETAIL = f"{BLUEPRINT_TRAITS}/{{trait_id}}"
    CONCEPTS = f"{BLUEPRINT_BASE}/concepts"
    CONCEPT_DETAIL = f"{CONCEPTS}/{{concept_id}}"
    VAMPIRE_CLANS = f"{BLUEPRINT_BASE}/vampire-clans"
    VAMPIRE_CLAN_DETAIL = f"{VAMPIRE_CLANS}/{{vampire_clan_id}}"
    WEREWOLF_TRIBES = f"{BLUEPRINT_BASE}/werewolf-tribes"
    WEREWOLF_TRIBE_DETAIL = f"{WEREWOLF_TRIBES}/{{werewolf_tribe_id}}"
    WEREWOLF_AUSPICES = f"{BLUEPRINT_BASE}/werewolf-auspices"
    WEREWOLF_AUSPICE_DETAIL = f"{WEREWOLF_AUSPICES}/{{werewolf_auspice_id}}"
    # Dictionary endpoints
    DICTIONARY_TERMS = f"{COMPANY}/dictionaries"
    DICTIONARY_TERM = f"{DICTIONARY_TERMS}/{{term_id}}"

    # Dice Rolls
    DICEROLLS = f"{COMPANY}/dicerolls"
    DICEROLL = f"{DICEROLLS}/{{diceroll_id}}"
    DICEROLL_QUICKROLL = f"{DICEROLLS}/quickroll"

    # Options and enumerations
    OPTIONS = f"{COMPANY}/options"
