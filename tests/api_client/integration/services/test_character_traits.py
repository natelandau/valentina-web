"""Integration tests for CharacterTraitsService."""

import json

import pytest
import respx
from respx import MockResponse

from tests.api_client.payloads import page
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import (
    ConflictError,
    NotFoundError,
    RequestValidationError,
    ValidationError,
)
from vweb.api_client.models import (
    BulkAssignTraitResponse,
    CharacterTrait,
    CharacterTraitAdd,
    CharacterTraitValueOptionsResponse,
    CounterTracker,
    PaginatedResponse,
    StainsTracker,
    TrackerStateSet,
)


@pytest.fixture
def paginated_character_trait_response(character_trait_response_data: dict) -> dict:
    """Return a one-item paginated character traits response."""
    return page(character_trait_response_data)


@pytest.fixture
def character_trait_value_options_response_data(trait_response_data: dict) -> dict:
    """Return a response data for the value options for a character trait."""
    return {
        "name": "Strength",
        "current_value": 2,
        "trait": trait_response_data,
        "xp_current": 0,
        "starting_points_current": 0,
        "options": {
            "1": {
                "direction": "decrease",
                "point_change": 10,
                "can_use_xp": True,
                "xp_after": 10,
                "can_use_starting_points": True,
                "starting_points_after": 10,
            },
            "3": {
                "direction": "increase",
                "point_change": 15,
                "can_use_xp": False,
                "xp_after": -15,
                "can_use_starting_points": False,
                "starting_points_after": -15,
            },
            "4": {
                "direction": "increase",
                "point_change": 35,
                "can_use_xp": False,
                "xp_after": -35,
                "can_use_starting_points": False,
                "starting_points_after": -35,
            },
            "5": {
                "direction": "increase",
                "point_change": 60,
                "can_use_xp": False,
                "xp_after": -60,
                "can_use_starting_points": False,
                "starting_points_after": -60,
            },
        },
    }


class TestCharacterTraitsServiceGetPage:
    """Tests for CharacterTraitsService.get_page method."""

    @respx.mock
    def test_get_page(self, vclient, base_url, paginated_character_trait_response) -> None:
        """Verify getting a page of character traits returns paginated response."""
        # Given: A mocked character traits list endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=paginated_character_trait_response))

        # When: Requesting a page of character traits
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_page()

        # Then: The route was called and response is paginated
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], CharacterTrait)
        assert result.items[0].trait.name == "Strength"
        assert result.items[0].value == 3
        assert result.total == 1

    @respx.mock
    def test_get_page_with_pagination_params(
        self, vclient, base_url, paginated_character_trait_response
    ) -> None:
        """Verify get_page passes pagination parameters correctly."""
        # Given: A mocked endpoint expecting pagination params
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "20", "offset": "10"},
        ).mock(return_value=MockResponse(200, json=paginated_character_trait_response))

        # When: Requesting with pagination
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_page(limit=20, offset=10)

        # Then: The route was called with correct params
        assert route.called
        assert isinstance(result, PaginatedResponse)

    @respx.mock
    def test_get_page_with_category_filter(
        self, vclient, base_url, paginated_character_trait_response
    ) -> None:
        """Verify get_page filters by category_id."""
        # Given: A mocked endpoint expecting filter params
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "10", "offset": "0", "category_id": "cat123"},
        ).mock(return_value=MockResponse(200, json=paginated_character_trait_response))

        # When: Requesting with filter
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_page(category_id="cat123")

        # Then: The route was called with correct params
        assert route.called
        assert len(result.items) == 1

    @respx.mock
    def test_get_page_with_is_rollable_true(
        self, vclient, base_url, paginated_character_trait_response
    ) -> None:
        """Verify get_page passes is_rollable=True filter correctly."""
        # Given: A mocked endpoint expecting is_rollable param
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "10", "offset": "0", "is_rollable": "true"},
        ).mock(return_value=MockResponse(200, json=paginated_character_trait_response))

        # When: Requesting with is_rollable filter
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_page(is_rollable=True)

        # Then: The route was called with correct params
        assert route.called
        assert len(result.items) == 1

    @respx.mock
    def test_get_page_with_is_rollable_false(
        self, vclient, base_url, paginated_character_trait_response
    ) -> None:
        """Verify get_page passes is_rollable=False filter correctly."""
        # Given: A mocked endpoint expecting is_rollable=False param
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "10", "offset": "0", "is_rollable": "false"},
        ).mock(return_value=MockResponse(200, json=paginated_character_trait_response))

        # When: Requesting with is_rollable=False filter
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_page(is_rollable=False)

        # Then: The route was called with correct params
        assert route.called
        assert len(result.items) == 1


