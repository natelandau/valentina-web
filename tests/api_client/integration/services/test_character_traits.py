"""Integration tests for CharacterTraitsService."""

import pytest
import respx
from respx import MockResponse

from tests.api_client.payloads import endpoint_url, page, sent_json, sent_params
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import (
    CharacterTraitAdd,
    CharacterTraitValueOptionsResponse,
    CounterTracker,
    StainsTracker,
    TrackerStateSet,
    TraitCreate,
)

IDS = {"company_id": "company123", "character_id": "char123"}
TRAIT_IDS = {**IDS, "character_trait_id": "ct123"}


@pytest.fixture
def service(vclient):
    """Return a character traits service for the standard test ids."""
    return vclient.character_traits("char123", "on-behalf-of-user", company_id="company123")


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
        },
    }


class TestCharacterTraitsServiceList:
    """Tests for the CharacterTraitsService list methods."""

    @respx.mock
    def test_get_page(self, service, base_url, character_trait_response_data) -> None:
        """Verify get_page parses the paginated character traits."""
        # Given: A character traits list endpoint
        respx.get(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAITS, **TRAIT_IDS),
            params={"limit": "10", "offset": "0"},
        ).mock(return_value=MockResponse(200, json=page(character_trait_response_data)))

        # When: Requesting a page of character traits
        result = service.get_page()

        # Then: The items parse with their trait data
        assert result.total == 1
        assert result.items[0].trait.name == "Strength"
        assert result.items[0].value == 3

    @pytest.mark.parametrize(
        ("call", "expected_query"),
        [
            (lambda s: s.get_page(limit=20, offset=10), {"limit": "20", "offset": "10"}),
            (lambda s: s.get_page(category_id="cat123"), {"category_id": "cat123"}),
            (lambda s: s.get_page(is_rollable=True), {"is_rollable": "true"}),
            (lambda s: s.get_page(is_rollable=False), {"is_rollable": "false"}),
            (lambda s: s.list_all(category_id="cat123"), {"category_id": "cat123"}),
            (lambda s: s.list_all(is_rollable=True), {"is_rollable": "true"}),
            (lambda s: list(s.iter_all(category_id="cat456")), {"category_id": "cat456"}),
            (lambda s: list(s.iter_all(is_rollable=False)), {"is_rollable": "false"}),
        ],
        ids=[
            "get_page-pagination",
            "get_page-category",
            "get_page-rollable",
            "get_page-not-rollable",
            "list_all-category",
            "list_all-rollable",
            "iter_all-category",
            "iter_all-not-rollable",
        ],
    )
    @respx.mock
    def test_list_methods_send_filters(
        self, service, base_url, character_trait_response_data, call, expected_query
    ) -> None:
        """Verify every list method forwards its filters as query params."""
        # Given: A list endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTER_TRAITS, **TRAIT_IDS)).mock(
            return_value=MockResponse(200, json=page(character_trait_response_data))
        )

        # When: Calling the list method with filters
        call(service)

        # Then: The filters reach the query string
        query = sent_params(route)
        assert query.items() >= expected_query.items()


