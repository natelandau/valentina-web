"""Tests for the registry module."""

import pytest

from vweb.api_client import VClient
from vweb.api_client.registry import (
    books_service,
    campaigns_service,
    chapters_service,
    character_autogen_service,
    character_blueprint_service,
    character_traits_service,
    characters_service,
    clear_default_client,
    companies_service,
    configure_default_client,
    default_client,
    dicerolls_service,
    dictionary_service,
    identity_service,
    options_service,
    system_service,
    users_service,
)
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
    UsersService,
)


@pytest.fixture(autouse=True)
def reset_default_client():
    """Reset the default client before and after each test."""
    # Given: Clear any existing default client
    from vweb.api_client import registry

    registry._default_client = None
    yield
    # Then: Clean up after test
    registry._default_client = None


class TestConfigureDefaultClient:
    """Tests for configure_default_client function."""

    def test_configure_default_client_stores_client(self, base_url, api_key) -> None:
        """Verify configure_default_client stores the client in module state."""
        # Given: A VClient instance
        client = VClient(base_url=base_url, api_key=api_key)

        # When: Configuring the default client
        configure_default_client(client)

        # Then: The client is stored
        from vweb.api_client import registry

        assert registry._default_client is client

    def test_configure_default_client_overwrites_previous(self, base_url, api_key) -> None:
        """Verify configure_default_client overwrites a previously configured client."""
        # Given: Two VClient instances
        client1 = VClient(base_url=base_url, api_key=api_key)
        client2 = VClient(base_url=base_url, api_key=api_key)

        # When: Configuring the first, then the second
        configure_default_client(client1)
        configure_default_client(client2)

        # Then: The second client is stored
        from vweb.api_client import registry

        assert registry._default_client is client2


class TestClearDefaultClient:
    """Tests for clear_default_client function."""

    def test_clears_default_when_matching(self, base_url, api_key) -> None:
        """Verify clear_default_client resets the default when the instance matches."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Clearing with the same instance
        clear_default_client(client)

        # Then: No default client is configured
        with pytest.raises(RuntimeError, match="No default client configured"):
            default_client()

    def test_preserves_default_when_not_matching(self, base_url, api_key) -> None:
        """Verify clear_default_client is a no-op when a different instance is the default."""
        # Given: Two clients, with client1 as default
        client1 = VClient(base_url=base_url, api_key=api_key)
        client2 = VClient(base_url=base_url, api_key=api_key, set_as_default=False)
        configure_default_client(client1)

        # When: Clearing with the non-default instance
        clear_default_client(client2)

        # Then: The original default is preserved
        assert default_client() is client1

    def test_close_clears_default_client(self, base_url, api_key) -> None:
        """Verify VClient.close() clears the default client reference."""
        # Given: A default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Closing the client
        client.close()

        # Then: default_client() raises instead of returning a closed session
        with pytest.raises(RuntimeError, match="No default client configured"):
            default_client()

    def test_context_manager_clears_default_client(self, base_url, api_key) -> None:
        """Verify context manager exit clears the default client reference."""
        # Given/When: Using client as context manager
        with VClient(base_url=base_url, api_key=api_key):
            pass

        # Then: default_client() raises instead of returning a closed session
        with pytest.raises(RuntimeError, match="No default client configured"):
            default_client()


class TestDefaultClient:
    """Tests for default_client function."""

    def test_default_client_raises_when_not_configured(self) -> None:
        """Verify default_client raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling default_client raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            default_client()

    def test_default_client_returns_configured_client(self, base_url, api_key) -> None:
        """Verify default_client returns the configured client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the default client
        result = default_client()

        # Then: The configured client is returned
        assert result is client


class TestCompaniesService:
    """Tests for companies_service factory function."""

    def test_companies_service_raises_when_not_configured(self) -> None:
        """Verify companies_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling companies_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            companies_service()

    def test_companies_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify companies_service returns a CompaniesService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the companies service
        service = companies_service()

        # Then: A CompaniesService is returned with the correct client
        assert isinstance(service, CompaniesService)
        assert service._client is client