class TestCharacterTraitsServiceGet:
    """Tests for CharacterTraitsService.get method."""

    @respx.mock
    def test_get_character_trait(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify getting a character trait returns CharacterTrait object."""
        # Given: A mocked character trait endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAIT.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}"
        ).mock(return_value=MockResponse(200, json=character_trait_response_data))

        # When: Requesting a character trait
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get("ct123")

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.id == "ct123"
        assert result.character_id == "char123"
        assert result.value == 3
        assert result.trait.name == "Strength"

    @respx.mock
    def test_get_character_trait_not_found(self, vclient, base_url) -> None:
        """Verify getting a non-existent character trait raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAIT.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='nonexistent')}"
        ).mock(
            return_value=MockResponse(
                404, json={"detail": "Character trait not found", "status_code": 404}
            )
        )

        # When/Then: Requesting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.character_traits("char123", "on-behalf-of-user", company_id="company123").get(
                "nonexistent"
            )

        assert route.called


class TestCharacterTraitsServiceListAll:
    """Tests for CharacterTraitsService.list_all method."""

    @respx.mock
    def test_list_all_character_traits(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify list_all returns all character traits across pages."""
        # Given: A mocked endpoint that returns paginated results
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Requesting all character traits
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).list_all()

        # Then: All character traits are returned as a list
        assert route.called
        assert len(result) == 1
        assert isinstance(result[0], CharacterTrait)
        assert result[0].trait.name == "Strength"

    @respx.mock
    def test_list_all_with_category_filter(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify list_all filters by category_id."""
        # Given: A mocked endpoint expecting filter params
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "100", "offset": "0", "category_id": "cat123"},
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Requesting with filter
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).list_all(category_id="cat123")

        # Then: Filtered results are returned
        assert route.called
        assert len(result) == 1

    @respx.mock
    def test_list_all_with_is_rollable_filter(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify list_all filters by is_rollable."""
        # Given: A mocked endpoint expecting is_rollable param
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "100", "offset": "0", "is_rollable": "true"},
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Requesting with is_rollable filter
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).list_all(is_rollable=True)

        # Then: Filtered results are returned
        assert route.called
        assert len(result) == 1


class TestCharacterTraitsServiceIterAll:
    """Tests for CharacterTraitsService.iter_all method."""

    @respx.mock
    def test_iter_all_character_traits(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify iter_all yields character traits across pages."""
        # Given: A mocked endpoint
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Iterating through all character traits
        traits = list(
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).iter_all()
        )

        # Then: All character traits are yielded
        assert route.called
        assert len(traits) == 1
        assert isinstance(traits[0], CharacterTrait)

    @respx.mock
    def test_iter_all_with_filter(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify iter_all filters by category_id."""
        # Given: A mocked endpoint expecting filter params
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "100", "offset": "0", "category_id": "cat456"},
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Iterating with filter
        traits = list(
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).iter_all(category_id="cat456")
        )

        # Then: Filtered results are yielded
        assert route.called
        assert len(traits) == 1

    @respx.mock
    def test_iter_all_with_is_rollable_filter(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify iter_all filters by is_rollable."""
        # Given: A mocked endpoint expecting is_rollable param
        paginated_response = page(character_trait_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "100", "offset": "0", "is_rollable": "false"},
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Iterating with is_rollable filter
        traits = list(
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).iter_all(is_rollable=False)
        )

        # Then: Filtered results are yielded
        assert route.called
        assert len(traits) == 1


