"""Integration tests for CharactersService."""

from datetime import UTC, date, datetime

import pytest
import respx

from tests.api_client.payloads import endpoint_url, page, sent_json, sent_params, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import (
    HealthStateSet,
    HunterAttributesCreate,
    HunterAttributesUpdate,
    PaginatedResponse,
    VampireAttributesCreate,
    VampireAttributesUpdate,
    WerewolfAttributesCreate,
    WerewolfAttributesUpdate,
)
from vweb.api_client.models.character_trait import CharacterCreateTraitAssign
from vweb.api_client.testing import (
    AssetFactory,
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    NoteFactory,
    TraitFactory,
)

COMPANY_ID = "company123"
CHARACTER_ID = "char123"
ITEM_ID = "item123"
CATEGORY_ID = "cat1"


@pytest.fixture
def characters(vclient):
    """Return a characters service acting on behalf of a user."""
    return vclient.characters("on-behalf-of-user", company_id=COMPANY_ID)


IDS = {
    "company_id": COMPANY_ID,
    "character_id": CHARACTER_ID,
    "item_id": ITEM_ID,
    "category_id": CATEGORY_ID,
}


@pytest.fixture
def full_sheet_category_response_data() -> dict:
    """Return full sheet category response data holding one trait and one available trait."""
    return wire(
        FullSheetTraitCategoryFactory.build(
            id=CATEGORY_ID,
            name="Attributes",
            subcategories=[],
            character_traits=[CharacterTraitFactory.build(value=3)],
            available_traits=[TraitFactory.build(name="Dexterity")],
        )
    )


@pytest.fixture
def full_sheet_response_data(full_sheet_category_response_data: dict) -> dict:
    """Return full sheet response data with one section and category."""
    return wire(
        CharacterFullSheetFactory.build(
            character=CharacterFactory.build(name_first="Marcus"),
            sections=[
                FullSheetTraitSectionFactory.build(
                    name="Physical", categories=[full_sheet_category_response_data]
                )
            ],
        )
    )


@pytest.fixture
def inventory_item_response_data() -> dict:
    """Return sample inventory item response data."""
    return {
        "id": ITEM_ID,
        "character_id": CHARACTER_ID,
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name": "Test Item",
        "type": "BOOK",
        "description": "This is test content",
    }


class TestCharactersServiceGetPage:
    """Tests for CharactersService.get_page method."""

    @respx.mock
    @pytest.mark.parametrize(
        ("kwargs", "expected_params"),
        [
            pytest.param(
                {}, {"limit": "10", "offset": "0", "is_temporary": "false"}, id="defaults"
            ),
            pytest.param(
                {
                    "limit": 25,
                    "offset": 50,
                    "campaign_id": "camp1",
                    "user_player_id": "u1",
                    "user_creator_id": "u2",
                    "character_class": "VAMPIRE",
                    "character_type": "NPC",
                    "status": "ALIVE",
                    "is_temporary": True,
                },
                {
                    "limit": "25",
                    "offset": "50",
                    "campaign_id": "camp1",
                    "user_player_id": "u1",
                    "user_creator_id": "u2",
                    "character_class": "VAMPIRE",
                    "character_type": "NPC",
                    "status": "ALIVE",
                    "is_temporary": "true",
                },
                id="filters",
            ),
        ],
    )
    def test_get_page_sends_filters_and_parses_characters(
        self, characters, base_url, character_response_data, kwargs, expected_params
    ) -> None:
        """Verify get_page sends paging and filter params and parses the characters."""
        # Given: A mocked characters list endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTERS, **IDS)).respond(
            200, json=page(character_response_data)
        )

        # When: Requesting a page of characters
        result = characters.get_page(**kwargs)

        # Then: The params are sent and the characters are parsed
        assert sent_params(route) == expected_params
        assert [c.name_first for c in result.items] == ["John"]
        assert result.total == 1


