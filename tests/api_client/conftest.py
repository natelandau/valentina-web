"""Shared test fixtures."""

import contextlib
from collections.abc import Iterator

import pytest
import pytest_httpx2  # noqa: F401  importing registers respx's "httpcore2" mocker
import respx.mocks
from loguru import logger
from polyfactory.factories.pydantic_factory import ModelFactory

from tests.api_client.payloads import page, wire
from vweb.api_client.models import CharacterTraitSpecialty, VampireAttributes
from vweb.api_client.testing import (
    CharacterFactory,
    CharacterTraitFactory,
    CompanyFactory,
    RollStatisticsFactory,
    TraitFactory,
    UserFactory,
)

# httpx2 ships its own httpcore fork (httpcore2). respx patches httpcore by module
# path, so its default mocker only intercepts upstream httpx. Point the default mocker
# at pytest-httpx2's "httpcore2" targets so every respx fixture and decorator in the
# suite intercepts httpx2 without per-callsite `using=` changes.
# respx still checks mocked responses against upstream httpx.Response, so tests build
# them with respx.MockResponse rather than httpx2.Response.
_HTTPX2_MOCKER = "httpcore2"
# Fail loudly at collection if the mocker is missing (e.g. a respx/pytest-httpx2 change):
# a silent fallback to the default "httpcore" mocker would let httpx2 requests escape the
# mock and hit the real network instead of raising here.
if _HTTPX2_MOCKER not in respx.mocks.Mocker.registry:
    msg = (
        f"respx mocker {_HTTPX2_MOCKER!r} is not registered; ensure pytest-httpx2 is "
        "installed so httpx2 requests are intercepted instead of reaching the network."
    )
    raise RuntimeError(msg)
respx.mocks.DEFAULT_MOCKER = _HTTPX2_MOCKER

_SpecialtyFactory = ModelFactory.create_factory(CharacterTraitSpecialty)


@pytest.fixture
def api_key() -> str:
    """Return a test API key."""
    return "test-api-key-12345"


@pytest.fixture
def base_url() -> str:
    """Return a test base URL."""
    return "https://api.test.valentina-noir.com"


@pytest.fixture
def caplog(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Route loguru records into ``caplog`` for client tests.

    The client logs through loguru only. A per-test sink is required because
    ``create_app`` removes every loguru sink, so one added at import time would not survive.
    """
    sink_id = logger.add(
        caplog.handler,
        level=0,
        format="{message}",
        # Handler.handle() skips level checks, so honor `caplog.at_level` here
        filter=lambda record: record["level"].no >= caplog.handler.level,
    )
    yield caplog
    # A test that resets loguru sinks has already removed ours
    with contextlib.suppress(ValueError):
        logger.remove(sink_id)


@pytest.fixture
def statistics_response_data() -> dict:
    """Return roll statistics response data."""
    return wire(RollStatisticsFactory.build(total_rolls=100, success_percentage=50.0))


@pytest.fixture
def trait_response_data() -> dict:
    """Return trait response data."""
    return wire(TraitFactory.build(id="trait123", name="Strength"))


@pytest.fixture
def character_trait_response_data(trait_response_data: dict) -> dict:
    """Return character trait response data."""
    return wire(
        CharacterTraitFactory.build(
            id="ct123",
            character_id="char123",
            value=3,
            trait=trait_response_data,
            specialties=[_SpecialtyFactory.build(id="spec123", name="Knives")],
        )
    )


@pytest.fixture
def character_response_data() -> dict:
    """Return character response data for a V5 vampire."""
    return wire(
        CharacterFactory.build(
            id="char123",
            name_first="John",
            name_last="Doe",
            character_class="VAMPIRE",
            game_version="V5",
            character_trait_ids=["trait1", "trait2"],
            vampire_attributes=VampireAttributes(
                clan_name="Ventrue", generation=10, sire="Ancient One"
            ),
        )
    )


@pytest.fixture
def user_response_data() -> dict:
    """Return user response data."""
    return wire(
        UserFactory.build(
            id="507f1f77bcf86cd799439011",
            name_first="Test",
            name_last="User",
            username="testuser",
            email="test@example.com",
        )
    )


@pytest.fixture
def company_response_data() -> dict:
    """Return company response data."""
    return wire(
        CompanyFactory.build(
            id="507f1f77bcf86cd799439011", name="Test Company", email="test@example.com"
        )
    )


@pytest.fixture
def paginated_companies_response(company_response_data: dict) -> dict:
    """Return a one-item paginated companies response."""
    return page(company_response_data)