class TestCharacterTraitsServiceAssign:
    """Tests for CharacterTraitsService.assign method."""

    @respx.mock
    def test_assign_trait(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify assigning an existing trait to a character."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(201, json=character_trait_response_data))

        # When: Assigning a trait
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).assign(trait_id="trait123", value=3, currency="XP")

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.id == "ct123"
        assert result.value == 3

        # Verify request body
        body = json.loads(route.calls[0].request.content)
        assert body["trait_id"] == "trait123"
        assert body["value"] == 3

    @respx.mock
    def test_assign_trait_zero_value(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify assigning a trait with value zero."""
        # Given: A mocked create endpoint with zero value response
        response_data = {**character_trait_response_data, "value": 0}
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(201, json=response_data))

        # When: Assigning a trait with value 0
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).assign(trait_id="trait123", value=0, currency="XP")

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.value == 0

    @respx.mock
    def test_assign_trait_not_found(self, vclient, base_url) -> None:
        """Verify assigning a non-existent trait raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(
            return_value=MockResponse(404, json={"detail": "Trait not found", "status_code": 404})
        )

        # When/Then: Assigning raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).assign(trait_id="nonexistent", value=1, currency="XP")

        assert route.called


class TestCharacterTraitsServiceCreate:
    """Tests for CharacterTraitsService.create method."""

    @respx.mock
    def test_create_trait_minimal(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify creating a custom trait with minimal fields."""
        # Given: A mocked create endpoint
        response_data = {
            **character_trait_response_data,
            "trait": {
                **character_trait_response_data["trait"],
                "name": "Custom Skill",
                "custom_for_character_id": "char123",
            },
        }
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_CREATE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(201, json=response_data))

        # When: Creating a custom trait with required fields only
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).create(
            name="Custom Skill",
            category_id="cat123",
            currency="XP",
        )

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.trait.name == "Custom Skill"

        # Verify request body contains required fields
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "Custom Skill"
        assert body["category_id"] == "cat123"
        assert body["currency"] == "XP"
        # Defaults (max_value, min_value, is_rollable) are not sent unless explicitly set;
        # the server defaults custom traits to rollable.
        assert "is_rollable" not in body

    @respx.mock
    def test_create_trait_all_options(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify creating a custom trait with all optional fields."""
        # Given: A mocked create endpoint
        response_data = {
            **character_trait_response_data,
            "value": 1,
            "trait": {
                **character_trait_response_data["trait"],
                "name": "Custom Background",
                "description": "A custom background trait",
                "max_value": 10,
                "min_value": 1,
                "show_when_zero": False,
                "initial_cost": 3,
                "upgrade_cost": 2,
                "custom_for_character_id": "char123",
            },
        }
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_CREATE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(201, json=response_data))

        # When: Creating a custom trait with all fields
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).create(
            name="Custom Background",
            category_id="backgrounds_cat",
            currency="STARTING_POINTS",
            description="A custom background trait",
            max_value=10,
            min_value=1,
            show_when_zero=False,
            is_rollable=False,
            initial_cost=3,
            upgrade_cost=2,
            count_based_cost_multiplier=4,
        )

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.trait.name == "Custom Background"

        # Verify request body contains all fields
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "Custom Background"
        assert body["category_id"] == "backgrounds_cat"
        assert body["currency"] == "STARTING_POINTS"
        assert body["description"] == "A custom background trait"
        assert body["max_value"] == 10
        assert body["min_value"] == 1
        assert body["show_when_zero"] is False
        assert body["is_rollable"] is False
        assert body["initial_cost"] == 3
        assert body["upgrade_cost"] == 2
        assert body["count_based_cost_multiplier"] == 4
        assert "value" not in body

    @respx.mock
    def test_create_trait_no_cost_currency(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify creating a custom trait with NO_COST currency."""
        # Given: A mocked create endpoint
        response_data = {**character_trait_response_data, "value": 1}
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_CREATE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(201, json=response_data))

        # When: Creating a custom trait paid for with NO_COST
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).create(
            name="Custom Trait",
            category_id="cat123",
            currency="NO_COST",
        )

        # Then: The trait is created at a value of 1 and currency is sent
        assert route.called
        assert result.value == 1

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["currency"] == "NO_COST"
        assert "value" not in body

    @respx.mock
    def test_create_trait_not_found_category(self, vclient, base_url) -> None:
        """Verify creating a trait with invalid category raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_CREATE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(
            return_value=MockResponse(
                404, json={"detail": "Parent category not found", "status_code": 404}
            )
        )

        # When/Then: Creating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).create(
                name="Custom Trait",
                category_id="nonexistent_cat",
                currency="XP",
            )

        assert route.called


