"""API services for interacting with specific endpoints."""

from ._assets import AssetsMixin
from ._notes import NotesMixin
from .base import BaseService
from .campaign_book_chapters import ChaptersService
from .campaign_books import BooksService
from .campaigns import CampaignsService
from .character_autogen import CharacterAutogenService
from .character_blueprint import CharacterBlueprintService
from .character_traits import CharacterTraitsService
from .characters import CharactersService
from .companies import CompaniesService
from .dicerolls import DicerollService
from .dictionary import DictionaryService
from .identity import IdentityService
from .options import OptionsService
from .system import SystemService
from .user_lookup import UserLookupService
from .users import UsersService

__all__ = [
    "AssetsMixin",
    "BaseService",
    "BooksService",
    "CampaignsService",
    "ChaptersService",
    "CharacterAutogenService",
    "CharacterBlueprintService",
    "CharacterTraitsService",
    "CharactersService",
    "CompaniesService",
    "DicerollService",
    "DictionaryService",
    "IdentityService",
    "NotesMixin",
    "OptionsService",
    "SystemService",
    "UserLookupService",
    "UsersService",
]
