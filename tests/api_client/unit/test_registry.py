"""Tests for the registry module."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from vweb.api_client import VClient, registry
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
    user_lookup_service,
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
    UserLookupService,
    UsersService,
)

NOT_CONFIGURED = "No default client configured"


@pytest.fixture(autouse=True)
def reset_default_client() -> Iterator[None]:
    """Start and end each test with no default client."""
    registry._default_client = None
    yield
    registry._default_client = None


@pytest.fixture
def make_client(base_url: str, api_key: str) -> Callable[..., VClient]:
    """Return a builder for clients against the test API."""

    def _make(**kwargs: Any) -> VClient:
        return VClient(base_url=base_url, api_key=api_key, **kwargs)

    return _make


class TestDefaultClient:
    """Tests for registering, reading, and clearing the default client."""

    def test_raises_when_not_configured(self) -> None:
        """Verify reading the default before any client exists fails with a clear error."""
        with pytest.raises(RuntimeError, match=NOT_CONFIGURED):
            default_client()

    def test_new_client_registers_itself(self, make_client) -> None:
        """Verify a new client becomes the default unless it opts out."""
        client = make_client()
        make_client(set_as_default=False)

        assert default_client() is client

    def test_configure_replaces_the_default(self, make_client) -> None:
        """Verify configuring a client makes it the default over an earlier one."""
        make_client()
        second = make_client(set_as_default=False)

        configure_default_client(second)

        assert default_client() is second

    def test_clear_ignores_a_client_that_is_not_the_default(self, make_client) -> None:
        """Verify clearing another client leaves the current default in place."""
        default = make_client()

        clear_default_client(make_client(set_as_default=False))

        assert default_client() is default

    @pytest.mark.parametrize(
        "release",
        [
            pytest.param(clear_default_client, id="clear"),
            pytest.param(VClient.close, id="close"),
            pytest.param(lambda client: client.__exit__(None, None, None), id="context-exit"),
        ],
    )
    def test_releasing_the_default_unregisters_it(self, make_client, release) -> None:
        """Verify a cleared or closed default is never handed out again."""
        client = make_client()

        release(client)

        with pytest.raises(RuntimeError, match=NOT_CONFIGURED):
            default_client()


_FACTORIES = [
    (companies_service, (), {}, CompaniesService),
    (system_service, (), {}, SystemService),
    (user_lookup_service, (), {}, UserLookupService),
    (identity_service, (), {"company_id": "co"}, IdentityService),
    (users_service, ("u",), {"company_id": "co"}, UsersService),
    (campaigns_service, ("u",), {"company_id": "co"}, CampaignsService),
    (books_service, ("camp", "u"), {"company_id": "co"}, BooksService),
    (chapters_service, ("camp", "book", "u"), {"company_id": "co"}, ChaptersService),
    (characters_service, ("u",), {"company_id": "co"}, CharactersService),
    (character_traits_service, ("ch", "u"), {"company_id": "co"}, CharacterTraitsService),
    (character_blueprint_service, ("u",), {"company_id": "co"}, CharacterBlueprintService),
    (dictionary_service, ("u",), {"company_id": "co"}, DictionaryService),
    (dicerolls_service, ("u",), {"company_id": "co"}, DicerollService),
    (options_service, ("u",), {"company_id": "co"}, OptionsService),
    (character_autogen_service, ("u",), {"company_id": "co"}, CharacterAutogenService),
]


@pytest.mark.parametrize(
    ("factory", "args", "kwargs", "service_class"),
    _FACTORIES,
    ids=[factory.__name__ for factory, *_ in _FACTORIES],
)
class TestServiceFactories:
    """Tests for the module-level service factories."""

    def test_raises_when_not_configured(self, factory, args, kwargs, service_class) -> None:
        """Verify each factory fails with a clear error before a client exists."""
        with pytest.raises(RuntimeError, match=NOT_CONFIGURED):
            factory(*args, **kwargs)

    def test_builds_service_on_default_client(
        self, make_client, factory, args, kwargs, service_class
    ) -> None:
        """Verify each factory builds its service on the default client."""
        client = make_client()

        service = factory(*args, **kwargs)

        assert isinstance(service, service_class)
        assert service._client is client


@pytest.mark.parametrize(
    ("default_company_id", "company_id", "expected"),
    [
        ("default-company", None, "default-company"),
        ("default-company", "explicit-company", "explicit-company"),
        (None, "explicit-company", "explicit-company"),
    ],
)
def test_service_company_id_falls_back_to_client_default(
    make_client, default_company_id, company_id, expected
) -> None:
    """Verify an explicit company id wins and the client's default fills in when it is omitted."""
    make_client(default_company_id=default_company_id)

    assert users_service("u", company_id=company_id)._company_id == expected


def test_service_without_any_company_id_raises(make_client) -> None:
    """Verify a company-scoped service needs a company id from the caller or the client."""
    make_client()

    with pytest.raises(ValueError, match="company_id is required"):
        users_service("u")