class TestCharacterTraitsServiceDelete:
    """Tests for CharacterTraitsService.delete method."""

    @respx.mock
    def test_delete_trait(self, vclient, base_url) -> None:
        """Verify deleting a character trait."""
        # Given: A mocked delete endpoint
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER_TRAIT.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}"
        ).mock(return_value=MockResponse(204))

        # When: Deleting the trait
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).delete("ct123")

        # Then: The route was called and None is returned
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_trait_with_currency(self, vclient, base_url) -> None:
        """Verify deleting a character trait with a currency parameter."""
        # Given: A mocked delete endpoint expecting currency param
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER_TRAIT.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}",
            params={"currency": "XP"},
        ).mock(return_value=MockResponse(204))

        # When: Deleting the trait with currency
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).delete("ct123", currency="XP")

        # Then: The route was called with currency param and None is returned
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_trait_not_found(self, vclient, base_url) -> None:
        """Verify deleting a non-existent trait raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER_TRAIT.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='nonexistent')}"
        ).mock(
            return_value=MockResponse(404, json={"detail": "Trait not found", "status_code": 404})
        )

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).delete("nonexistent")

        assert route.called


class TestCharacterTraitsServiceMultiplePages:
    """Tests for CharacterTraitsService pagination across multiple pages."""

    @respx.mock
    def test_iter_all_multiple_pages(self, vclient, base_url, trait_response_data) -> None:
        """Verify iter_all handles multiple pages correctly."""
        # Given: Two pages of character traits
        trait1 = {
            "id": "ct1",
            "character_id": "char123",
            "value": 1,
            "trait": {**trait_response_data, "id": "trait1", "name": "Strength"},
        }
        trait2 = {
            "id": "ct2",
            "character_id": "char123",
            "value": 2,
            "trait": {**trait_response_data, "id": "trait2", "name": "Dexterity"},
        }

        page1_response = page(trait1, limit=1, total=2)
        page2_response = page(trait2, limit=1, offset=1, total=2)

        route1 = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "1", "offset": "0"},
        ).mock(return_value=MockResponse(200, json=page1_response))

        route2 = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAITS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params={"limit": "1", "offset": "1"},
        ).mock(return_value=MockResponse(200, json=page2_response))

        # When: Iterating through all character traits with limit=1
        traits = list(
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).iter_all(limit=1)
        )

        # Then: All character traits from both pages are yielded
        assert route1.called
        assert route2.called
        assert len(traits) == 2
        assert traits[0].trait.name == "Strength"
        assert traits[1].trait.name == "Dexterity"


class TestCharacterTraitsServiceGetValueOptions:
    """Tests for CharacterTraitsService.get_value_options method."""

    @respx.mock
    def test_get_value_options(
        self, vclient, base_url, character_trait_value_options_response_data
    ) -> None:
        """Verify getting the value options for a character trait."""
        # Given: A mocked get value options endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_VALUE_OPTIONS.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}",
        ).mock(return_value=MockResponse(200, json=character_trait_value_options_response_data))

        # When: Getting the value options for a character trait
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).get_value_options("ct123")

        # Then: The route was called and the value options are returned
        assert route.called
        assert result == CharacterTraitValueOptionsResponse.model_validate(
            character_trait_value_options_response_data
        )


class TestCharacterTraitsServiceChangeValue:
    """Tests for CharacterTraitsService.change_value method."""

    @respx.mock
    def test_change_value(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify changing the value of a character trait."""
        # Given: A mocked change value endpoint
        route = respx.put(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_VALUE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}",
        ).mock(return_value=MockResponse(200, json=character_trait_response_data))

        # When: Changing the value of a character trait
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).change_value("ct123", new_value=4, currency="XP")

        # Then: The route was called and character trait is returned
        assert route.called
        assert isinstance(result, CharacterTrait)
        assert result.trait.name == "Strength"
        assert result.specialties[0].name == "Knives"

    @respx.mock
    def test_change_value_conflict(self, vclient, base_url) -> None:
        """Verify a 409 from a concurrent value change raises ConflictError."""
        # Given: A change value endpoint that reports a concurrent change
        respx.put(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_VALUE.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123', character_trait_id='ct123')}",
        ).mock(
            return_value=MockResponse(
                409, json={"status": 409, "title": "Conflict", "detail": "Trait value changed"}
            )
        )

        # When/Then: Changing the value raises ConflictError
        with pytest.raises(ConflictError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).change_value("ct123", new_value=4, currency="XP")


