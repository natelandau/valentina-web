"""Constants for the vweb application."""

from enum import Enum
from pathlib import Path
from typing import Final

PROJECT_ROOT_PATH: Final[Path] = Path(__file__).parents[2].absolute()
PACKAGE_PATH: Final[Path] = Path(__file__).parent.absolute()
TEMPLATES_PATH: Final[Path] = PACKAGE_PATH / "templates"
STATIC_PATH: Final[Path] = PACKAGE_PATH / "static"

CACHE_CHARACTER_FULL_SHEET_PREFIX: Final[str] = "char_full_sheet:"
CACHE_CHARACTER_FULL_SHEET_TTL: Final[int] = 60
CACHE_BLUEPRINT_TTL: Final[int] = 60 * 60  # 1 hour
CACHE_OPTIONS_TTL: Final[int] = 60 * 60  # 1 hour
CACHE_BLUEPRINT_SHEET_SECTIONS_PREFIX: Final[str] = "bp_sheet_sections:"
CACHE_BLUEPRINT_CATEGORIES_PREFIX: Final[str] = "bp_categories:"
CACHE_DICTIONARY_KEY: Final[str] = "dictionary_terms"
CACHE_DICTIONARY_TTL: Final[int] = 60 * 60  # 1 hour

ANONYMOUS_ON_BEHALF_OF: Final[str] = "anonymous"

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
