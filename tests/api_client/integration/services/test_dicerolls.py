"""Integration tests for DicerollService."""

import json

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.models import Diceroll, PaginatedResponse


@pytest.fixture
def diceroll_response_data() -> dict:
    """Return sample diceroll response data."""
    return {
        "id": "diceroll123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "dice_size": 10,
        "difficulty": 6,
        "num_dice": 1,
        "num_desperation_dice": 0,
        "comment": "A test comment",
        "trait_ids": ["trait1", "trait2"],
        "user_id": "user123",
        "character_id": "character123",
        "campaign_id": "campaign123",
        "company_id": "company123",
        "quickroll_id": "quickroll123",
        "result": {
            "total_result": 1,
            "total_result_type": "SUCCESS",
            "total_result_humanized": "Success",
            "total_dice_roll": [1],
            "player_roll": [1],
            "desperation_roll": [0],
            "player_roll_emoji": "🎲",
            "player_roll_shortcode": ":one:",
            "desperation_roll_emoji": "💥",
            "desperation_roll_shortcode": ":one:",
            "total_dice_roll_emoji": "🎲",
            "total_dice_roll_shortcode": ":one:",
            "total_result_emoji": "🎉",
            "total_result_shortcode": "1",
        },
    }


@pytest.fixture
def paginated_dicerolls_response(diceroll_response_data) -> dict:
    """Return sample paginated dicerolls response."""
    return {
        "items": [diceroll_response_data],
        "limit": 10,
        "offset": 0,
        "total": 1,
    }


class TestDicerollServiceGetPage:
    """Tests for DicerollService.get_page method."""

    @respx.mock
    def test_get_page(self, vclient, base_url, paginated_dicerolls_response):
        """Verify getting a page of dicerolls."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting a page of dicerolls
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").get_page()

        # Then: Returns paginated Diceroll objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Diceroll)
        assert result.items[0].id == "diceroll123"
        assert result.total == 1
        assert result.items[0].result is not None
        assert result.items[0].result.total_result == 1
        assert result.items[0].result.total_result_type == "SUCCESS"
        assert result.items[0].result.total_result_humanized == "Success"
        assert result.items[0].result.total_dice_roll == [1]
        assert result.items[0].result.player_roll == [1]
        assert result.items[0].result.desperation_roll == [0]
        assert result.items[0].result.player_roll_emoji == "🎲"
        assert result.items[0].result.player_roll_shortcode == ":one:"
        assert result.items[0].result.desperation_roll_emoji == "💥"

    @respx.mock
    def test_get_page_with_filters(self, vclient, base_url, paginated_dicerolls_response):
        """Verify get_page accepts filter parameters."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={
                "limit": "10",
                "offset": "0",
                "userid": "user123",
                "characterid": "character123",
                "campaignid": "campaign123",
                "character_type": "PLAYER",
            },
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting a page of dicerolls with filters
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").get_page(
            userid="user123",
            characterid="character123",
            campaignid="campaign123",
            character_type="PLAYER",
        )

        # Then: Returns paginated Diceroll objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Diceroll)
        assert result.items[0].id == "diceroll123"
        assert result.total == 1
        assert result.items[0].result is not None
        assert result.items[0].result.total_result == 1
        assert result.items[0].result.total_result_type == "SUCCESS"
        assert result.items[0].result.total_result_humanized == "Success"

    @respx.mock
    def test_get_page_with_character_type_filter(
        self, vclient, base_url, paginated_dicerolls_response
    ):
        """Verify get_page filters by character_type alone."""
        # Given: A mocked diceroll endpoint expecting only the character_type filter
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={"limit": "10", "offset": "0", "character_type": "STORYTELLER"},
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting a page filtered by character type
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").get_page(
            character_type="STORYTELLER"
        )

        # Then: Returns paginated Diceroll objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Diceroll)

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, paginated_dicerolls_response):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={"limit": "25", "offset": "50"},
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting a page of dicerolls with pagination
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").get_page(
            limit=25, offset=50
        )

        # Then: Returns paginated Diceroll objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Diceroll)
        assert result.items[0].id == "diceroll123"
        assert result.total == 1
        assert result.items[0].result is not None
        assert result.items[0].result.total_result == 1
        assert result.items[0].result.total_result_type == "SUCCESS"
        assert result.items[0].result.total_result_humanized == "Success"


class TestDicerollServiceListAll:
    """Tests for DicerollService.list_all method."""

    @respx.mock
    def test_list_all(self, vclient, base_url, paginated_dicerolls_response):
        """Verify getting all dicerolls."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting all dicerolls
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").list_all()

        # Then: Returns list of Diceroll objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Diceroll)
        assert result[0].id == "diceroll123"
        assert result[0].result is not None
        assert result[0].result.total_result == 1

    @respx.mock
    def test_list_all_with_filters(self, vclient, base_url, paginated_dicerolls_response):
        """Verify list_all accepts filter parameters."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={
                "userid": "user123",
                "characterid": "character123",
                "campaignid": "campaign123",
                "character_type": "PLAYER",
            },
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting all dicerolls with filters
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").list_all(
            userid="user123",
            characterid="character123",
            campaignid="campaign123",
            character_type="PLAYER",
        )

        # Then: Returns list of Diceroll objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Diceroll)
        assert result[0].id == "diceroll123"
        assert result[0].result is not None
        assert result[0].result.total_result == 1

    @respx.mock
    def test_list_all_with_character_type_filter(
        self, vclient, base_url, paginated_dicerolls_response
    ):
        """Verify list_all filters by character_type alone."""
        # Given: A mocked diceroll endpoint expecting only the character_type filter
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
            params={"character_type": "NPC"},
        ).respond(200, json=paginated_dicerolls_response)

        # When: Getting all dicerolls filtered by character type
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").list_all(
            character_type="NPC"
        )

        # Then: Returns list of Diceroll objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Diceroll)


