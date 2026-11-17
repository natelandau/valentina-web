"""Integration tests for CharactersService."""

import json
from datetime import UTC, date, datetime

import pytest
import respx
from respx import MockResponse

from tests.api_client.payloads import page, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError, RequestValidationError, ValidationError
from vweb.api_client.models import (
    Character,
    CharacterDetail,
    CharacterFullSheet,
    FullSheetTraitCategory,
    Health,
    HealthStateSet,
    HunterAttributes,
    HunterAttributesCreate,
    HunterAttributesUpdate,
    InventoryItem,
    PaginatedResponse,
    RollStatistics,
    VampireAttributesCreate,
    VampireAttributesUpdate,
    WerewolfAttributes,
    WerewolfAttributesCreate,
    WerewolfAttributesUpdate,
)
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


@pytest.fixture
def paginated_character_response(character_response_data: dict) -> dict:
    """Return a one-item paginated characters response."""
    return page(character_response_data)


@pytest.fixture
def full_sheet_response_data(full_sheet_category_response_data: dict) -> dict:
    """Return full sheet response data with one section and category."""
    return _full_sheet(full_sheet_category_response_data)


@pytest.fixture
def full_sheet_category_response_data() -> dict:
    """Return full sheet category response data holding one trait at value 3."""
    return wire(
        FullSheetTraitCategoryFactory.build(
            id="cat1",
            name="Attributes",
            subcategories=[],
            character_traits=[CharacterTraitFactory.build(value=3)],
            available_traits=[],
        )
    )


@pytest.fixture
def full_sheet_category_response_data_with_available_traits(
    full_sheet_category_response_data: dict,
) -> dict:
    """Return full sheet category response data offering one available trait."""
    return {
        **full_sheet_category_response_data,
        "character_traits": [],
        "available_traits": [wire(TraitFactory.build(name="Dexterity"))],
    }


@pytest.fixture
def full_sheet_response_data_with_available_traits(
    full_sheet_category_response_data_with_available_traits: dict,
) -> dict:
    """Return full sheet response data whose category offers available traits."""
    return _full_sheet(full_sheet_category_response_data_with_available_traits)


def _full_sheet(category: dict) -> dict:
    return wire(
        CharacterFullSheetFactory.build(
            character=CharacterFactory.build(name_first="Marcus"),
            sections=[FullSheetTraitSectionFactory.build(name="Physical", categories=[category])],
        )
    )


@pytest.fixture
def inventory_item_response_data() -> dict:
    """Return sample inventory item response data."""
    return {
        "id": "item123",
        "character_id": "char123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name": "Test Item",
        "type": "BOOK",
        "description": "This is test content",
    }


@pytest.fixture
def werewolf_character_response_data() -> dict:
    """Return werewolf character response data."""
    return wire(
        CharacterFactory.build(
            id="char456",
            character_class="WEREWOLF",
            werewolf_attributes=WerewolfAttributes(
                tribe_name="Shadow Lords", auspice_name="Ahroun"
            ),
        )
    )


@pytest.fixture
def hunter_character_response_data() -> dict:
    """Return hunter character response data."""
    return wire(
        CharacterFactory.build(
            id="char789",
            character_class="HUNTER",
            hunter_attributes=HunterAttributes(creed="Avenger"),
        )
    )


class TestCharactersServiceGetPage:
    """Tests for CharactersService.get_page method."""

    @respx.mock
    def test_get_page(self, vclient, base_url, paginated_character_response) -> None:
        """Verify getting a page of characters returns paginated response."""
        # Given: A mocked characters list endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=paginated_character_response))

        # When: Requesting a page of characters
        result = vclient.characters("on-behalf-of-user", company_id="company123").get_page()

        # Then: The route was called and response is paginated
        assert route.called
        assert len(result.items) == 1
        assert isinstance(result.items[0], Character)
        assert result.items[0].name_first == "John"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_filters(self, vclient, base_url, paginated_character_response) -> None:
        """Verify get_page passes filter parameters correctly."""
        # Given: A mocked endpoint expecting filter params
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}",
            params={
                "limit": "10",
                "offset": "0",
                "character_class": "VAMPIRE",
                "status": "ALIVE",
                "is_temporary": "true",
            },
        ).mock(return_value=MockResponse(200, json=paginated_character_response))

        # When: Requesting with filters
        result = vclient.characters("on-behalf-of-user", company_id="company123").get_page(
            character_class="VAMPIRE", status="ALIVE", is_temporary=True
        )

        # Then: The route was called with correct params
        assert route.called
        assert len(result.items) == 1


