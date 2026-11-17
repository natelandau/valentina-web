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
    """Create a fresh ``VClient.companies`` service on the default client."""
    from vweb.api_client.services.companies import CompaniesService

    return CompaniesService(default_client())


def system_service() -> "SystemService":
    """Create a fresh ``VClient.system`` service on the default client."""
    from vweb.api_client.services.system import SystemService

    return SystemService(default_client())


def user_lookup_service() -> "UserLookupService":
    """Create a fresh ``VClient.user_lookup`` service on the default client."""
    from vweb.api_client.services.user_lookup import UserLookupService

    return UserLookupService(default_client())


def users_service(on_behalf_of: str, *, company_id: str | None = None) -> "UsersService":
    """Return ``VClient.users`` from the default client."""
    return default_client().users(on_behalf_of, company_id=company_id)


def identity_service(*, company_id: str | None = None) -> "IdentityService":
    """Return ``VClient.identity`` from the default client."""
    return default_client().identity(company_id=company_id)


def campaigns_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CampaignsService":
    """Return ``VClient.campaigns`` from the default client."""
    return default_client().campaigns(on_behalf_of, company_id=company_id)


def books_service(
    campaign_id: str,
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "BooksService":
    """Return ``VClient.books`` from the default client."""
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
    """Return ``VClient.chapters`` from the default client."""
    return default_client().chapters(
        campaign_id=campaign_id, book_id=book_id, on_behalf_of=on_behalf_of, company_id=company_id
    )


def characters_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharactersService":
    """Return ``VClient.characters`` from the default client."""
    return default_client().characters(on_behalf_of=on_behalf_of, company_id=company_id)


def character_traits_service(
    character_id: str,
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharacterTraitsService":
    """Return ``VClient.character_traits`` from the default client."""
    return default_client().character_traits(
        character_id=character_id, on_behalf_of=on_behalf_of, company_id=company_id
    )


def character_blueprint_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "CharacterBlueprintService":
    """Return ``VClient.character_blueprint`` from the default client."""
    return default_client().character_blueprint(on_behalf_of=on_behalf_of, company_id=company_id)


def dictionary_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "DictionaryService":
    """Return ``VClient.dictionary`` from the default client."""
    return default_client().dictionary(on_behalf_of=on_behalf_of, company_id=company_id)


def dicerolls_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "DicerollService":
    """Return ``VClient.dicerolls`` from the default client."""
    return default_client().dicerolls(on_behalf_of=on_behalf_of, company_id=company_id)


def options_service(
    on_behalf_of: str | None = None,
    *,
    company_id: str | None = None,
) -> "OptionsService":
    """Return ``VClient.options`` from the default client."""
    return default_client().options(on_behalf_of=on_behalf_of, company_id=company_id)


def character_autogen_service(
    on_behalf_of: str,
    *,
    company_id: str | None = None,
) -> "CharacterAutogenService":
    """Return ``VClient.character_autogen`` from the default client."""
    return default_client().character_autogen(on_behalf_of=on_behalf_of, company_id=company_id)