class TestCharactersServiceCollectionMethods:
    """Tests for the list, iterate, and page methods that wrap paginated routes."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "args", "kwargs", "endpoint", "expected_params", "item"),
        [
            pytest.param(
                "list_all",
                (),
                {"campaign_id": "camp1", "status": "DEAD"},
                Endpoints.CHARACTERS,
                {
                    "limit": "100",
                    "offset": "0",
                    "campaign_id": "camp1",
                    "status": "DEAD",
                    "is_temporary": "false",
                },
                "character",
                id="list_all",
            ),
            pytest.param(
                "iter_all",
                (),
                {"character_class": "WEREWOLF"},
                Endpoints.CHARACTERS,
                {
                    "limit": "100",
                    "offset": "0",
                    "character_class": "WEREWOLF",
                    "is_temporary": "false",
                },
                "character",
                id="iter_all",
            ),
            pytest.param(
                "get_inventory_page",
                (CHARACTER_ID,),
                {},
                Endpoints.CHARACTER_INVENTORY,
                {"limit": "10", "offset": "0"},
                "inventory",
                id="get_inventory_page",
            ),
            pytest.param(
                "list_all_inventory",
                (CHARACTER_ID,),
                {},
                Endpoints.CHARACTER_INVENTORY,
                {"limit": "100", "offset": "0"},
                "inventory",
                id="list_all_inventory",
            ),
            pytest.param(
                "iter_all_inventory",
                (CHARACTER_ID,),
                {},
                Endpoints.CHARACTER_INVENTORY,
                {"limit": "100", "offset": "0"},
                "inventory",
                id="iter_all_inventory",
            ),
        ],
    )
    def test_collection_method_requests_route_and_parses_items(
        self,
        characters,
        base_url,
        character_response_data,
        inventory_item_response_data,
        method,
        args,
        kwargs,
        endpoint,
        expected_params,
        item,
    ) -> None:
        """Verify each collection method requests its route and parses the items."""
        # Given: The route returns one page holding one item
        payload = character_response_data if item == "character" else inventory_item_response_data
        route = respx.get(endpoint_url(base_url, endpoint, **IDS)).respond(200, json=page(payload))

        # When: Calling the collection method
        result = getattr(characters, method)(*args, **kwargs)
        items = result.items if isinstance(result, PaginatedResponse) else list(result)

        # Then: The route gets the expected params and the item is parsed
        assert sent_params(route) == expected_params
        assert [i.id for i in items] == [payload["id"]]


class TestCharactersServiceGet:
    """Tests for CharactersService.get method."""

    @respx.mock
    def test_get_character_without_include(
        self, characters, base_url, character_response_data
    ) -> None:
        """Verify get() sends no include param, parses the character, and leaves embeds unset."""
        # Given: A mocked character endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTER, **IDS)).respond(
            200, json=character_response_data
        )

        # When: Requesting a character
        result = characters.get(CHARACTER_ID)

        # Then: No query is sent and the character and its class attributes are parsed
        assert not sent_params(route)
        assert result.id == CHARACTER_ID
        assert (result.name_first, result.name_last) == ("John", "Doe")
        assert result.character_class == "VAMPIRE"
        assert result.game_version == "V5"
        assert result.vampire_attributes.clan_name == "Ventrue"
        assert result.vampire_attributes.generation == 10
        assert result.vampire_attributes.sire == "Ancient One"
        assert result.traits is None
        assert result.inventory is None
        assert result.notes is None
        assert result.assets is None

    @respx.mock
    def test_get_character_with_include(
        self,
        characters,
        base_url,
        character_response_data,
        character_trait_response_data,
        inventory_item_response_data,
    ) -> None:
        """Verify get() with include sends repeated query params and parses the embeds."""
        # Given: A mocked character endpoint returning embedded resources
        payload = {
            **character_response_data,
            "traits": [character_trait_response_data],
            "inventory": [inventory_item_response_data],
            "notes": [wire(NoteFactory.build())],
            "assets": [wire(AssetFactory.build(character_id=CHARACTER_ID))],
        }
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTER, **IDS)).respond(
            200, json=payload
        )

        # When: Requesting a character with include
        result = characters.get(CHARACTER_ID, include=["traits", "notes"])

        # Then: Each include is a separate query param and the embeds are parsed
        assert route.calls.last.request.url.params.get_list("include") == ["traits", "notes"]
        assert [t.id for t in result.traits] == [character_trait_response_data["id"]]
        assert len(result.notes) == 1


CREATE_KWARGS = {
    "campaign_id": "campaign123",
    "character_class": "VAMPIRE",
    "game_version": "V5",
    "name_first": "John",
    "name_last": "Doe",
}


class TestCharactersServiceCreate:
    """Tests for CharactersService.create method."""

    @respx.mock
    @pytest.mark.parametrize(
        ("extra_kwargs", "expected_extra_body"),
        [
            pytest.param({}, {}, id="minimal"),
            pytest.param(
                {
                    "type": "NPC",
                    "name_nick": "Johnny",
                    "age": 35,
                    "date_of_birth": date(1888, 6, 15),
                    "biography": "A mysterious vampire.",
                    "demeanor": "Friendly",
                    "nature": "Warrior",
                    "concept_id": "concept123",
                    "user_player_id": "user456",
                },
                {
                    "type": "NPC",
                    "name_nick": "Johnny",
                    "age": 35,
                    "date_of_birth": "1888-06-15",
                    "biography": "A mysterious vampire.",
                    "demeanor": "Friendly",
                    "nature": "Warrior",
                    "concept_id": "concept123",
                    "user_player_id": "user456",
                },
                id="profile-fields",
            ),
            pytest.param(
                {
                    "vampire_attributes": VampireAttributesCreate(
                        clan_id="clan123",
                        generation=10,
                        sire="Ancient One",
                        bane_name="Rarefied Tastes",
                        bane_description="Feeds only on specific blood",
                    )
                },
                {
                    "vampire_attributes": {
                        "clan_id": "clan123",
                        "generation": 10,
                        "sire": "Ancient One",
                        "bane_name": "Rarefied Tastes",
                        "bane_description": "Feeds only on specific blood",
                    }
                },
                id="vampire",
            ),
            pytest.param(
                {
                    "character_class": "WEREWOLF",
                    "werewolf_attributes": WerewolfAttributesCreate(
                        tribe_id="tribe123", auspice_id="auspice123", pack_name="Moon Runners"
                    ),
                },
                {
                    "character_class": "WEREWOLF",
                    "werewolf_attributes": {
                        "tribe_id": "tribe123",
                        "auspice_id": "auspice123",
                        "pack_name": "Moon Runners",
                    },
                },
                id="werewolf",
            ),
            pytest.param(
                {
                    "character_class": "HUNTER",
                    "hunter_attributes": HunterAttributesCreate(creed="Avenger"),
                },
                {"character_class": "HUNTER", "hunter_attributes": {"creed": "Avenger"}},
                id="hunter",
            ),
            pytest.param(
                {
                    "traits": [
                        CharacterCreateTraitAssign(trait_id="trait123", value=3),
                        CharacterCreateTraitAssign(trait_id="trait456", value=2),
                    ]
                },
                {
                    "traits": [
                        {"trait_id": "trait123", "value": 3},
                        {"trait_id": "trait456", "value": 2},
                    ]
                },
                id="traits",
            ),
        ],
    )
    def test_create_character_sends_given_fields(
        self,
        characters,
        base_url,
        character_response_data,
        extra_kwargs,
        expected_extra_body,
    ) -> None:
        """Verify create sends exactly the fields given and parses the created character."""
        # Given: A mocked create endpoint
        route = respx.post(endpoint_url(base_url, Endpoints.CHARACTERS, **IDS)).respond(
            201, json=character_response_data
        )

        # When: Creating a character
        result = characters.create(**{**CREATE_KWARGS, **extra_kwargs})

        # Then: Exactly the given fields are sent and the character is returned
        assert sent_json(route) == {**CREATE_KWARGS, **expected_extra_body}
        assert result.id == CHARACTER_ID


class TestCharactersServiceUpdate:
    """Tests for CharactersService.update method."""

    @respx.mock
    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            pytest.param({"name_first": "Jane"}, {"name_first": "Jane"}, id="name"),
            pytest.param({"status": "DEAD"}, {"status": "DEAD"}, id="status"),
            pytest.param(
                {"date_of_birth": date(1888, 6, 15)}, {"date_of_birth": "1888-06-15"}, id="dob"
            ),
            pytest.param({"date_of_birth": None}, {"date_of_birth": None}, id="clear-dob"),
            pytest.param(
                {"name_first": "Renamed", "name_nick": None, "age": None, "concept_id": None},
                {"name_first": "Renamed", "name_nick": None, "age": None, "concept_id": None},
                id="clear-profile-fields",
            ),
            pytest.param(
                {"vampire_attributes": {"clan_id": "clan1", "sire": None}, "user_player_id": None},
                {"user_player_id": None, "vampire_attributes": {"clan_id": "clan1", "sire": None}},
                id="clear-nested-attribute",
            ),
            pytest.param(
                {
                    "vampire_attributes": VampireAttributesUpdate(
                        clan_id="clan456",
                        generation=9,
                        sire="New Sire",
                        compulsion_name="Obsession",
                        compulsion_description="Cannot resist beauty",
                    )
                },
                {
                    "vampire_attributes": {
                        "clan_id": "clan456",
                        "generation": 9,
                        "sire": "New Sire",
                        "compulsion_name": "Obsession",
                        "compulsion_description": "Cannot resist beauty",
                    }
                },
                id="vampire",
            ),
            pytest.param(
                {
                    "werewolf_attributes": WerewolfAttributesUpdate(
                        tribe_id="tribe456", auspice_id="auspice456", pack_name="Star Gazers"
                    )
                },
                {
                    "werewolf_attributes": {
                        "tribe_id": "tribe456",
                        "auspice_id": "auspice456",
                        "pack_name": "Star Gazers",
                    }
                },
                id="werewolf",
            ),
            pytest.param(
                {"hunter_attributes": HunterAttributesUpdate(creed="Defender")},
                {"hunter_attributes": {"creed": "Defender"}},
                id="hunter",
            ),
        ],
    )
    def test_update_character_sends_only_given_fields(
        self, characters, base_url, character_response_data, kwargs, expected_body
    ) -> None:
        """Verify update sends only the fields passed, with explicit nulls for cleared ones."""
        # Given: A mocked update endpoint
        route = respx.patch(endpoint_url(base_url, Endpoints.CHARACTER, **IDS)).respond(
            200, json={**character_response_data, "name_first": "Jane"}
        )

        # When: Updating the character
        result = characters.update(CHARACTER_ID, **kwargs)

        # Then: Only the given fields are sent and the updated character is returned
        assert sent_json(route) == expected_body
        assert result.name_first == "Jane"


class TestCharactersServiceDelete:
    """Tests for CharactersService.delete method."""

    @respx.mock
    def test_delete_character(self, characters, base_url) -> None:
        """Verify deleting a character calls its route and returns None."""
        # Given: A mocked delete endpoint
        route = respx.delete(endpoint_url(base_url, Endpoints.CHARACTER, **IDS)).respond(204)

        # When: Deleting the character
        result = characters.delete(CHARACTER_ID)

        # Then: The route was called and None is returned
        assert route.call_count == 1
        assert result is None


class TestCharactersServiceGetStatistics:
    """Tests for CharactersService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, characters, base_url, statistics_response_data):
        """Verify get_statistics sends the default top-trait count and parses the stats."""
        # Given: A mocked statistics endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTER_STATISTICS, **IDS)).respond(
            200, json=statistics_response_data
        )

        # When: Getting statistics
        result = characters.get_statistics(CHARACTER_ID)

        # Then: The default param is sent and the stats are parsed
        assert sent_params(route) == {"num_top_traits": "5"}
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0