class TestIdentityService:
    """Tests for identity_service factory function."""

    def test_identity_service_raises_when_not_configured(self) -> None:
        """Verify identity_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling identity_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            identity_service(company_id="company123")

    def test_identity_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify identity_service returns an IdentityService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the identity service
        service = identity_service(company_id="company123")

        # Then: An IdentityService is returned with the correct client
        assert isinstance(service, IdentityService)
        assert service._client is client


class TestCharacterTraitsService:
    """Tests for character_traits_service factory function."""

    def test_character_traits_service_raises_when_not_configured(self) -> None:
        """Verify character_traits_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling character_traits_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            character_traits_service("character_id", "on-behalf-of-user", company_id="company_id")

    def test_character_traits_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify character_traits_service returns a CharacterTraitsService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the character traits service
        service = character_traits_service(
            "character_id", "on-behalf-of-user", company_id="company_id"
        )

        # Then: A CharacterTraitsService is returned with the correct client
        assert isinstance(service, CharacterTraitsService)
        assert service._client is client


class TestCharactersService:
    """Tests for characters_service factory function."""

    def test_characters_service_raises_when_not_configured(self) -> None:
        """Verify characters_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling characters_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            characters_service("on-behalf-of-user", company_id="company_id")

    def test_characters_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify characters_service returns a CharactersService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the characters service
        service = characters_service("on-behalf-of-user", company_id="company_id")

        # Then: A CharactersService is returned with the correct client
        assert isinstance(service, CharactersService)
        assert service._client is client


class TestChaptersService:
    """Tests for chapters_service factory function."""

    def test_chapters_service_raises_when_not_configured(self) -> None:
        """Verify chapters_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling chapters_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            chapters_service("campaign_id", "book_id", "on-behalf-of-user", company_id="company_id")

    def test_chapters_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify chapters_service returns a ChaptersService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the chapters service
        service = chapters_service(
            "campaign_id", "book_id", "on-behalf-of-user", company_id="company_id"
        )

        # Then: A ChaptersService is returned with the correct client
        assert isinstance(service, ChaptersService)
        assert service._client is client


class TestBooksService:
    """Tests for books_service factory function."""

    def test_books_service_raises_when_not_configured(self) -> None:
        """Verify books_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling books_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            books_service("campaign_id", "on-behalf-of-user", company_id="company_id")

    def test_books_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify books_service returns a BooksService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the books service
        service = books_service("campaign_id", "on-behalf-of-user", company_id="company_id")

        # Then: A BooksService is returned with the correct client
        assert isinstance(service, BooksService)
        assert service._client is client


class TestCampaignsService:
    """Tests for campaigns_service factory function."""

    def test_campaigns_service_raises_when_not_configured(self) -> None:
        """Verify campaigns_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling campaigns_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            campaigns_service("on-behalf-of-user", company_id="company_id")

    def test_campaigns_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify campaigns_service returns a CampaignsService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the campaigns service
        service = campaigns_service("on-behalf-of-user", company_id="company_id")

        # Then: A CampaignsService is returned with the correct client
        assert isinstance(service, CampaignsService)
        assert service._client is client


class TestUsersService:
    """Tests for users_service factory function."""

    def test_users_service_raises_when_not_configured(self) -> None:
        """Verify users_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling users_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            users_service("on-behalf-of-user", company_id="company_id")

    def test_users_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify users_service returns a UsersService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the users service
        service = users_service("on-behalf-of-user", company_id="company_id")

        # Then: A UsersService is returned with the correct client
        assert isinstance(service, UsersService)
        assert service._client is client


class TestSystemService:
    """Tests for system_service factory function."""

    def test_system_service_raises_when_not_configured(self) -> None:
        """Verify system_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling system_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            system_service()

    def test_system_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify system_service returns a SystemService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the system service
        service = system_service()

        # Then: A SystemService is returned with the correct client
        assert isinstance(service, SystemService)
        assert service._client is client


