"""Constants for the vweb application."""

from enum import Enum
from pathlib import Path
from typing import Final

PROJECT_ROOT_PATH: Final[Path] = Path(__file__).parents[2].absolute()
PACKAGE_PATH: Final[Path] = Path(__file__).parent.absolute()
TEMPLATES_PATH: Final[Path] = PACKAGE_PATH / "templates"
STATIC_PATH: Final[Path] = PACKAGE_PATH / "static"

# --- Cache TTLs in seconds: one place to tune every API-response cache ---
# Long-lived shared reference data that rarely changes within a session.
CACHE_BLUEPRINT_TTL: Final[int] = 60 * 60  # 1 hour
CACHE_OPTIONS_TTL: Final[int] = 60 * 60  # 1 hour
CACHE_DICTIONARY_TTL: Final[int] = 60 * 60  # 1 hour
CACHE_CAMPAIGN_CONTENT_TTL: Final[int] = 60 * 60  # 1 hour
# shorter lived caches
CACHE_CHARACTER_FULL_SHEET_TTL: Final[int] = 60
CACHE_SYSTEM_STATUS_TTL: Final[int] = 120
CACHE_STATISTICS_TTL: Final[int] = 30
CACHE_DICEROLLS_TTL: Final[int] = 30
CACHE_AUDIT_LOG_TTL: Final[int] = 60
# How long before the company resources_modified_at stamp is re-validated against the API.
CACHE_GLOBAL_CONTEXT_TIMESTAMP_TTL: Final[int] = 120

MAX_IMAGE_SIZE: Final[int] = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)


class LogLevel(Enum):
    """Log level."""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