class TestDicerollServiceIterAll:
    """Tests for DicerollService.iter_all method."""

    @respx.mock
    def test_iter_all(self, vclient, base_url, paginated_dicerolls_response):
        """Verify iterating through all dicerolls."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
        ).respond(200, json=paginated_dicerolls_response)

        # When: Iterating through all dicerolls
        result = list(vclient.dicerolls("on-behalf-of-user", company_id="company123").iter_all())

        # Then: Returns list of Diceroll objects
        assert route.called
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Diceroll)
        assert result[0].id == "diceroll123"
        assert result[0].result is not None
        assert result[0].result.total_result == 1


class TestDicerollServiceGet:
    """Tests for DicerollService.get method."""

    @respx.mock
    def test_get(self, vclient, base_url, diceroll_response_data):
        """Verify getting a diceroll."""
        # Given: A mocked diceroll endpoint
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLL.format(company_id='company123', user_id='user123', diceroll_id='diceroll123')}",
        ).respond(200, json=diceroll_response_data)

        # When: Getting a diceroll
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").get("diceroll123")

        # Then: Returns Diceroll object
        assert route.called
        assert isinstance(result, Diceroll)
        assert result.id == "diceroll123"
        assert result.result is not None
        assert result.result.total_result == 1
        assert result.result.total_result_type == "SUCCESS"
        assert result.result.total_result_humanized == "Success"
        assert result.result.total_dice_roll == [1]
        assert result.result.player_roll == [1]
        assert result.result.desperation_roll == [0]

    @respx.mock
    def test_get_not_found(self, vclient, base_url):
        """Verify getting a non-existent diceroll raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        route = respx.get(
            f"{base_url}{Endpoints.DICEROLL.format(company_id='company123', user_id='user123', diceroll_id='nonexistent')}",
        ).respond(404, json={"detail": "Diceroll not found"})

        # When/Then: Getting the diceroll raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.dicerolls("on-behalf-of-user", company_id="company123").get("nonexistent")

        assert route.called


class TestDicerollServiceCreate:
    """Tests for DicerollService.create method."""

    @respx.mock
    def test_create(self, vclient, base_url, diceroll_response_data):
        """Verify creating a diceroll."""
        # Given: A mocked diceroll endpoint
        route = respx.post(
            f"{base_url}{Endpoints.DICEROLLS.format(company_id='company123', user_id='user123')}",
        ).respond(200, json=diceroll_response_data)

        # When: Creating a diceroll
        result = vclient.dicerolls("on-behalf-of-user", company_id="company123").create(
            dice_size=10,
            difficulty=6,
            num_dice=1,
            num_desperation_dice=0,
            comment="A test comment",
            trait_ids=["trait1", "trait2"],
            character_id="character123",
            campaign_id="campaign123",
            dice_modifier=1,
        )

        # Then: Returns Diceroll object
        assert route.called
        assert isinstance(result, Diceroll)
        assert result.id == "diceroll123"
        assert result.result is not None
        assert result.result.total_result == 1
        assert result.result.total_result_type == "SUCCESS"
        assert result.result.total_result_humanized == "Success"

        # Verify request body
        request = route.calls.last.request
        body = json.loads(request.content)
        assert body == {
            "dice_size": 10,
            "difficulty": 6,
            "num_dice": 1,
            "num_desperation_dice": 0,
            "dice_modifier": 1,
            "comment": "A test comment",
            "trait_ids": ["trait1", "trait2"],
            "character_id": "character123",
            "campaign_id": "campaign123",
        }


class TestDicerollServiceCreateQuickroll:
    """Tests for DicerollService.create_from_quickroll method."""

    @respx.mock
    def test_create_from_quickroll(self, vclient, base_url, diceroll_response_data):
        """Verify creating a diceroll quickroll."""
        # Given: A mocked diceroll endpoint
        route = respx.post(
            f"{base_url}{Endpoints.DICEROLL_QUICKROLL.format(company_id='company123', user_id='user123')}",
        ).respond(200, json=diceroll_response_data)

        # When: Creating a diceroll quickroll
        result = vclient.dicerolls(
            "on-behalf-of-user", company_id="company123"
        ).create_from_quickroll(
            quickroll_id="quickroll123",
            character_id="character123",
            comment="A test comment",
            difficulty=6,
            num_desperation_dice=0,
        )

        # Then: Returns Diceroll object
        assert route.called
        assert isinstance(result, Diceroll)

        # Verify request body
        request = route.calls.last.request
        body = json.loads(request.content)
        assert body == {
            "quickroll_id": "quickroll123",
            "character_id": "character123",
            "comment": "A test comment",
            "difficulty": 6,
            "num_desperation_dice": 0,
            "dice_modifier": 0,
        }

    @respx.mock
    def test_create_from_quickroll_sends_dice_modifier(
        self, vclient, base_url, diceroll_response_data
    ):
        """Verify the quickroll request carries dice_modifier."""
        # Given: A mocked quickroll endpoint
        route = respx.post(
            f"{base_url}{Endpoints.DICEROLL_QUICKROLL.format(company_id='company123', user_id='user123')}",
        ).respond(200, json=diceroll_response_data)

        # When: Creating a quickroll with a negative modifier
        vclient.dicerolls("on-behalf-of-user", company_id="company123").create_from_quickroll(
            quickroll_id="quickroll123", character_id="character123", dice_modifier=-1
        )

        # Then: The modifier is in the request body
        assert json.loads(route.calls.last.request.content)["dice_modifier"] == -1