class TestCharactersServiceGet:
    """Tests for CharactersService.get method."""

    @respx.mock
    def test_get_character(self, vclient, base_url, character_response_data) -> None:
        """Verify getting a character returns Character object."""
        # Given: A mocked character endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Requesting a character
        result = vclient.characters("on-behalf-of-user", company_id="company123").get("char123")

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, CharacterDetail)
        assert isinstance(result, Character)
        assert result.id == "char123"
        assert result.name_first == "John"
        assert result.name_last == "Doe"
        assert result.character_class == "VAMPIRE"
        assert result.game_version == "V5"

    @respx.mock
    def test_get_character_not_found(self, vclient, base_url) -> None:
        """Verify getting a non-existent character raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='nonexistent')}"
        ).mock(
            return_value=MockResponse(
                404, json={"detail": "Character not found", "status_code": 404}
            )
        )

        # When/Then: Requesting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.characters("on-behalf-of-user", company_id="company123").get("nonexistent")

        assert route.called


@pytest.fixture
def character_detail_response_data(
    character_response_data: dict,
    character_trait_response_data: dict,
    inventory_item_response_data: dict,
) -> dict:
    """Return sample character detail response with embedded resources."""
    return {
        **character_response_data,
        "traits": [character_trait_response_data],
        "inventory": [inventory_item_response_data],
        "notes": [wire(NoteFactory.build())],
        "assets": [wire(AssetFactory.build(character_id="char123"))],
    }


class TestCharactersServiceGetWithInclude:
    """Tests for CharactersService.get method with include parameter."""

    @respx.mock
    def test_get_character_with_include(
        self, vclient, base_url, character_detail_response_data
    ) -> None:
        """Verify getting a character with include returns CharacterDetail with embedded resources."""
        # Given: A mocked character endpoint expecting include params
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}",
            params=[("include", "traits"), ("include", "notes")],
        ).mock(return_value=MockResponse(200, json=character_detail_response_data))

        # When: Requesting a character with include
        result = vclient.characters("on-behalf-of-user", company_id="company123").get(
            "char123", include=["traits", "notes"]
        )

        # Then: The route was called with include params and detail is returned
        assert route.called
        assert isinstance(result, CharacterDetail)
        assert isinstance(result, Character)
        assert result.id == "char123"
        assert result.traits is not None
        assert len(result.traits) == 1
        assert result.notes is not None
        assert len(result.notes) == 1

    @respx.mock
    def test_get_character_without_include_returns_detail(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify getting a character without include still returns CharacterDetail."""
        # Given: A mocked character endpoint with no include params
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Requesting a character without include
        result = vclient.characters("on-behalf-of-user", company_id="company123").get("char123")

        # Then: Returns CharacterDetail with None embedded fields
        assert route.called
        assert isinstance(result, CharacterDetail)
        assert result.traits is None
        assert result.inventory is None
        assert result.notes is None
        assert result.assets is None


