"""Shared test assertion helpers and response builders."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from vclient.testing import CampaignFactory, CompanyFactory, UserFactory

from vweb.lib.global_context import GlobalContext

if TYPE_CHECKING:
    from flask.testing import TestResponse
    from pytest_mock import MockerFixture
    from vclient.models import Campaign, Character, Company, User


def assert_success(response: TestResponse) -> None:
    """Assert the response has a 200 status code."""
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def assert_shows_error(response: TestResponse) -> None:
    """Assert the response body contains a daisyUI error alert."""
    body = response.get_data(as_text=True)
    assert "alert-error" in body, "Expected alert-error in response body"


def assert_shows_success(response: TestResponse) -> None:
    """Assert the response body contains a daisyUI success alert."""
    body = response.get_data(as_text=True)
    assert "alert-success" in body, "Expected alert-success in response body"


def assert_redirects_to(response: TestResponse, path: str) -> None:
    """Assert the response is a 302 redirect to the given path."""
    assert response.status_code == 302, f"Expected 302, got {response.status_code}"
    location = response.headers.get("Location", "")
    assert location == path, f"Expected redirect to {path}, got {location}"


def assert_has_element(
    response: TestResponse,
    *,
    id: str | None = None,
    name: str | None = None,
) -> None:
    """Assert the response body contains an HTML element with the given id or name attribute.

    Args:
        response: The Flask test response.
        id: Expected element id attribute.
        name: Expected element name attribute.

    Raises:
        ValueError: If neither id nor name is provided.
    """
    if id is None and name is None:
        msg = "assert_has_element requires at least one of id or name"
        raise ValueError(msg)

    body = response.get_data(as_text=True)

    if id is not None:
        assert f'id="{id}"' in body, f'Expected element with id="{id}" in response body'

    if name is not None:
        assert f'name="{name}"' in body, f'Expected element with name="{name}" in response body'


def assert_has_hx_attr(
    response: TestResponse,
    attr: str,
    value: str | None = None,
) -> None:
    """Assert the response body contains an HTMX attribute, optionally with a specific value.

    Args:
        response: The Flask test response.
        attr: The HTMX attribute name (e.g., "hx-get", "hx-swap-oob").
        value: Optional expected value for the attribute.
    """
    body = response.get_data(as_text=True)

    expected = f'{attr}="{value}"' if value is not None else attr

    assert expected in body, f"Expected {expected} in response body"


def build_global_context(
    *,
    user_role: str,
    company: Company | None = None,
    user: User | None = None,
    campaign: Campaign | None = None,
    characters: list[Character] | None = None,
) -> GlobalContext:
    """Build a GlobalContext with sensible defaults for testing.

    Callers must pass `user_role` explicitly to avoid silent role mismatches
    between test files that previously defaulted to different roles.

    Args:
        user_role: The role for the test user (e.g., "STORYTELLER", "PLAYER").
        company: Optional custom Company. Defaults to factory-built.
        user: Optional custom User. Defaults to factory-built with id="test-user-id".
        campaign: Optional custom Campaign. Defaults to factory-built.
        characters: Optional list of characters to associate with the campaign.

    Returns:
        A populated GlobalContext ready for use in tests.
    """
    if user is not None and user_role != user.role:
        msg = (
            f"user_role='{user_role}' conflicts with user.role='{user.role}'. "
            "When passing a custom user, ensure user_role matches or omit the custom user."
        )
        raise ValueError(msg)

    company = company or CompanyFactory.build(name="Test Company")
    user = user or UserFactory.build(
        id="test-user-id",
        name_first="Test",
        name_last="User",
        company_id="test-company-id",
        role=user_role,
    )
    campaign = campaign or CampaignFactory.build(name="Test Campaign")

    characters = characters or []

    return GlobalContext(
        company=company,
        users=[user],
        campaigns=[campaign],
        books_by_campaign={campaign.id: []},
        characters_by_campaign={campaign.id: characters},
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )


def make_cache_store_mock(mocker: MockerFixture, module_path: str) -> dict:
    """Create a dict-backed mock of Flask-Caching and patch it at the given module path.

    Each cache test file imports `cache` at its own module path. This function
    patches the correct one and returns the backing dict for assertions.

    Args:
        mocker: The pytest-mock fixture.
        module_path: Dotted path to the cache object (e.g., "vweb.lib.options_cache.cache").

    Returns:
        The dict backing the mock cache, for direct inspection in tests.
    """
    store: dict = {}
    mock_cache = MagicMock()
    mock_cache.get.side_effect = store.get
    mock_cache.set.side_effect = lambda key, value, timeout=None: store.__setitem__(key, value)
    mock_cache.delete.side_effect = lambda key: store.pop(key, None)
    mock_cache.clear.side_effect = store.clear
    mocker.patch(module_path, mock_cache)
    return store


def setup_form_options(mocker: MockerFixture, module_path: str, **overrides: object) -> MagicMock:
    """Patch fetch_form_options at the given module path with sensible defaults.

    Each route module imports `fetch_form_options` into its own namespace,
    so the patch target must be route-specific.

    Args:
        mocker: The pytest-mock fixture.
        module_path: Dotted path to fetch_form_options (e.g.,
            "vweb.routes.character_create.fetch_form_options").
        **overrides: Keys to override in the default form options dict.

    Returns:
        The MagicMock wrapping fetch_form_options, for further assertions if needed.
    """
    defaults: dict[str, object] = {
        "character_classes": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "MORTAL"],
        "experience_levels": ["NEW", "INTERMEDIATE", "ADVANCED"],
        "skill_focuses": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
        "concepts": [],
        "vampire_clans": [],
        "werewolf_tribes": [],
        "werewolf_auspices": [],
    }
    defaults.update(overrides)
    return mocker.patch(module_path, return_value=defaults)
