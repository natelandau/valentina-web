"""Default client registry and service factory functions.

This module provides a way to access services from any module without passing
the client explicitly. VClient automatically registers itself as the default
when instantiated (unless `set_as_default=False` is passed).

Example:
    ```python
    from vweb.api_client import VClient, companies_service

    # Client auto-registers as default
    client = VClient(base_url="https://api.example.com", api_key="...")

    # Use services anywhere
    def some_function():
        companies = companies_service()
        return companies.list_all()
    ```
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vweb.api_client.client import VClient
    from vweb.api_client.services import (
        BooksService,
        CampaignsService,
        ChaptersService,
        CharacterAutogenService,
        CharacterBlueprintService,
        CharactersService,
        CharacterTraitsService,
        CompaniesService,
        DicerollService,
        DictionaryService,
        IdentityService,
        OptionsService,
        SystemService,
        UserLookupService,
        UsersService,
    )

_default_client: "VClient | None" = None


def configure_default_client(client: "VClient") -> None:
    """Configure the default client for service factory functions.

    Note: This is called automatically when VClient is instantiated (unless
    `set_as_default=False` is passed). You typically don't need to call this
    directly unless you're switching between multiple clients.

    Args:
        client (VClient): The configured VClient instance to use as the default.

    Example:
        ```python
        # Switch to a different client
        client2 = VClient(base_url=url, api_key="other-key", set_as_default=False)
        configure_default_client(client2)
        ```
    """
    global _default_client  # noqa: PLW0603
    _default_client = client


def clear_default_client(client: "VClient") -> None:
    """Clear the default client if it matches the given instance.

    Called automatically by ``VClient.close()`` so that subsequent calls to
    ``default_client()`` raise a clear ``RuntimeError`` instead of returning a
    closed HTTP session.

    Args:
        client: The client instance to compare against the current default.
    """
    global _default_client  # noqa: PLW0603
    if _default_client is client:
        _default_client = None


def default_client() -> "VClient":
    """Retrieve the configured default client.

    Use this when you need direct access to the VClient instance that was
    configured via `configure_default_client()`.

    Returns:
        VClient: The configured default client instance.

    Raises:
        RuntimeError: If no default client has been configured.
    """
    if _default_client is None:
        msg = "No default client configured. Call configure_default_client() first."
        raise RuntimeError(msg)
    return _default_client


def companies_service() -> "CompaniesService":
    """Create a CompaniesService using the default client.

    Provides access to company management operations (list, get, create, update, delete)
    without needing to pass a client instance.

    Returns:
        CompaniesService: A service instance for company operations.

    Raises:
        RuntimeError: If no default client has been configured.

    Example:
        ```python
        companies = companies_service()
        all_companies = companies.list_all()
        ```
    """
    from vweb.api_client.services.companies import CompaniesService

    return CompaniesService(default_client())


def system_service() -> "SystemService":
    """Create a SystemService using the default client.

    Provides access to system-level operations (health checks, status)
    without needing to pass a client instance.

    Returns:
        SystemService: A service instance for system operations.

    Raises:
        RuntimeError: If no default client has been configured.

    Example:
        ```python
        system = system_service()
        health = system.health()
        ```
    """
    from vweb.api_client.services.system import SystemService

    return SystemService(default_client())


def user_lookup_service() -> "UserLookupService":
    """Create a UserLookupService using the default client.

    Discover which companies a person has a user record in by searching
    via email, Discord ID, Google ID, GitHub ID, or Apple ID.

    Returns:
        UserLookupService: A service instance for cross-company user lookup.

    Raises:
        RuntimeError: If no default client has been configured.

    Example:
        ```python
        lookup = user_lookup_service()
        results = lookup.by_email("alice@example.com")
        ```
    """
    from vweb.api_client.services.user_lookup import UserLookupService

    return UserLookupService(default_client())


def users_service(on_behalf_of: str, *, company_id: str | None = None) -> "UsersService":
    """Create a UsersService scoped to a specific company using the default client.

    Provides access to user management operations (list, get, create, update, delete)
    within a specific company without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Returns:
        UsersService: A service instance scoped to the specified company.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.

    Example:
        ```python
        users = users_service("user_id", "company_id")
        all_users = users.list_all()
        user = users.get("user_id")
        ```
    """
    return default_client().users(on_behalf_of, company_id=company_id)


def identity_service(*, company_id: str | None = None) -> "IdentityService":
    """Create a company-scoped IdentityService using the default client.

    Resolves verified provider logins (Apple/Google ID tokens, Discord/GitHub
    access tokens) to canonical users. Does not require an acting user, only
    developer API key authentication.

    Args:
        company_id: The ID of the company to resolve identities in. If not
            provided, uses the default_company_id from the client config.

    Returns:
        IdentityService: A service instance for identity resolution.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.

    Example:
        ```python
        identity = identity_service()
        result = identity.identify(provider="google", token="<id-token>")
        ```
    """
    return default_client().identity(company_id=company_id)


def campaigns_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CampaignsService":
    """Create a CampaignsService scoped to a specific company.

    Provides access to campaign management operations (list, get, create, update, delete)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Returns:
        CampaignsService: A service instance scoped to the specified company.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.

    Example:
        ```python
        campaigns = campaigns_service("user_id")
        all_campaigns = campaigns.list_all()
        campaign = campaigns.get("campaign_id")
        ```
    """
    return default_client().campaigns(on_behalf_of, company_id=company_id)


def books_service(
    campaign_id: str,
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "BooksService":
    """Create a BooksService scoped to a specific company and campaign.

    Provides access to campaign book management operations (list, get, create, update, delete)
    within a specific company and campaign context without needing to pass a client instance.

    Args:
        campaign_id: The ID of the campaign to operate within.
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Returns:
        BooksService: A service instance scoped to the specified context.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.

    Example:
        ```python
        books = books_service("campaign_id", "user_id")
        all_books = books.list_all()
        book = books.get("book_id")
        ```
    """
    return default_client().books(
        campaign_id=campaign_id, on_behalf_of=on_behalf_of, company_id=company_id
    )


def chapters_service(
    campaign_id: str,
    book_id: str,
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "ChaptersService":
    """Create a ChaptersService scoped to a specific company, campaign, and book.

    Provides access to campaign book chapter management operations (list, get, create, update, delete)
    within a specific company, campaign, and book context without needing to pass a client instance.

    Args:
        campaign_id: The ID of the campaign to operate within.
        book_id: The ID of the book to operate within.
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().chapters(
        campaign_id=campaign_id, book_id=book_id, on_behalf_of=on_behalf_of, company_id=company_id
    )