class TestCharactersServiceCreate:
    """Tests for CharactersService.create method."""

    @respx.mock
    def test_create_character_minimal(self, vclient, base_url, character_response_data) -> None:
        """Verify creating a character with minimal fields."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=character_response_data))

        # When: Creating a character with required fields only
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.name_first == "John"

        # Verify request body
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["character_class"] == "VAMPIRE"
        assert body["game_version"] == "V5"
        assert body["name_first"] == "John"
        assert body["name_last"] == "Doe"

    @respx.mock
    def test_create_character_with_all_options(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify creating a character with all optional fields."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=character_response_data))

        # When: Creating a character with all fields
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            type="NPC",
            name_nick="Johnny",
            age=35,
            date_of_birth=date(1888, 6, 15),
            biography="A mysterious vampire.",
            demeanor="Friendly",
            nature="Warrior",
            concept_id="concept123",
            user_player_id="user456",
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)

        # Verify request body includes optional fields
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["type"] == "NPC"  # explicitly set
        assert body["name_nick"] == "Johnny"
        assert body["age"] == 35
        assert body["date_of_birth"] == "1888-06-15"
        assert body["biography"] == "A mysterious vampire."

    @respx.mock
    def test_create_character_with_vampire_attributes(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify creating a character with vampire attributes."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=character_response_data))

        # Given: Vampire attributes to create
        vampire_attrs = VampireAttributesCreate(
            clan_id="clan123",
            generation=10,
            sire="Ancient One",
            bane_name="Rarefied Tastes",
            bane_description="Feeds only on specific blood",
        )

        # When: Creating a character with vampire attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            vampire_attributes=vampire_attrs,
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.vampire_attributes is not None
        assert result.vampire_attributes.clan_name == "Ventrue"

        # Verify request body includes vampire_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "vampire_attributes" in body
        assert body["vampire_attributes"]["clan_id"] == "clan123"
        assert body["vampire_attributes"]["generation"] == 10
        assert body["vampire_attributes"]["sire"] == "Ancient One"
        assert body["vampire_attributes"]["bane_name"] == "Rarefied Tastes"
        assert body["vampire_attributes"]["bane_description"] == "Feeds only on specific blood"

    @respx.mock
    def test_create_character_with_werewolf_attributes(
        self, vclient, base_url, werewolf_character_response_data
    ) -> None:
        """Verify creating a character with werewolf attributes."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=werewolf_character_response_data))

        # Given: Werewolf attributes to create
        werewolf_attrs = WerewolfAttributesCreate(
            tribe_id="tribe123",
            auspice_id="auspice123",
            pack_name="Moon Runners",
        )

        # When: Creating a character with werewolf attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="WEREWOLF",
            game_version="V5",
            name_first="Wolf",
            name_last="Runner",
            werewolf_attributes=werewolf_attrs,
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.werewolf_attributes is not None
        assert result.werewolf_attributes.tribe_name == "Shadow Lords"
        assert result.werewolf_attributes.auspice_name == "Ahroun"

        # Verify request body includes werewolf_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "werewolf_attributes" in body
        assert body["werewolf_attributes"]["tribe_id"] == "tribe123"
        assert body["werewolf_attributes"]["auspice_id"] == "auspice123"
        assert body["werewolf_attributes"]["pack_name"] == "Moon Runners"

    @respx.mock
    def test_create_character_with_hunter_attributes(
        self, vclient, base_url, hunter_character_response_data
    ) -> None:
        """Verify creating a character with hunter attributes."""
        # Given: A mocked create endpoint
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=hunter_character_response_data))

        # Given: Hunter attributes to create
        hunter_attrs = HunterAttributesCreate(
            creed="Avenger",
        )

        # When: Creating a character with hunter attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="HUNTER",
            game_version="V5",
            name_first="John",
            name_last="Hunter",
            hunter_attributes=hunter_attrs,
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.hunter_attributes is not None
        assert result.hunter_attributes.creed == "Avenger"

        # Verify request body includes hunter_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "hunter_attributes" in body
        assert body["hunter_attributes"]["creed"] == "Avenger"

    @respx.mock
    def test_create_character_with_traits(self, vclient, base_url, character_response_data) -> None:
        """Verify creating a character with traits."""
        # Given: A mocked create endpoint
        response_data = {
            **character_response_data,
            "character_trait_ids": ["trait123", "trait456"],
        }
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(201, json=response_data))

        # Given: Traits to assign
        from vweb.api_client.models.character_trait import CharacterCreateTraitAssign

        traits = [
            CharacterCreateTraitAssign(trait_id="trait123", value=3),
            CharacterCreateTraitAssign(trait_id="trait456", value=2),
        ]

        # When: Creating a character with traits
        result = vclient.characters("on-behalf-of-user", company_id="company123").create(
            campaign_id="campaign123",
            character_class="VAMPIRE",
            game_version="V5",
            name_first="John",
            name_last="Doe",
            traits=traits,
        )

        # Then: The route was called and character is returned
        assert route.called
        assert isinstance(result, Character)
        assert len(result.character_trait_ids) == 2

        # Verify request body includes traits
        import json

        body = json.loads(route.calls[0].request.content)
        assert "traits" in body
        assert len(body["traits"]) == 2
        assert body["traits"][0]["trait_id"] == "trait123"
        assert body["traits"][0]["value"] == 3
        assert body["traits"][1]["trait_id"] == "trait456"
        assert body["traits"][1]["value"] == 2


