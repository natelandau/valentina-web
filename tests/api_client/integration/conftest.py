"""Integration test fixtures."""

from collections.abc import Iterator

import pytest
import respx

from vweb.api_client import VClient
from vweb.api_client.services.base import BaseService


@pytest.fixture
def mock_api(base_url) -> Iterator[respx.Router]:
    """Return a respx mock router for the API."""
    with respx.mock(base_url=base_url, assert_all_called=False) as respx_mock:
        yield respx_mock


@pytest.fixture
def vclient(base_url, api_key) -> Iterator[VClient]:
    """Return a VClient for testing."""
    client = VClient(base_url=base_url, api_key=api_key, timeout=10.0)
    yield client
    client.close()


@pytest.fixture
def vclient_with_auto_idempotency(base_url, api_key) -> Iterator[VClient]:
    """Return a VClient with auto_idempotency_keys enabled for testing."""
    client = VClient(
        base_url=base_url,
        api_key=api_key,
        auto_idempotency_keys=True,
    )
    yield client
    client.close()


class ConcreteService(BaseService):
    """Concrete implementation of BaseService for testing."""


@pytest.fixture
def base_service(vclient) -> ConcreteService:
    """Return a BaseService instance for testing."""
    return ConcreteService(vclient)


@pytest.fixture
def base_service_with_auto_idempotency(
    vclient_with_auto_idempotency,
) -> ConcreteService:
    """Return a BaseService instance with auto_idempotency_keys enabled."""
    return ConcreteService(vclient_with_auto_idempotency)