INCLUDE_AVAILABLE_TRAITS_CASES = [
    pytest.param({}, {}, id="default"),
    pytest.param(
        {"include_available_traits": True},
        {"include_available_traits": "true"},
        id="include-available-traits",
    ),
]


class TestCharactersServiceGetFullSheet:
    """Tests for CharactersService full sheet methods."""

    @respx.mock
    @pytest.mark.parametrize(("kwargs", "expected_params"), INCLUDE_AVAILABLE_TRAITS_CASES)
    def test_get_full_sheet(
        self, characters, base_url, full_sheet_response_data, kwargs, expected_params
    ):
        """Verify get_full_sheet sends the include flag only when asked and parses the sheet."""
        # Given: A mocked full sheet endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.CHARACTER_FULL_SHEET, **IDS)).respond(
            200, json=full_sheet_response_data
        )

        # When: Getting the full sheet
        result = characters.get_full_sheet(CHARACTER_ID, **kwargs)

        # Then: The params are sent and the section hierarchy is parsed
        assert sent_params(route) == expected_params
        assert result.character.name_first == "Marcus"
        category = result.sections[0].categories[0]
        assert result.sections[0].name == "Physical"
        assert category.character_traits[0].value == 3
        assert [t.name for t in category.available_traits] == ["Dexterity"]

    @respx.mock
    @pytest.mark.parametrize(("kwargs", "expected_params"), INCLUDE_AVAILABLE_TRAITS_CASES)
    def test_get_full_sheet_category(
        self, characters, base_url, full_sheet_category_response_data, kwargs, expected_params
    ):
        """Verify get_full_sheet_category sends the include flag only when asked."""
        # Given: A mocked category endpoint
        route = respx.get(
            endpoint_url(base_url, Endpoints.CHARACTER_FULL_SHEET_CATEGORY, **IDS)
        ).respond(200, json=full_sheet_category_response_data)

        # When: Getting a single category
        result = characters.get_full_sheet_category(CHARACTER_ID, CATEGORY_ID, **kwargs)

        # Then: The params are sent and the category is parsed
        assert sent_params(route) == expected_params
        assert result.id == CATEGORY_ID
        assert result.character_traits[0].value == 3
        assert [t.name for t in result.available_traits] == ["Dexterity"]