class TestCharacterTraitsServiceCrud:
    """Tests for CharacterTraitsService single-trait methods."""

    @respx.mock
    def test_get_character_trait(self, service, base_url, character_trait_response_data) -> None:
        """Verify get requests the trait by ID and parses it."""
        # Given: A character trait endpoint
        respx.get(endpoint_url(base_url, Endpoints.CHARACTER_TRAIT, **TRAIT_IDS)).mock(
            return_value=MockResponse(200, json=character_trait_response_data)
        )

        # When: Requesting a character trait
        result = service.get("ct123")

        # Then: The character trait parses
        assert result.id == "ct123"
        assert result.character_id == "char123"
        assert result.trait.name == "Strength"

    @pytest.mark.parametrize("value", [3, 0])
    @respx.mock
    def test_assign_trait(self, service, base_url, character_trait_response_data, value) -> None:
        """Verify assign sends the trait, value (zero included), and currency."""
        # Given: An assign endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_ASSIGN, **TRAIT_IDS)
        ).mock(
            return_value=MockResponse(201, json={**character_trait_response_data, "value": value})
        )

        # When: Assigning a trait
        result = service.assign(trait_id="trait123", value=value, currency="XP")

        # Then: The body carries every field and the trait parses
        assert sent_json(route) == {
            "trait_id": "trait123",
            "value": value,
            "currency": "XP",
        }
        assert result.value == value

    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            pytest.param(
                {"name": "Custom Skill", "category_id": "cat123", "currency": "XP"},
                {"name": "Custom Skill", "category_id": "cat123", "currency": "XP"},
                id="minimal-leaves-defaults-to-server",
            ),
            pytest.param(
                {"name": "Custom Trait", "category_id": "cat123", "currency": "NO_COST"},
                {"name": "Custom Trait", "category_id": "cat123", "currency": "NO_COST"},
                id="no-cost",
            ),
            pytest.param(
                {
                    "name": "Custom Background",
                    "category_id": "backgrounds_cat",
                    "currency": "STARTING_POINTS",
                    "description": "A custom background trait",
                    "max_value": 10,
                    "min_value": 1,
                    "show_when_zero": False,
                    "is_rollable": False,
                    "initial_cost": 3,
                    "upgrade_cost": 2,
                },
                {
                    "name": "Custom Background",
                    "category_id": "backgrounds_cat",
                    "currency": "STARTING_POINTS",
                    "description": "A custom background trait",
                    "max_value": 10,
                    "min_value": 1,
                    "show_when_zero": False,
                    "is_rollable": False,
                    "initial_cost": 3,
                    "upgrade_cost": 2,
                },
                id="all-options",
            ),
            pytest.param(
                {"request": TraitCreate(name="Custom Skill", category_id="cat123", currency="XP")},
                {"name": "Custom Skill", "category_id": "cat123", "currency": "XP"},
                id="request-model",
            ),
        ],
    )
    @respx.mock
    def test_create_trait(
        self, service, base_url, character_trait_response_data, kwargs, expected_body
    ) -> None:
        """Verify create sends only the fields set, so the server applies its defaults."""
        # Given: A create endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_CREATE, **TRAIT_IDS)
        ).mock(return_value=MockResponse(201, json=character_trait_response_data))

        # When: Creating a custom trait
        result = service.create(**kwargs)

        # Then: The body holds exactly the fields set
        assert sent_json(route) == expected_body
        assert result.id == "ct123"

    @pytest.mark.parametrize(
        ("kwargs", "expected_query"),
        [({}, {}), ({"currency": "XP"}, {"currency": "XP"})],
    )
    @respx.mock
    def test_delete_trait(self, service, base_url, kwargs, expected_query) -> None:
        """Verify delete sends the recoup currency only when given."""
        # Given: A delete endpoint
        route = respx.delete(endpoint_url(base_url, Endpoints.CHARACTER_TRAIT, **TRAIT_IDS)).mock(
            return_value=MockResponse(204)
        )

        # When: Deleting the trait
        result = service.delete("ct123", **kwargs)

        # Then: The query carries only the given currency
        assert sent_params(route) == expected_query
        assert result is None

    @respx.mock
    def test_get_value_options(
        self, service, base_url, character_trait_value_options_response_data
    ) -> None:
        """Verify get_value_options parses the options keyed by target value."""
        # Given: A value options endpoint
        respx.get(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_VALUE_OPTIONS, **TRAIT_IDS)
        ).mock(return_value=MockResponse(200, json=character_trait_value_options_response_data))

        # When: Getting the value options for a character trait
        result = service.get_value_options("ct123")

        # Then: The response parses in full
        assert result == CharacterTraitValueOptionsResponse.model_validate(
            character_trait_value_options_response_data
        )

    @respx.mock
    def test_change_value(self, service, base_url, character_trait_response_data) -> None:
        """Verify change_value sends the target value and currency."""
        # Given: A change value endpoint
        route = respx.put(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_VALUE, **TRAIT_IDS)
        ).mock(return_value=MockResponse(200, json=character_trait_response_data))

        # When: Changing the value of a character trait
        result = service.change_value("ct123", new_value=4, currency="XP")

        # Then: The body names the target value and the trait parses
        assert sent_json(route) == {
            "target_value": 4,
            "currency": "XP",
        }
        assert result.specialties[0].name == "Knives"


class TestCharacterTraitsServiceSpecialties:
    """Tests for CharacterTraitsService specialty methods."""

    @pytest.mark.parametrize(
        ("kwargs", "expected_currency"),
        [({"currency": "XP"}, "XP"), ({}, "NO_COST")],
    )
    @respx.mock
    def test_add_specialty(
        self, service, base_url, character_trait_response_data, kwargs, expected_currency
    ) -> None:
        """Verify add_specialty posts the name and currency, defaulting to NO_COST."""
        # Given: An add specialty endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_SPECIALTIES, **TRAIT_IDS)
        ).mock(return_value=MockResponse(201, json=character_trait_response_data))

        # When: Adding a specialty
        result = service.add_specialty("ct123", name="Knives", **kwargs)

        # Then: The body carries the name and currency
        assert sent_json(route) == {
            "name": "Knives",
            "currency": expected_currency,
        }
        assert result.specialties[0].id == "spec123"

    @respx.mock
    def test_update_specialty(self, service, base_url, character_trait_response_data) -> None:
        """Verify renaming a specialty patches only the new name."""
        # Given: An update specialty endpoint
        route = respx.patch(
            endpoint_url(
                base_url, Endpoints.CHARACTER_TRAIT_SPECIALTY, **TRAIT_IDS, specialty_id="spec123"
            )
        ).mock(return_value=MockResponse(200, json=character_trait_response_data))

        # When: Renaming the specialty
        result = service.update_specialty("ct123", "spec123", name="Knives")

        # Then: The body carries only the name
        assert sent_json(route) == {"name": "Knives"}
        assert result.id == "ct123"

    @respx.mock
    def test_delete_specialty(self, service, base_url) -> None:
        """Verify deleting a specialty calls its delete endpoint."""
        # Given: A delete specialty endpoint
        route = respx.delete(
            endpoint_url(
                base_url, Endpoints.CHARACTER_TRAIT_SPECIALTY, **TRAIT_IDS, specialty_id="spec123"
            )
        ).mock(return_value=MockResponse(204))

        # When: Deleting the specialty
        result = service.delete_specialty("ct123", "spec123")

        # Then: The route was called and nothing is returned
        assert route.called
        assert result is None