class TestCharactersServiceUpdate:
    """Tests for CharactersService.update method."""

    @respx.mock
    def test_update_character_name(self, vclient, base_url, character_response_data) -> None:
        """Verify updating a character's name."""
        # Given: A mocked update endpoint
        updated_data = {**character_response_data, "name_first": "Jane"}
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=updated_data))

        # When: Updating the character's name
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", name_first="Jane"
        )

        # Then: The route was called and updated character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.name_first == "Jane"

        # Verify only name_first was in request body
        import json

        body = json.loads(route.calls[0].request.content)
        assert body == {"name_first": "Jane"}

    @respx.mock
    def test_update_character_status(self, vclient, base_url, character_response_data) -> None:
        """Verify updating a character's status to dead."""
        # Given: A mocked update endpoint
        updated_data = {
            **character_response_data,
            "status": "DEAD",
            "date_killed": "2024-06-15T10:00:00Z",
        }
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=updated_data))

        # When: Updating the character's status
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", status="DEAD"
        )

        # Then: The route was called and updated character is returned
        assert route.called
        assert result.status == "DEAD"

    @respx.mock
    def test_update_character_date_of_birth(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify setting date_of_birth sends an ISO 8601 date string."""
        # Given: A mocked update endpoint
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Updating the date_of_birth
        vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", date_of_birth=date(1888, 6, 15)
        )

        # Then: The request body carries the ISO date string
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"date_of_birth": "1888-06-15"}

    @respx.mock
    def test_update_character_clears_date_of_birth(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify passing date_of_birth=None sends an explicit null to clear it."""
        # Given: A mocked update endpoint returning a cleared date_of_birth
        cleared_data = {**character_response_data, "date_of_birth": None}
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=cleared_data))

        # When: Clearing the date_of_birth with an explicit None
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", date_of_birth=None
        )

        # Then: The explicit null survives exclude_none and reaches the server
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"date_of_birth": None}
        assert result.date_of_birth is None

    @respx.mock
    def test_update_character_clears_blanked_profile_fields(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify None on a clearable profile field sends null, while omitted fields stay out."""
        # Given: A mocked update endpoint
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Clearing the nickname, age, and concept while renaming the character
        vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", name_first="Renamed", name_nick=None, age=None, concept_id=None
        )

        # Then: Each cleared field is sent as null and nothing else is added
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"name_first": "Renamed", "name_nick": None, "age": None, "concept_id": None}

    @respx.mock
    def test_update_character_not_found(self, vclient, base_url) -> None:
        """Verify updating a non-existent character raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='nonexistent')}"
        ).mock(
            return_value=MockResponse(
                404, json={"detail": "Character not found", "status_code": 404}
            )
        )

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.characters("on-behalf-of-user", company_id="company123").update(
                "nonexistent", name_first="Jane"
            )

        assert route.called

    @respx.mock
    def test_update_character_vampire_attributes(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify updating a character's vampire attributes."""
        # Given: A mocked update endpoint with updated vampire attributes
        updated_data = {
            **character_response_data,
            "vampire_attributes": {
                "clan_id": "clan456",
                "clan_name": "Toreador",
                "generation": 9,
                "sire": "New Sire",
                "bane_name": None,
                "bane_description": None,
                "compulsion_name": "Obsession",
                "compulsion_description": "Cannot resist beauty",
            },
        }
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=updated_data))

        # Given: Vampire attributes to update
        vampire_attrs = VampireAttributesUpdate(
            clan_id="clan456",
            generation=9,
            sire="New Sire",
            compulsion_name="Obsession",
            compulsion_description="Cannot resist beauty",
        )

        # When: Updating the character's vampire attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char123", vampire_attributes=vampire_attrs
        )

        # Then: The route was called and updated character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.vampire_attributes is not None
        assert result.vampire_attributes.clan_name == "Toreador"
        assert result.vampire_attributes.generation == 9
        assert result.vampire_attributes.sire == "New Sire"

        # Verify request body includes vampire_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "vampire_attributes" in body
        assert body["vampire_attributes"]["clan_id"] == "clan456"
        assert body["vampire_attributes"]["generation"] == 9
        assert body["vampire_attributes"]["sire"] == "New Sire"
        assert body["vampire_attributes"]["compulsion_name"] == "Obsession"

    @respx.mock
    def test_update_character_werewolf_attributes(
        self, vclient, base_url, werewolf_character_response_data
    ) -> None:
        """Verify updating a character's werewolf attributes."""
        # Given: A mocked update endpoint with updated werewolf attributes
        updated_data = {
            **werewolf_character_response_data,
            "werewolf_attributes": {
                "tribe_id": "tribe456",
                "tribe_name": "Silver Fangs",
                "auspice_id": "auspice456",
                "auspice_name": "Galliard",
                "pack_name": "Star Gazers",
            },
        }
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char456')}"
        ).mock(return_value=MockResponse(200, json=updated_data))

        # Given: Werewolf attributes to update
        werewolf_attrs = WerewolfAttributesUpdate(
            tribe_id="tribe456",
            auspice_id="auspice456",
            pack_name="Star Gazers",
        )

        # When: Updating the character's werewolf attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char456", werewolf_attributes=werewolf_attrs
        )

        # Then: The route was called and updated character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.werewolf_attributes is not None
        assert result.werewolf_attributes.tribe_name == "Silver Fangs"
        assert result.werewolf_attributes.auspice_name == "Galliard"
        assert result.werewolf_attributes.pack_name == "Star Gazers"

        # Verify request body includes werewolf_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "werewolf_attributes" in body
        assert body["werewolf_attributes"]["tribe_id"] == "tribe456"
        assert body["werewolf_attributes"]["auspice_id"] == "auspice456"
        assert body["werewolf_attributes"]["pack_name"] == "Star Gazers"

    @respx.mock
    def test_update_character_hunter_attributes(
        self, vclient, base_url, hunter_character_response_data
    ) -> None:
        """Verify updating a character's hunter attributes."""
        # Given: A mocked update endpoint with updated hunter attributes
        updated_data = {
            **hunter_character_response_data,
            "hunter_attributes": {
                "creed": "Defender",
            },
        }
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char789')}"
        ).mock(return_value=MockResponse(200, json=updated_data))

        # Given: Hunter attributes to update
        hunter_attrs = HunterAttributesUpdate(
            creed="Defender",
        )

        # When: Updating the character's hunter attributes
        result = vclient.characters("on-behalf-of-user", company_id="company123").update(
            "char789", hunter_attributes=hunter_attrs
        )

        # Then: The route was called and updated character is returned
        assert route.called
        assert isinstance(result, Character)
        assert result.hunter_attributes is not None
        assert result.hunter_attributes.creed == "Defender"

        # Verify request body includes hunter_attributes
        import json

        body = json.loads(route.calls[0].request.content)
        assert "hunter_attributes" in body
        assert body["hunter_attributes"]["creed"] == "Defender"