class TestCharacterTraitsServiceSpecialties:
    """Tests for CharacterTraitsService specialty methods."""

    @respx.mock
    def test_add_specialty(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify adding a specialty posts the name and currency."""
        # Given: A mocked add specialty endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTIES.format(company_id='company123', character_id='char123', character_trait_id='ct123')}",
        ).mock(return_value=MockResponse(201, json=character_trait_response_data))

        # When: Adding a specialty paid with XP
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).add_specialty("ct123", name="Knives", currency="XP")

        # Then: The request body carries the name and currency
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"name": "Knives", "currency": "XP"}
        assert isinstance(result, CharacterTrait)
        assert result.specialties[0].id == "spec123"

    @respx.mock
    def test_add_specialty_default_currency(
        self, vclient, base_url, character_trait_response_data
    ) -> None:
        """Verify add_specialty sends NO_COST when no currency is given."""
        # Given: A mocked add specialty endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTIES.format(company_id='company123', character_id='char123', character_trait_id='ct123')}",
        ).mock(return_value=MockResponse(201, json=character_trait_response_data))

        # When: Adding a specialty without a currency
        vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).add_specialty("ct123", name="Knives")

        # Then: The request body uses NO_COST
        assert json.loads(route.calls.last.request.content) == {
            "name": "Knives",
            "currency": "NO_COST",
        }

    def test_add_specialty_name_too_short(self, vclient) -> None:
        """Verify a short name fails client-side before any request."""
        # When/Then: Adding a two-character specialty raises
        with pytest.raises(RequestValidationError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).add_specialty("ct123", name="ab")

    @respx.mock
    def test_add_specialty_validation_error(self, vclient, base_url) -> None:
        """Verify a 400 from the server raises ValidationError."""
        # Given: An endpoint rejecting the specialty
        respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTIES.format(company_id='company123', character_id='char123', character_trait_id='ct123')}",
        ).mock(
            return_value=MockResponse(
                400, json={"status": 400, "title": "Bad Request", "detail": "Not an ability"}
            )
        )

        # When/Then: Adding the specialty raises ValidationError
        with pytest.raises(ValidationError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).add_specialty("ct123", name="Knives")

    @respx.mock
    def test_update_specialty(self, vclient, base_url, character_trait_response_data) -> None:
        """Verify renaming a specialty patches the new name."""
        # Given: A mocked update specialty endpoint
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTY.format(company_id='company123', character_id='char123', character_trait_id='ct123', specialty_id='spec123')}",
        ).mock(return_value=MockResponse(200, json=character_trait_response_data))

        # When: Renaming the specialty
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).update_specialty("ct123", "spec123", name="Knives")

        # Then: The request body carries only the name
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"name": "Knives"}
        assert isinstance(result, CharacterTrait)

    @respx.mock
    def test_delete_specialty(self, vclient, base_url) -> None:
        """Verify deleting a specialty calls the delete endpoint."""
        # Given: A mocked delete specialty endpoint
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTY.format(company_id='company123', character_id='char123', character_trait_id='ct123', specialty_id='spec123')}",
        ).mock(return_value=MockResponse(204))

        # When: Deleting the specialty
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).delete_specialty("ct123", "spec123")

        # Then: The route was called and nothing is returned
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_specialty_not_found(self, vclient, base_url) -> None:
        """Verify a 404 for an unknown specialty raises NotFoundError."""
        # Given: An endpoint that cannot find the specialty
        respx.delete(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_SPECIALTY.format(company_id='company123', character_id='char123', character_trait_id='ct123', specialty_id='missing')}",
        ).mock(
            return_value=MockResponse(
                404, json={"status": 404, "title": "Not Found", "detail": "Specialty not found"}
            )
        )

        # When/Then: Deleting the specialty raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).delete_specialty("ct123", "missing")


@pytest.fixture
def bulk_assign_response_data(character_trait_response_data: dict) -> dict:
    """Return sample bulk assign response data with mixed results."""
    return {
        "succeeded": [
            {"trait_id": "trait1", "character_trait": character_trait_response_data},
        ],
        "failed": [
            {"trait_id": "trait2", "error": "Not enough XP to add trait"},
        ],
    }


@pytest.fixture
def bulk_assign_all_success_response_data(character_trait_response_data: dict) -> dict:
    """Return sample bulk assign response with all successes."""
    return {
        "succeeded": [
            {"trait_id": "trait1", "character_trait": character_trait_response_data},
            {
                "trait_id": "trait2",
                "character_trait": {**character_trait_response_data, "id": "ct456"},
            },
        ],
        "failed": [],
    }


class TestCharacterTraitsServiceBulkAssign:
    """Tests for CharacterTraitsService.bulk_assign method."""

    @respx.mock
    def test_bulk_assign_success(
        self, vclient, base_url, bulk_assign_all_success_response_data
    ) -> None:
        """Verify bulk assigning traits returns BulkAssignTraitResponse with all successes."""
        # Given: A mocked bulk-assign endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_BULK_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=bulk_assign_all_success_response_data))

        # When: Bulk assigning traits
        items = [
            CharacterTraitAdd(trait_id="trait1", value=2, currency="NO_COST"),
            CharacterTraitAdd(trait_id="trait2", value=1, currency="XP"),
        ]
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).bulk_assign(items)

        # Then: The route was called and response is parsed correctly
        assert route.called
        assert isinstance(result, BulkAssignTraitResponse)
        assert len(result.succeeded) == 2
        assert len(result.failed) == 0
        assert result.succeeded[0].trait_id == "trait1"
        assert isinstance(result.succeeded[0].character_trait, CharacterTrait)

        # Verify request body is a JSON list
        body = json.loads(route.calls[0].request.content)
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["trait_id"] == "trait1"
        assert body[0]["value"] == 2
        assert body[0]["currency"] == "NO_COST"

    @respx.mock
    def test_bulk_assign_mixed_results(self, vclient, base_url, bulk_assign_response_data) -> None:
        """Verify bulk assign with mixed succeeded and failed items."""
        # Given: A mocked endpoint returning mixed results
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_BULK_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=bulk_assign_response_data))

        # When: Bulk assigning traits
        items = [
            CharacterTraitAdd(trait_id="trait1", value=2, currency="NO_COST"),
            CharacterTraitAdd(trait_id="trait2", value=1, currency="XP"),
        ]
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).bulk_assign(items)

        # Then: Both succeeded and failed lists are populated
        assert route.called
        assert len(result.succeeded) == 1
        assert len(result.failed) == 1
        assert result.failed[0].trait_id == "trait2"
        assert result.failed[0].error == "Not enough XP to add trait"

    @respx.mock
    def test_bulk_assign_empty_list(self, vclient, base_url) -> None:
        """Verify bulk assign with empty list returns empty response."""
        # Given: A mocked endpoint returning empty results
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_BULK_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json={"succeeded": [], "failed": []}))

        # When: Bulk assigning an empty list
        result = vclient.character_traits(
            "char123", "on-behalf-of-user", company_id="company123"
        ).bulk_assign([])

        # Then: Both lists are empty
        assert route.called
        assert result.succeeded == []
        assert result.failed == []

    @respx.mock
    def test_bulk_assign_validation_error(self, vclient, base_url) -> None:
        """Verify bulk assign over batch limit raises ValidationError."""
        # Given: A mocked 400 response for exceeding batch limit
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_TRAIT_BULK_ASSIGN.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(
            return_value=MockResponse(
                400,
                json={"detail": "Batch size must not exceed 200 items", "status_code": 400},
            )
        )

        # When/Then: Bulk assigning raises ValidationError
        items = [CharacterTraitAdd(trait_id="t1", value=1, currency="NO_COST")]
        with pytest.raises(ValidationError):
            vclient.character_traits(
                "char123", "on-behalf-of-user", company_id="company123"
            ).bulk_assign(items)

        assert route.called


def _tracker_url(base_url: str, endpoint: str) -> str:
    """Build a tracker endpoint URL for the standard test ids."""
    return f"{base_url}{endpoint.format(company_id='company123', character_id='char123', character_trait_id='ct123')}"


COUNTER_TRACKER = {"type": "COUNTER", "size": 5, "current": 3}
STAINS_TRACKER = {"type": "STAINS", "humanity": 7, "stain_capacity": 3, "stains": 4}


class TestCharacterTraitsServiceTracker:
    """Tests for CharacterTraitsService tracker methods."""

    @pytest.fixture
    def service(self, vclient):
        """Return a character traits service for the standard test ids."""
        return vclient.character_traits("char123", "on-behalf-of-user", company_id="company123")

    @respx.mock
    def test_get_tracker(self, service, base_url) -> None:
        """Verify get_tracker returns the typed tracker variant."""
        # Given: A mocked tracker endpoint returning a counter
        respx.get(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER)).mock(
            return_value=MockResponse(200, json=COUNTER_TRACKER)
        )

        # When: Getting the tracker
        result = service.get_tracker("ct123")

        # Then: A CounterTracker is returned
        assert isinstance(result, CounterTracker)
        assert result.current == 3

    @respx.mock
    def test_get_tracker_not_found(self, service, base_url) -> None:
        """Verify a trait without a tracker raises NotFoundError."""
        # Given: The endpoint returns 404
        respx.get(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER)).mock(
            return_value=MockResponse(
                404, json={"status": 404, "title": "Not Found", "detail": "Trait has no tracker"}
            )
        )

        # When/Then: Getting the tracker raises
        with pytest.raises(NotFoundError):
            service.get_tracker("ct123")

    @respx.mock
    def test_set_tracker_kwargs(self, service, base_url) -> None:
        """Verify set_tracker sends a zero value and nothing else."""
        # Given: A mocked set tracker endpoint
        route = respx.put(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER)).mock(
            return_value=MockResponse(200, json=COUNTER_TRACKER)
        )

        # When: Setting current to zero
        result = service.set_tracker("ct123", current=0)

        # Then: Only current is sent and the response is typed
        assert json.loads(route.calls.last.request.content) == {"current": 0}
        assert isinstance(result, CounterTracker)

    @respx.mock
    def test_set_tracker_request_model(self, service, base_url) -> None:
        """Verify set_tracker accepts a TrackerStateSet."""
        # Given: A mocked set tracker endpoint
        route = respx.put(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER)).mock(
            return_value=MockResponse(200, json=STAINS_TRACKER)
        )

        # When: Setting stains with a request model
        result = service.set_tracker("ct123", TrackerStateSet(stains=2))

        # Then: Only stains is sent and the response is typed
        assert json.loads(route.calls.last.request.content) == {"stains": 2}
        assert isinstance(result, StainsTracker)

    def test_set_tracker_removed_field_rejected(self, service) -> None:
        """Verify a removed damage field fails before any request."""
        # When/Then: Setting superficial damage raises
        with pytest.raises(RequestValidationError):
            service.set_tracker("ct123", superficial=1)

    def test_set_tracker_negative_rejected(self, service) -> None:
        """Verify a negative value fails before any request."""
        # When/Then: Setting a negative value raises
        with pytest.raises(RequestValidationError):
            service.set_tracker("ct123", current=-1)

    @respx.mock
    def test_apply_tracker_action_defaults(self, service, base_url) -> None:
        """Verify an action sends only action and amount."""
        # Given: A mocked action endpoint
        route = respx.post(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS)).mock(
            return_value=MockResponse(200, json=COUNTER_TRACKER)
        )

        # When: Spending two points
        result = service.apply_tracker_action("ct123", "spend", amount=2)

        # Then: Only action and amount are sent
        assert json.loads(route.calls.last.request.content) == {"action": "spend", "amount": 2}
        assert isinstance(result, CounterTracker)

    @respx.mock
    def test_apply_tracker_action_stains(self, service, base_url) -> None:
        """Verify a stain action returns a StainsTracker."""
        # Given: An action endpoint returning a stains tracker
        respx.post(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS)).mock(
            return_value=MockResponse(200, json=STAINS_TRACKER)
        )

        # When: Adding a stain
        result = service.apply_tracker_action("ct123", "add_stain")

        # Then: The stains tracker is returned
        assert isinstance(result, StainsTracker)
        assert result.stains == 4

    def test_apply_tracker_action_no_damage_type(self, service) -> None:
        """Verify apply_tracker_action no longer accepts a damage type."""
        # When/Then: Passing damage_type raises
        with pytest.raises(TypeError):
            service.apply_tracker_action("ct123", "spend", damage_type="SUPERFICIAL")

    @respx.mock
    def test_apply_tracker_action_validation_error(self, service, base_url) -> None:
        """Verify a 400 from the server raises ValidationError."""
        # Given: The endpoint rejects the action
        respx.post(_tracker_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS)).mock(
            return_value=MockResponse(
                400, json={"status": 400, "title": "Bad Request", "detail": "Invalid action"}
            )
        )

        # When/Then: Applying the action raises
        with pytest.raises(ValidationError):
            service.apply_tracker_action("ct123", "add_stain")

    def test_apply_tracker_action_zero_amount(self, service) -> None:
        """Verify amount below 1 fails before any request."""
        # When/Then: amount=0 raises
        with pytest.raises(RequestValidationError):
            service.apply_tracker_action("ct123", "spend", amount=0)