class TestCharacterTraitsServiceBulkAssign:
    """Tests for CharacterTraitsService.bulk_assign method."""

    @respx.mock
    def test_bulk_assign(self, service, base_url, character_trait_response_data) -> None:
        """Verify bulk_assign sends a JSON list and parses succeeded and failed items."""
        # Given: A bulk-assign endpoint reporting one success and one failure
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_BULK_ASSIGN, **TRAIT_IDS)
        ).mock(
            return_value=MockResponse(
                200,
                json={
                    "succeeded": [
                        {"trait_id": "trait1", "character_trait": character_trait_response_data}
                    ],
                    "failed": [{"trait_id": "trait2", "error": "Not enough XP to add trait"}],
                },
            )
        )

        # When: Bulk assigning traits
        result = service.bulk_assign(
            [
                CharacterTraitAdd(trait_id="trait1", value=2, currency="NO_COST"),
                CharacterTraitAdd(trait_id="trait2", value=1, currency="XP"),
            ]
        )

        # Then: The body is a list of items and both outcomes parse
        assert sent_json(route) == [
            {"trait_id": "trait1", "value": 2, "currency": "NO_COST"},
            {"trait_id": "trait2", "value": 1, "currency": "XP"},
        ]
        assert result.succeeded[0].character_trait.id == "ct123"
        assert result.failed[0].trait_id == "trait2"
        assert result.failed[0].error == "Not enough XP to add trait"


COUNTER_TRACKER = {"type": "COUNTER", "size": 5, "current": 3}
STAINS_TRACKER = {"type": "STAINS", "humanity": 7, "stain_capacity": 3, "stains": 4}


class TestCharacterTraitsServiceTracker:
    """Tests for CharacterTraitsService tracker methods."""

    @respx.mock
    def test_get_tracker(self, service, base_url) -> None:
        """Verify get_tracker returns the typed tracker variant."""
        # Given: A tracker endpoint returning a counter
        respx.get(endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER, **TRAIT_IDS)).mock(
            return_value=MockResponse(200, json=COUNTER_TRACKER)
        )

        # When: Getting the tracker
        result = service.get_tracker("ct123")

        # Then: A CounterTracker is returned
        assert isinstance(result, CounterTracker)
        assert result.current == 3

    @pytest.mark.parametrize(
        ("args", "kwargs", "response", "expected_body", "expected_type"),
        [
            pytest.param((), {"current": 0}, COUNTER_TRACKER, {"current": 0}, CounterTracker),
            pytest.param(
                (TrackerStateSet(stains=2),), {}, STAINS_TRACKER, {"stains": 2}, StainsTracker
            ),
        ],
        ids=["kwargs-keeps-zero", "request-model"],
    )
    @respx.mock
    def test_set_tracker(
        self, service, base_url, args, kwargs, response, expected_body, expected_type
    ) -> None:
        """Verify set_tracker sends only the fields set and returns the typed tracker."""
        # Given: A set tracker endpoint
        route = respx.put(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER, **TRAIT_IDS)
        ).mock(return_value=MockResponse(200, json=response))

        # When: Setting the tracker
        result = service.set_tracker("ct123", *args, **kwargs)

        # Then: Only the set field is sent and the response is typed
        assert sent_json(route) == expected_body
        assert isinstance(result, expected_type)

    @respx.mock
    def test_apply_tracker_action(self, service, base_url) -> None:
        """Verify an action sends only action and amount."""
        # Given: An action endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS, **TRAIT_IDS)
        ).mock(return_value=MockResponse(200, json=COUNTER_TRACKER))

        # When: Spending two points
        result = service.apply_tracker_action("ct123", "spend", amount=2)

        # Then: Only action and amount are sent
        assert sent_json(route) == {"action": "spend", "amount": 2}
        assert isinstance(result, CounterTracker)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda s: s.add_specialty("ct123", name="ab"), id="specialty-name-too-short"),
        pytest.param(lambda s: s.set_tracker("ct123", current=-1), id="negative-tracker-value"),
        pytest.param(
            lambda s: s.apply_tracker_action("ct123", "spend", amount=0), id="zero-action-amount"
        ),
    ],
)
@respx.mock
def test_invalid_input_fails_before_any_request(service, call) -> None:
    """Verify input the API would reject fails client-side without a request."""
    # When/Then: The call raises before reaching the network
    with pytest.raises(RequestValidationError):
        call(service)

    assert not respx.calls