class TestCharactersServiceDelete:
    """Tests for CharactersService.delete method."""

    @respx.mock
    def test_delete_character(self, vclient, base_url) -> None:
        """Verify deleting a character."""
        # Given: A mocked delete endpoint
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(204))

        # When: Deleting the character
        result = vclient.characters("on-behalf-of-user", company_id="company123").delete("char123")

        # Then: The route was called and None is returned
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_character_not_found(self, vclient, base_url) -> None:
        """Verify deleting a non-existent character raises NotFoundError."""
        # Given: A mocked 404 response
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='nonexistent')}"
        ).mock(
            return_value=MockResponse(
                404, json={"detail": "Character not found", "status_code": 404}
            )
        )

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.characters("on-behalf-of-user", company_id="company123").delete("nonexistent")

        assert route.called


class TestCharactersServiceListAll:
    """Tests for CharactersService.list_all method."""

    @respx.mock
    def test_list_all_characters(self, vclient, base_url, character_response_data) -> None:
        """Verify list_all returns all characters across pages."""
        # Given: A mocked endpoint that returns paginated results
        paginated_response = page(character_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Requesting all characters
        result = vclient.characters("on-behalf-of-user", company_id="company123").list_all()

        # Then: All characters are returned as a list
        assert route.called
        assert len(result) == 1
        assert isinstance(result[0], Character)
        assert result[0].name_first == "John"


class TestCharactersServiceIterAll:
    """Tests for CharactersService.iter_all method."""

    @respx.mock
    def test_iter_all_characters(self, vclient, base_url, character_response_data) -> None:
        """Verify iter_all yields characters across pages."""
        # Given: A mocked endpoint
        paginated_response = page(character_response_data, limit=100)
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTERS.format(company_id='company123', user_id='user123', campaign_id='campaign123')}"
        ).mock(return_value=MockResponse(200, json=paginated_response))

        # When: Iterating through all characters
        characters = list(
            vclient.characters("on-behalf-of-user", company_id="company123").iter_all()
        )

        # Then: All characters are yielded
        assert route.called
        assert len(characters) == 1
        assert isinstance(characters[0], Character)


class TestCharactersServiceVampireAttributes:
    """Tests for character vampire attributes handling."""

    @respx.mock
    def test_get_character_with_vampire_attributes(
        self, vclient, base_url, character_response_data
    ) -> None:
        """Verify vampire attributes are properly parsed."""
        # Given: A mocked character endpoint
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER.format(company_id='company123', user_id='user123', campaign_id='campaign123', character_id='char123')}"
        ).mock(return_value=MockResponse(200, json=character_response_data))

        # When: Requesting the character
        result = vclient.characters("on-behalf-of-user", company_id="company123").get("char123")

        # Then: Vampire attributes are properly parsed
        assert route.called
        assert result.vampire_attributes is not None
        assert result.vampire_attributes.clan_name == "Ventrue"
        assert result.vampire_attributes.generation == 10
        assert result.vampire_attributes.sire == "Ancient One"