class TestTopLevelImports:
    """Tests for top-level package imports."""

    def test_imports_from_vclient(self) -> None:
        """Verify factory functions are importable from vweb.api_client package."""
        # When: Importing from vweb.api_client
        from vweb.api_client import (
            companies_service,
            system_service,
        )
        from vweb.api_client.registry import configure_default_client, default_client

        # Then: All functions are callable
        assert callable(configure_default_client)
        assert callable(default_client)
        assert callable(companies_service)
        assert callable(system_service)

    def test_imports_from_vclient_api(self) -> None:
        """Verify factory functions are importable from vweb.api_client.registry."""
        # When: Importing from vweb.api_client.registry
        from vweb.api_client.registry import (
            companies_service,
            configure_default_client,
            default_client,
            system_service,
        )

        # Then: All functions are callable
        assert callable(configure_default_client)
        assert callable(default_client)
        assert callable(companies_service)
        assert callable(system_service)


class TestCharacterBlueprintService:
    """Tests for character_blueprint_service factory function."""

    def test_character_blueprint_service_raises_when_not_configured(self) -> None:
        """Verify character_blueprint_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling character_blueprint_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            character_blueprint_service("on-behalf-of-user", company_id="company_id")

    def test_character_blueprint_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify character_blueprint_service returns a CharacterBlueprintService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the character blueprint service
        service = character_blueprint_service("on-behalf-of-user", company_id="company_id")

        # Then: A CharacterBlueprintService is returned with the correct client
        assert isinstance(service, CharacterBlueprintService)
        assert service._client is client


class TestDictionaryService:
    """Tests for dictionary_service factory function."""

    def test_dictionary_service_raises_when_not_configured(self) -> None:
        """Verify dictionary_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling dictionary_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            dictionary_service("on-behalf-of-user", company_id="company_id")

    def test_dictionary_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify dictionary_service returns a DictionaryService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the dictionary service
        service = dictionary_service("on-behalf-of-user", company_id="company_id")

        # Then: A DictionaryService is returned with the correct client
        assert isinstance(service, DictionaryService)
        assert service._client is client


class TestDicerollService:
    """Tests for dicerolls_service factory function."""

    def test_dicerolls_service_raises_when_not_configured(self) -> None:
        """Verify dicerolls_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling dicerolls_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            dicerolls_service("on-behalf-of-user", company_id="company_id")

    def test_dicerolls_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify dicerolls_service returns a DicerollService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the dicerolls service
        service = dicerolls_service("on-behalf-of-user", company_id="company_id")

        # Then: A DicerollService is returned with the correct client
        assert isinstance(service, DicerollService)
        assert service._client is client


class TestOptionsService:
    """Tests for options_service factory function."""

    def test_options_service_raises_when_not_configured(self) -> None:
        """Verify options_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling options_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            options_service("on-behalf-of-user", company_id="company_id")

    def test_options_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify options_service returns a OptionsService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the options service
        service = options_service("on-behalf-of-user", company_id="company_id")

        # Then: A OptionsService is returned with the correct client
        assert isinstance(service, OptionsService)
        assert service._client is client


class TestCharacterAutogenService:
    """Tests for character_autogen_service factory function."""

    def test_character_autogen_service_raises_when_not_configured(self) -> None:
        """Verify character_autogen_service raises RuntimeError when no client is configured."""
        # Given: No default client configured

        # When/Then: Calling character_autogen_service raises RuntimeError
        with pytest.raises(RuntimeError, match="No default client configured"):
            character_autogen_service("on-behalf-of-user", company_id="company_id")

    def test_character_autogen_service_returns_service_instance(self, base_url, api_key) -> None:
        """Verify character_autogen_service returns a CharacterAutogenService with the default client."""
        # Given: A configured default client
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When: Getting the character autogen service
        service = character_autogen_service("on-behalf-of-user", company_id="company_id")

        # Then: A CharacterAutogenService is returned with the correct client
        assert isinstance(service, CharacterAutogenService)
        assert service._client is client