class TestCharactersServiceInventory:
    """Tests for CharactersService inventory methods."""

    @respx.mock
    def test_get_inventory_item(self, characters, base_url, inventory_item_response_data):
        """Verify getting an inventory item parses every field."""
        # Given: A mocked inventory item endpoint
        respx.get(endpoint_url(base_url, Endpoints.CHARACTER_INVENTORY_ITEM, **IDS)).respond(
            200, json=inventory_item_response_data
        )

        # When: Getting the inventory item
        result = characters.get_inventory_item(CHARACTER_ID, ITEM_ID)

        # Then: The item is parsed
        assert result.id == ITEM_ID
        assert result.name == "Test Item"
        assert result.type == "BOOK"
        assert result.description == "This is test content"
        assert result.character_id == CHARACTER_ID
        assert result.date_created == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    @respx.mock
    def test_create_inventory_item(self, characters, base_url, inventory_item_response_data):
        """Verify creating an inventory item sends its fields and returns it."""
        # Given: A mocked create endpoint
        route = respx.post(endpoint_url(base_url, Endpoints.CHARACTER_INVENTORY, **IDS)).respond(
            201, json=inventory_item_response_data
        )

        # When: Creating the inventory item
        result = characters.create_inventory_item(
            CHARACTER_ID, name="Test Item", type="BOOK", description="This is test content"
        )

        # Then: The fields are sent and the item is returned
        assert sent_json(route) == {
            "name": "Test Item",
            "type": "BOOK",
            "description": "This is test content",
        }
        assert result.id == ITEM_ID

    @respx.mock
    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            pytest.param({"name": "Updated Item"}, {"name": "Updated Item"}, id="name"),
            pytest.param({"description": None}, {"description": None}, id="clear-description"),
        ],
    )
    def test_update_inventory_item_sends_only_given_fields(
        self, characters, base_url, inventory_item_response_data, kwargs, expected_body
    ):
        """Verify updating an inventory item sends only the given fields, keeping nulls."""
        # Given: A mocked update endpoint
        route = respx.patch(
            endpoint_url(base_url, Endpoints.CHARACTER_INVENTORY_ITEM, **IDS)
        ).respond(200, json={**inventory_item_response_data, "name": "Updated Item"})

        # When: Updating the inventory item
        result = characters.update_inventory_item(CHARACTER_ID, ITEM_ID, **kwargs)

        # Then: Only the given fields are sent and the updated item is returned
        assert sent_json(route) == expected_body
        assert result.name == "Updated Item"

    @respx.mock
    def test_delete_inventory_item(self, characters, base_url):
        """Verify deleting an inventory item calls its route."""
        # Given: A mocked delete endpoint
        route = respx.delete(
            endpoint_url(base_url, Endpoints.CHARACTER_INVENTORY_ITEM, **IDS)
        ).respond(204)

        # When: Deleting the inventory item
        characters.delete_inventory_item(CHARACTER_ID, ITEM_ID)

        # Then: The route was called
        assert route.call_count == 1