class TestCharactersServiceGetStatistics:
    """Tests for CharactersService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, vclient, base_url, statistics_response_data):
        """Verify getting character statistics."""
        # Given: A mocked statistics endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_STATISTICS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
            params={"num_top_traits": "5"},
        ).respond(200, json=statistics_response_data)

        # When: Getting statistics
        result = vclient.characters("on-behalf-of-user", company_id=company_id).get_statistics(
            character_id
        )

        # Then: Returns RollStatistics object
        assert route.called
        assert isinstance(result, RollStatistics)
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0


class TestCharactersServiceGetFullSheet:
    """Tests for CharactersService.get_full_sheet method."""

    @respx.mock
    def test_get_full_sheet(self, vclient, base_url, full_sheet_response_data):
        """Verify getting character full sheet."""
        # Given: A mocked full sheet endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_FULL_SHEET.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
        ).respond(200, json=full_sheet_response_data)

        # When: Getting the full sheet
        result = vclient.characters("on-behalf-of-user", company_id=company_id).get_full_sheet(
            character_id
        )

        # Then: Returns CharacterFullSheet with correct hierarchy
        assert route.called
        assert isinstance(result, CharacterFullSheet)
        assert result.character.name_first == "Marcus"
        assert len(result.sections) == 1
        assert result.sections[0].name == "Physical"
        assert result.sections[0].categories[0].character_traits[0].value == 3

    @respx.mock
    def test_get_full_sheet_with_available_traits(
        self, vclient, base_url, full_sheet_response_data_with_available_traits
    ):
        """Verify getting full sheet with include_available_traits param."""
        # Given: A mocked full sheet endpoint expecting the query param
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_FULL_SHEET.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
            params={"include_available_traits": "true"},
        ).respond(200, json=full_sheet_response_data_with_available_traits)

        # When: Getting the full sheet with include_available_traits=True
        result = vclient.characters("on-behalf-of-user", company_id=company_id).get_full_sheet(
            character_id, include_available_traits=True
        )

        # Then: Returns CharacterFullSheet with available_traits populated
        assert route.called
        assert isinstance(result, CharacterFullSheet)
        assert len(result.sections[0].categories[0].available_traits) == 1
        assert result.sections[0].categories[0].available_traits[0].name == "Dexterity"


class TestCharactersServiceGetFullSheetCategory:
    """Tests for CharactersService.get_full_sheet_category method."""

    @respx.mock
    def test_get_full_sheet_category(self, vclient, base_url, full_sheet_category_response_data):
        """Verify getting a single category from the full sheet."""
        # Given: A mocked category endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        character_id = "char123"
        category_id = "cat1"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_FULL_SHEET_CATEGORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id, category_id=category_id)}",
        ).respond(200, json=full_sheet_category_response_data)

        # When: Getting a single category
        result = vclient.characters(
            "on-behalf-of-user", company_id=company_id
        ).get_full_sheet_category(character_id, category_id)

        # Then: Returns FullSheetTraitCategory with correct data
        assert route.called
        assert isinstance(result, FullSheetTraitCategory)
        assert result.id == "cat1"
        assert result.name == "Attributes"
        assert len(result.character_traits) == 1
        assert result.character_traits[0].value == 3

    @respx.mock
    def test_get_full_sheet_category_with_available_traits(
        self, vclient, base_url, full_sheet_category_response_data_with_available_traits
    ):
        """Verify getting a category with available traits."""
        # Given: A mocked category endpoint expecting the query param
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        character_id = "char123"
        category_id = "cat1"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_FULL_SHEET_CATEGORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id, category_id=category_id)}",
            params={"include_available_traits": "true"},
        ).respond(200, json=full_sheet_category_response_data_with_available_traits)

        # When: Getting a category with available traits
        result = vclient.characters(
            "on-behalf-of-user", company_id=company_id
        ).get_full_sheet_category(character_id, category_id, include_available_traits=True)

        # Then: Returns category with available_traits populated
        assert route.called
        assert isinstance(result, FullSheetTraitCategory)
        assert len(result.available_traits) == 1
        assert result.available_traits[0].name == "Dexterity"


class TestCharactersServiceInventory:
    """Tests for CharactersService inventory methods."""

    @respx.mock
    def test_get_inventory_page(self, vclient, base_url, inventory_item_response_data):
        """Verify getting a page of inventory items."""
        # Given: A mocked inventory endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json=page(inventory_item_response_data),
        )

        # When: Getting a page of inventory items
        result = vclient.characters("on-behalf-of-user", company_id=company_id).get_inventory_page(
            character_id
        )

        # Then: Returns paginated InventoryItem objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], InventoryItem)
        assert result.items[0].name == "Test Item"
        assert result.items[0].type == "BOOK"
        assert result.items[0].description == "This is test content"
        assert result.items[0].character_id == "char123"
        assert result.items[0].date_created == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert result.items[0].date_modified == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    @respx.mock
    def test_list_all_inventory(self, vclient, base_url, inventory_item_response_data):
        """Verify listing all inventory items."""
        # Given: A mocked inventory endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
        ).respond(
            200,
            json={"items": [inventory_item_response_data], "total": 1, "limit": 100, "offset": 0},
        )

        # When: Listing all inventory items
        result = vclient.characters("on-behalf-of-user", company_id=company_id).list_all_inventory(
            character_id
        )

        # Then: Returns list of InventoryItem objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], InventoryItem)
        assert result[0].name == "Test Item"

    @respx.mock
    def test_iter_all_inventory(self, vclient, base_url, inventory_item_response_data):
        """Verify iterating through all inventory items."""
        # Given: A mocked inventory endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}",
        ).respond(
            200,
            json={"items": [inventory_item_response_data], "total": 1, "limit": 100, "offset": 0},
        )
        # When: Iterating through all inventory items
        result = list(
            vclient.characters("on-behalf-of-user", company_id=company_id).iter_all_inventory(
                character_id
            )
        )

        # Then: Returns list of InventoryItem objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], InventoryItem)
        assert result[0].name == "Test Item"

    @respx.mock
    def test_get_inventory_item(self, vclient, base_url, inventory_item_response_data):
        """Verify getting a specific inventory item."""
        # Given: A mocked inventory item endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        item_id = "item123"
        route = respx.get(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY_ITEM.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id, item_id=item_id)}"
        ).respond(200, json=inventory_item_response_data)
        # When: Getting the inventory item
        result = vclient.characters("on-behalf-of-user", company_id=company_id).get_inventory_item(
            character_id, item_id
        )

        # Then: Returns InventoryItem object
        assert route.called
        assert isinstance(result, InventoryItem)
        assert result.name == "Test Item"
        assert result.type == "BOOK"
        assert result.description == "This is test content"
        assert result.character_id == "char123"

    @respx.mock
    def test_create_inventory_item(self, vclient, base_url, inventory_item_response_data):
        """Verify creating a new inventory item."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        route = respx.post(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id)}"
        ).respond(201, json=inventory_item_response_data)
        # When: Creating the inventory item
        result = vclient.characters(
            "on-behalf-of-user", company_id=company_id
        ).create_inventory_item(
            character_id, name="Test Item", type="BOOK", description="This is test content"
        )

        # Then: Returns InventoryItem object
        assert route.called
        assert isinstance(result, InventoryItem)
        assert result.name == "Test Item"
        assert result.type == "BOOK"
        assert result.description == "This is test content"
        assert result.character_id == "char123"

    @respx.mock
    def test_update_inventory_item(self, vclient, base_url, inventory_item_response_data):
        """Verify updating an inventory item."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        item_id = "item123"
        updated_data = {**inventory_item_response_data, "name": "Updated Item"}
        route = respx.patch(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY_ITEM.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id, item_id=item_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the inventory item
        result = vclient.characters(
            "on-behalf-of-user", company_id=company_id
        ).update_inventory_item(character_id, item_id, name="Updated Item")

        # Then: Returns InventoryItem object
        assert route.called
        assert isinstance(result, InventoryItem)
        assert result.name == "Updated Item"
        assert result.type == "BOOK"
        assert result.description == "This is test content"
        assert result.character_id == "char123"

    @respx.mock
    def test_delete_inventory_item(self, vclient, base_url):
        """Verify deleting an inventory item."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        character_id = "char123"
        item_id = "item123"
        route = respx.delete(
            f"{base_url}{Endpoints.CHARACTER_INVENTORY_ITEM.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id, character_id=character_id, item_id=item_id)}"
        ).respond(204)

        # When: Deleting the inventory item
        vclient.characters("on-behalf-of-user", company_id=company_id).delete_inventory_item(
            character_id, item_id
        )

        # Then: Request was made
        assert route.called