class TestDefaultCompanyId:
    """Tests for default_company_id behavior."""

    def test_uses_default_company_id_when_not_provided(self, base_url, api_key) -> None:
        """Verify service uses default_company_id when company_id not passed."""
        # Given: A client with default_company_id configured
        client = VClient(base_url=base_url, api_key=api_key, default_company_id="default-company")
        configure_default_client(client)

        # When: Getting users service without company_id
        service = users_service("on-behalf-of-user")

        # Then: Service uses the default company_id
        assert service._company_id == "default-company"

    def test_explicit_company_id_overrides_default(self, base_url, api_key) -> None:
        """Verify explicit company_id overrides default_company_id."""
        # Given: A client with default_company_id configured
        client = VClient(base_url=base_url, api_key=api_key, default_company_id="default-company")
        configure_default_client(client)

        # When: Getting users service with explicit company_id
        service = users_service("on-behalf-of-user", company_id="explicit-company")

        # Then: Service uses the explicit company_id
        assert service._company_id == "explicit-company"

    def test_raises_when_no_company_id_and_no_default(self, base_url, api_key) -> None:
        """Verify ValueError raised when no company_id and no default."""
        # Given: A client without default_company_id
        client = VClient(base_url=base_url, api_key=api_key)
        configure_default_client(client)

        # When/Then: Calling users_service without company_id raises ValueError
        with pytest.raises(ValueError, match="company_id is required"):
            users_service("on-behalf-of-user")


class TestVClientDefaultCompanyId:
    """Tests for VClient default_company_id behavior."""

    def test_default_company_id_property(self, base_url, api_key) -> None:
        """Verify default_company_id property returns configured value."""
        # When: Creating client with default_company_id
        client = VClient(
            base_url=base_url,
            api_key=api_key,
            default_company_id="my-company",
            set_as_default=False,
        )

        # Then: Property returns the value
        assert client.default_company_id == "my-company"

    def test_default_company_id_property_returns_none(self, base_url, api_key) -> None:
        """Verify default_company_id property returns None when not configured."""
        # When: Creating client without default_company_id
        client = VClient(base_url=base_url, api_key=api_key, set_as_default=False)

        # Then: Property returns None
        assert client.default_company_id is None

    def test_client_users_uses_default_company_id(self, base_url, api_key) -> None:
        """Verify client.users() uses default_company_id when not passed."""
        # Given: A client with default_company_id configured
        client = VClient(
            base_url=base_url,
            api_key=api_key,
            default_company_id="default-company",
            set_as_default=False,
        )

        # When: Getting users service without company_id
        service = client.users("on-behalf-of-user")

        # Then: Service uses the default company_id
        assert service._company_id == "default-company"

    def test_client_users_explicit_overrides_default(self, base_url, api_key) -> None:
        """Verify client.users() explicit company_id overrides default."""
        # Given: A client with default_company_id configured
        client = VClient(
            base_url=base_url,
            api_key=api_key,
            default_company_id="default-company",
            set_as_default=False,
        )

        # When: Getting users service with explicit company_id
        service = client.users("on-behalf-of-user", company_id="explicit-company")

        # Then: Service uses the explicit company_id
        assert service._company_id == "explicit-company"

    def test_client_users_raises_when_no_company_id_and_no_default(self, base_url, api_key) -> None:
        """Verify client.users() raises ValueError when no company_id and no default."""
        # Given: A client without default_company_id
        client = VClient(base_url=base_url, api_key=api_key, set_as_default=False)

        # When/Then: Calling users() without company_id raises ValueError
        with pytest.raises(ValueError, match="company_id is required"):
            client.users("on-behalf-of-user")
