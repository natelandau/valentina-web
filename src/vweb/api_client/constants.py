"""Constants for the API client."""

from typing import Final, Literal

# Authentication
API_KEY_HEADER = "X-API-KEY"

# The API identifies clients by this User-Agent product token
USER_AGENT_PRODUCT = "vclient/3.7.0"

# Request defaults
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 0.5
DEFAULT_MAX_RETRY_DELAY = 2.0
DEFAULT_RETRY_BUDGET = 10.0
DEFAULT_MAX_PARALLEL_REQUESTS = 4
DEFAULT_RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT_HTTP_METHODS: frozenset[str] = frozenset({"GET", "PUT", "DELETE"})

# Pagination defaults
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 100
# Reference/catalog list endpoints serve bounded seed data and allow fetching a
# full catalog in one request, so they accept a higher per-request limit.
MAX_REFERENCE_PAGE_LIMIT = 1000
MAX_PAGINATION_OFFSET = 100_000

# Request field limits the API enforces with a 400
MAX_NAME_LENGTH: Final[int] = 50
MAX_LONG_TEXT_LENGTH: Final[int] = 20_000
MAX_URL_LENGTH: Final[int] = 2048
MAX_PROVIDER_TOKEN_LENGTH: Final[int] = 16_384
MAX_DICTIONARY_SYNONYMS: Final[int] = 50
MAX_SYNONYM_LENGTH: Final[int] = 50
MIN_VAMPIRE_GENERATION: Final[int] = 1
MAX_VAMPIRE_GENERATION: Final[int] = 16
MAX_TRAIT_VALUE: Final[int] = 100
MAX_EXTRA_HEALTH_LEVELS: Final[int] = 20
MIN_CUSTOM_FLAW_XP_COST: Final[int] = 0
MAX_CUSTOM_FLAW_XP_COST: Final[int] = 100
DEFAULT_CUSTOM_FLAW_XP_COST: Final[int] = 2

# HTTP Status Code Ranges (5xx Server Errors)
HTTP_500_INTERNAL_SERVER_ERROR = 500
HTTP_600_UPPER_BOUND = 600

# Idempotency
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_IN_PROGRESS_CODE: Final[str] = "IDEMPOTENCY_IN_PROGRESS"
REQUEST_ID_HEADER = "X-Request-Id"
ON_BEHALF_OF_HEADER = "On-Behalf-Of"

# Rate Limiting Headers
RATE_LIMIT_HEADER = "RateLimit"

# Valentina API Constants
AbilityFocus = Literal["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"]
AuditEntityType = Literal[
    "ASSET",
    "BOOK",
    "CAMPAIGN",
    "CHAPTER",
    "CHARACTER",
    "CHARACTER_HEALTH",
    "CHARACTER_INVENTORY",
    "CHARACTER_TRAIT",
    "CHARACTER_TRAIT_SPECIALTY",
    "CHARGEN_SESSION",
    "COMPANY",
    "DEVELOPER",
    "DICTIONARY_TERM",
    "EXPERIENCE",
    "NOTE",
    "QUICKROLL",
    "USER",
]
AuditLogInclude = Literal["request_details"]
AuditOperation = Literal["CREATE", "UPDATE", "DELETE"]
AutoGenExperienceLevel = Literal["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"]
CharacterClass = Literal["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"]
CharacterInclude = Literal["traits", "inventory", "notes", "assets"]
BookInclude = Literal["chapters", "notes", "assets"]
ChapterInclude = Literal["notes", "assets"]
UserInclude = Literal["quickrolls", "notes", "assets", "characters"]
CharacterInventoryType = Literal[
    "BOOK",
    "CONSUMABLE",
    "ENCHANTED",
    "EQUIPMENT",
    "OTHER",
    "WEAPON",
]
CharacterStatus = Literal["ALIVE", "DEAD"]
CharacterType = Literal["PLAYER", "NPC", "STORYTELLER"]
DiceSize = Literal[4, 6, 8, 10, 20, 100]
FreeTraitChangesPermission = Literal["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"]
GameVersion = Literal["V4", "V5"]
GrantXPPermission = Literal["UNRESTRICTED", "PLAYER", "STORYTELLER"]
HunterCreed = Literal["ENTREPRENEURIAL", "FAITHFUL", "INQUISITIVE", "MARTIAL", "UNDERGROUND"]
HunterEdgeType = Literal["ASSETS", "APTITUDES", "ENDOWMENTS"]
IdentityProvider = Literal["apple", "google", "discord", "github"]
IdentityResolutionType = Literal["matched", "linked", "created"]
ManageCampaignPermission = Literal["UNRESTRICTED", "STORYTELLER"]
ManageNPCPermission = Literal["UNRESTRICTED", "STORYTELLER"]
PermissionLevel = Literal["USER", "ADMIN", "OWNER", "REVOKE"]
RecoupXPPermission = Literal["UNRESTRICTED", "DENIED", "WITHIN_SESSION"]
RollResultType = Literal["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"]
AssetType = Literal["image", "text", "audio", "video", "document", "archive", "other"]
SpecialtyRules = Literal["FIXED_COST", "RATING_BASED"]
SpecialtyType = Literal["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"]
UserRole = Literal["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"]
WerewolfRenown = Literal["HONOR", "GLORY", "WISDOM"]
BlueprintTraitOrderBy = Literal["NAME", "SHEET"]
TraitModifyCurrency = Literal["XP", "STARTING_POINTS", "NO_COST"]
TrackerType = Literal["COUNTER", "DAMAGE", "STAINS"]
TrackerAction = Literal["spend", "gain", "damage", "heal", "add_stain", "remove_stain", "reset"]
