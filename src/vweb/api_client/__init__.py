"""In-repo API client for the Valentina API.

Primary exports:
    VClient: The synchronous API client class

Factory functions (primary access pattern):
    books_service, campaigns_service, chapters_service, etc.

For exceptions, use: from vweb.api_client.exceptions import APIError, NotFoundError, ...
For models, use: from vweb.api_client.models import Character, Campaign, ...
For service classes, use: from vweb.api_client.services import CharactersService, ...
"""

from loguru import logger as _logger

_logger.disable("vweb.api_client")

from vweb.api_client.client import VClient  # noqa: E402
from vweb.api_client.registry import (  # noqa: E402
    books_service,
    campaigns_service,
    chapters_service,
    character_autogen_service,
    character_blueprint_service,
    character_traits_service,
    characters_service,
    companies_service,
    default_client,
    dicerolls_service,
    dictionary_service,
    identity_service,
    options_service,
    system_service,
    user_lookup_service,
    users_service,
)

__all__ = (
    "VClient",
    "books_service",
    "campaigns_service",
    "chapters_service",
    "character_autogen_service",
    "character_blueprint_service",
    "character_traits_service",
    "characters_service",
    "companies_service",
    "default_client",
    "dicerolls_service",
    "dictionary_service",
    "identity_service",
    "options_service",
    "system_service",
    "user_lookup_service",
    "users_service",
)