V5_HEALTH = {"type": "DAMAGE", "size": 5, "damage": 2, "extra_levels": 0}
V4_HEALTH = {
    "type": "DAMAGE",
    "size": 7,
    "damage": 1,
    "extra_levels": 0,
    "levels": [{"name": "Bruised", "marked": True}, {"name": "Hurt", "marked": False}],
}


def _health_url(base_url: str, endpoint: str) -> str:
    """Build a health endpoint URL for the standard test ids."""
    return f"{base_url}{endpoint.format(company_id='company123', character_id='char123')}"


class TestCharactersServiceHealth:
    """Tests for CharactersService health methods."""

    @pytest.fixture
    def service(self, vclient):
        """Return a characters service for the standard test ids."""
        return vclient.characters("on-behalf-of-user", company_id="company123")

    @respx.mock
    def test_get_health(self, service, base_url) -> None:
        """Verify get_health returns V5 health with no levels."""
        # Given: A mocked health endpoint
        respx.get(_health_url(base_url, Endpoints.CHARACTER_HEALTH)).mock(
            return_value=MockResponse(200, json=V5_HEALTH)
        )

        # When: Getting health
        result = service.get_health("char123")

        # Then: A Health object is returned
        assert isinstance(result, Health)
        assert result.damage == 2
        assert result.levels is None

    @respx.mock
    def test_get_health_not_found(self, service, base_url) -> None:
        """Verify a character without health raises NotFoundError."""
        # Given: The endpoint returns 404
        respx.get(_health_url(base_url, Endpoints.CHARACTER_HEALTH)).mock(
            return_value=MockResponse(
                404,
                json={"status": 404, "title": "Not Found", "detail": "Character health not found"},
            )
        )

        # When/Then: Getting health raises
        with pytest.raises(NotFoundError):
            service.get_health("char123")

    @respx.mock
    def test_set_health_sends_all_fields(self, service, base_url) -> None:
        """Verify set_health sends every field so omitted ones reset to zero."""
        # Given: A mocked set health endpoint
        route = respx.put(_health_url(base_url, Endpoints.CHARACTER_HEALTH)).mock(
            return_value=MockResponse(200, json=V5_HEALTH)
        )

        # When: Setting only damage
        service.set_health("char123", damage=2)

        # Then: All fields are sent
        assert json.loads(route.calls.last.request.content) == {"extra_levels": 0, "damage": 2}

    @respx.mock
    def test_set_health_request_model(self, service, base_url) -> None:
        """Verify set_health accepts a HealthStateSet and parses V4 levels."""
        # Given: A mocked set health endpoint returning V4 health
        route = respx.put(_health_url(base_url, Endpoints.CHARACTER_HEALTH)).mock(
            return_value=MockResponse(200, json=V4_HEALTH)
        )

        # When: Setting damage with a request model
        result = service.set_health("char123", HealthStateSet(damage=1, extra_levels=1))

        # Then: The state is sent and V4 levels are parsed
        assert json.loads(route.calls.last.request.content) == {"extra_levels": 1, "damage": 1}
        assert result.levels[0].marked is True

    def test_set_health_negative_rejected(self, service) -> None:
        """Verify a negative value fails before any request."""
        # When/Then: Setting negative damage raises
        with pytest.raises(RequestValidationError):
            service.set_health("char123", damage=-1)

    def test_set_health_typed_mark_rejected(self, service) -> None:
        """Verify a removed typed damage field fails instead of resetting health."""
        # When/Then: Setting superficial damage raises
        with pytest.raises(RequestValidationError):
            service.set_health("char123", superficial=2)

    @respx.mock
    def test_apply_health_action_damage(self, service, base_url) -> None:
        """Verify a damage action sends only action and amount."""
        # Given: A mocked health action endpoint
        route = respx.post(_health_url(base_url, Endpoints.CHARACTER_HEALTH_ACTIONS)).mock(
            return_value=MockResponse(200, json=V5_HEALTH)
        )

        # When: Applying two damage
        result = service.apply_health_action("char123", "damage", amount=2)

        # Then: Only action and amount are sent
        assert json.loads(route.calls.last.request.content) == {"action": "damage", "amount": 2}
        assert isinstance(result, Health)

    def test_apply_health_action_no_damage_type(self, service) -> None:
        """Verify apply_health_action no longer accepts a damage type."""
        # When/Then: Passing damage_type raises
        with pytest.raises(TypeError):
            service.apply_health_action("char123", "damage", damage_type="AGGRAVATED")

    @respx.mock
    def test_apply_health_action_validation_error(self, service, base_url) -> None:
        """Verify a 400 from the server raises ValidationError."""
        # Given: The endpoint rejects the action
        respx.post(_health_url(base_url, Endpoints.CHARACTER_HEALTH_ACTIONS)).mock(
            return_value=MockResponse(
                400, json={"status": 400, "title": "Bad Request", "detail": "Invalid action"}
            )
        )

        # When/Then: Applying the action raises
        with pytest.raises(ValidationError):
            service.apply_health_action("char123", "spend")