def characters_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharactersService":
    """Create a CharactersService scoped to a specific company.

    Provides access to character management operations (list, get, create, update, delete)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().characters(on_behalf_of=on_behalf_of, company_id=company_id)


def character_traits_service(
    character_id: str,
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharacterTraitsService":
    """Create a CharacterTraitsService scoped to a specific company and character.

    Provides access to character trait management operations (list, get, create, update, delete)
    within a specific company and character context without needing to pass a client instance.

    Args:
        character_id: The ID of the character to operate within.
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().character_traits(
        character_id=character_id, on_behalf_of=on_behalf_of, company_id=company_id
    )


def character_blueprint_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "CharacterBlueprintService":
    """Create a CharacterBlueprintService scoped to a specific company.

    Provides access to character blueprint management operations (list, get, create, update, delete)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().character_blueprint(on_behalf_of=on_behalf_of, company_id=company_id)


def dictionary_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "DictionaryService":
    """Create a DictionaryService scoped to a specific company.

    Provides access to dictionary term management operations (list, get, create, update, delete)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().dictionary(on_behalf_of=on_behalf_of, company_id=company_id)


def dicerolls_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "DicerollService":
    """Create a DicerollService scoped to a specific company.

    Provides access to dice roll management operations (list, get, create)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().dicerolls(on_behalf_of=on_behalf_of, company_id=company_id)


def options_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "OptionsService":
    """Create a OptionsService scoped to a specific company.

    Provides access to options and enumerations management operations (list, get, create, update, delete)
    within a specific company context without needing to pass a client instance.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().options(on_behalf_of=on_behalf_of, company_id=company_id)


def character_autogen_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharacterAutogenService":
    """Create a CharacterAutogenService scoped to a specific company.

    Provides access to character autogeneration and chargen session operations
    without needing to pass a client instance. Pass ``campaign_id`` directly to
    ``generate_character()`` and ``start_chargen_session()`` to scope each call.

    Args:
        on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        company_id: The ID of the company to operate within. If not provided,
            uses the default_company_id from the client config.

    Raises:
        RuntimeError: If no default client has been configured.
        ValueError: If no company_id provided and no default configured.
    """
    return default_client().character_autogen(on_behalf_of=on_behalf_of, company_id=company_id)