V5_HEALTH = {"type": "DAMAGE", "size": 5, "damage": 2, "extra_levels": 0}
V4_HEALTH = {
    "type": "DAMAGE",
    "size": 7,
    "damage": 1,
    "extra_levels": 0,
    "levels": [{"name": "Bruised", "marked": True}, {"name": "Hurt", "marked": False}],
}


class TestCharactersServiceHealth:
    """Tests for CharactersService health methods."""

    @respx.mock
    def test_get_health(self, characters, base_url) -> None:
        """Verify get_health returns V5 health with no levels."""
        # Given: A mocked health endpoint
        respx.get(endpoint_url(base_url, Endpoints.CHARACTER_HEALTH, **IDS)).respond(
            200, json=V5_HEALTH
        )

        # When: Getting health
        result = characters.get_health(CHARACTER_ID)

        # Then: The health is parsed without levels
        assert result.damage == 2
        assert result.levels is None

    @respx.mock
    def test_set_health_sends_all_fields(self, characters, base_url) -> None:
        """Verify set_health sends every field so omitted ones reset to zero."""
        # Given: A mocked set health endpoint
        route = respx.put(endpoint_url(base_url, Endpoints.CHARACTER_HEALTH, **IDS)).respond(
            200, json=V5_HEALTH
        )

        # When: Setting only damage
        characters.set_health(CHARACTER_ID, damage=2)

        # Then: All fields are sent
        assert sent_json(route) == {"extra_levels": 0, "damage": 2}

    @respx.mock
    def test_set_health_request_model(self, characters, base_url) -> None:
        """Verify set_health accepts a HealthStateSet and parses V4 levels."""
        # Given: A mocked set health endpoint returning V4 health
        route = respx.put(endpoint_url(base_url, Endpoints.CHARACTER_HEALTH, **IDS)).respond(
            200, json=V4_HEALTH
        )

        # When: Setting damage with a request model
        result = characters.set_health(CHARACTER_ID, HealthStateSet(damage=1, extra_levels=1))

        # Then: The state is sent and V4 levels are parsed
        assert sent_json(route) == {"extra_levels": 1, "damage": 1}
        assert result.levels[0].marked is True

    @respx.mock
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"damage": -1}, id="negative"),
            pytest.param({"superficial": 2}, id="removed-typed-mark"),
        ],
    )
    def test_set_health_invalid_input_rejected(self, characters, kwargs) -> None:
        """Verify invalid health input fails before any request instead of resetting health."""
        # When/Then: Setting invalid health raises
        with pytest.raises(RequestValidationError):
            characters.set_health(CHARACTER_ID, **kwargs)

        assert not respx.calls

    @respx.mock
    def test_apply_health_action_damage(self, characters, base_url) -> None:
        """Verify a damage action sends only action and amount."""
        # Given: A mocked health action endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.CHARACTER_HEALTH_ACTIONS, **IDS)
        ).respond(200, json=V5_HEALTH)

        # When: Applying two damage
        result = characters.apply_health_action(CHARACTER_ID, "damage", amount=2)

        # Then: Only action and amount are sent and the new health is returned
        assert sent_json(route) == {"action": "damage", "amount": 2}
        assert result.damage == 2
