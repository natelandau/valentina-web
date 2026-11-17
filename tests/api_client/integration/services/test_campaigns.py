"""Tests for vweb.api_client.services.campaigns."""

from datetime import date

import pytest
import respx

from tests.api_client.payloads import page, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError, RequestValidationError
from vweb.api_client.models import Campaign, PaginatedResponse, RollStatistics
from vweb.api_client.testing import CampaignFactory


@pytest.fixture
def campaign_response_data() -> dict:
    """Return campaign response data."""
    return wire(
        CampaignFactory.build(
            id="507f1f77bcf86cd799439011", name="Test Campaign", desperation=2, danger=3
        )
    )


@pytest.fixture
def paginated_campaigns_response(campaign_response_data) -> dict:
    """Return a one-item paginated campaigns response."""
    return page(campaign_response_data)


class TestCampaignsServiceGetPage:
    """Tests for CampaignsService.get_page method."""

    @respx.mock
    def test_get_page_campaigns(self, vclient, base_url, paginated_campaigns_response):
        """Verify get_page returns paginated Campaign objects."""
        # Given: A mocked campaigns list endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_campaigns_response)

        # When: Getting a page of campaigns
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).get_page()

        # Then: Returns PaginatedResponse with Campaign objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Campaign)
        assert result.items[0].name == "Test Campaign"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, campaign_response_data):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json=page(campaign_response_data, limit=25, offset=50, total=100),
        )

        # When: Getting a page with custom pagination
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).get_page(
            limit=25, offset=50
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestCampaignsServiceListAll:
    """Tests for CampaignsService.list_all method."""

    @respx.mock
    def test_list_all_campaigns(self, vclient, base_url, campaign_response_data):
        """Verify list_all returns all campaigns across pages."""
        # Given: Mocked endpoint
        company_id = "company123"
        user_id = "user123"
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json=page(campaign_response_data, limit=100),
        )

        # When: Calling list_all
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).list_all()

        # Then: Returns list of Campaign objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Campaign)


class TestCampaignsServiceIterAll:
    """Tests for CampaignsService.iter_all method."""

    @respx.mock
    def test_iter_all_campaigns(self, vclient, base_url, campaign_response_data):
        """Verify iter_all yields Campaign objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company_id = "company123"
        user_id = "user123"
        campaign2 = {
            **campaign_response_data,
            "id": "507f1f77bcf86cd799439012",
            "name": "Campaign 2",
        }
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json=page(campaign_response_data, limit=1, total=2),
        )
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json=page(campaign2, limit=1, offset=1, total=2),
        )

        # When: Iterating through all campaigns
        campaigns = list(
            vclient.campaigns("on-behalf-of-user", company_id=company_id).iter_all(limit=1)
        )

        # Then: All campaigns are yielded as Campaign objects
        assert len(campaigns) == 2
        assert all(isinstance(c, Campaign) for c in campaigns)
        assert campaigns[0].name == "Test Campaign"
        assert campaigns[1].name == "Campaign 2"


class TestCampaignsServiceGet:
    """Tests for CampaignsService.get method."""

    @respx.mock
    def test_get_campaign(self, vclient, base_url, campaign_response_data):
        """Verify getting a campaign returns Campaign object."""
        # Given: A mocked campaign endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(200, json=campaign_response_data)

        # When: Getting the campaign
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).get(campaign_id)

        # Then: Returns Campaign object with correct data
        assert route.called
        assert isinstance(result, Campaign)
        assert result.id == campaign_id
        assert result.name == "Test Campaign"
        assert result.desperation == 2
        assert result.danger == 3

    @respx.mock
    def test_get_campaign_not_found(self, vclient, base_url):
        """Verify getting non-existent campaign raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "nonexistent"
        respx.get(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(404, json={"detail": "Campaign not found"})

        # When/Then: Getting the campaign raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.campaigns("on-behalf-of-user", company_id=company_id).get(campaign_id)


class TestCampaignsServiceCreate:
    """Tests for CampaignsService.create method."""

    @respx.mock
    def test_create_campaign_minimal(self, vclient, base_url, campaign_response_data):
        """Verify creating campaign with minimal data."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.post(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=campaign_response_data)

        # When: Creating a campaign with minimal data
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).create(
            name="Test Campaign"
        )

        # Then: Returns created Campaign object
        assert route.called
        assert isinstance(result, Campaign)
        assert result.name == "Test Campaign"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Campaign"

    @respx.mock
    def test_create_campaign_with_all_fields(self, vclient, base_url, campaign_response_data):
        """Verify creating campaign with all fields."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.post(
            f"{base_url}{Endpoints.CAMPAIGNS.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=campaign_response_data)

        # When: Creating a campaign with all fields
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).create(
            name="Test Campaign",
            description="A test campaign description",
            in_game_date=date(1924, 3, 15),
            desperation=2,
            danger=3,
        )

        # Then: Returns created Campaign object
        assert route.called
        assert isinstance(result, Campaign)

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Campaign"
        assert body["description"] == "A test campaign description"
        assert body["in_game_date"] == "1924-03-15"
        assert body["desperation"] == 2
        assert body["danger"] == 3

    def test_create_campaign_validation_error(self, vclient):
        """Verify validation error on invalid data raises RequestValidationError."""
        # When/Then: Creating with invalid data raises RequestValidationError
        with pytest.raises(RequestValidationError):
            vclient.campaigns("on-behalf-of-user", company_id="company123").create(name="AB")


class TestCampaignsServiceUpdate:
    """Tests for CampaignsService.update method."""

    @respx.mock
    def test_update_campaign_name(self, vclient, base_url, campaign_response_data):
        """Verify updating campaign name."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        updated_data = {**campaign_response_data, "name": "Updated Name"}
        route = respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the campaign name
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).update(
            campaign_id, name="Updated Name"
        )

        # Then: Returns updated Campaign object
        assert route.called
        assert isinstance(result, Campaign)
        assert result.name == "Updated Name"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"name": "Updated Name"}

    @respx.mock
    def test_update_campaign_in_game_date(self, vclient, base_url, campaign_response_data):
        """Verify setting in_game_date sends an ISO 8601 date string."""
        # Given: A mocked update endpoint
        company_id = "company123"
        campaign_id = "507f1f77bcf86cd799439011"
        route = respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, campaign_id=campaign_id)}"
        ).respond(200, json=campaign_response_data)

        # When: Updating the in_game_date
        vclient.campaigns("on-behalf-of-user", company_id=company_id).update(
            campaign_id, in_game_date=date(1924, 3, 15)
        )

        # Then: The request body carries the ISO date string
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"in_game_date": "1924-03-15"}

    @respx.mock
    def test_update_campaign_clears_in_game_date(self, vclient, base_url, campaign_response_data):
        """Verify passing in_game_date=None sends an explicit null to clear it."""
        # Given: A mocked update endpoint returning a cleared in_game_date
        company_id = "company123"
        campaign_id = "507f1f77bcf86cd799439011"
        cleared_data = {**campaign_response_data, "in_game_date": None}
        route = respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, campaign_id=campaign_id)}"
        ).respond(200, json=cleared_data)

        # When: Clearing the in_game_date with an explicit None
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).update(
            campaign_id, in_game_date=None
        )

        # Then: The explicit null survives exclude_none and reaches the server
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"in_game_date": None}
        assert result.in_game_date is None

    @respx.mock
    def test_update_campaign_not_found(self, vclient, base_url):
        """Verify updating non-existent campaign raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "nonexistent"
        respx.patch(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(404, json={"detail": "Campaign not found"})

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.campaigns("on-behalf-of-user", company_id=company_id).update(
                campaign_id, name="New Name"
            )


class TestCampaignsServiceDelete:
    """Tests for CampaignsService.delete method."""

    @respx.mock
    def test_delete_campaign(self, vclient, base_url):
        """Verify deleting a campaign."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        route = respx.delete(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(204)

        # When: Deleting the campaign
        vclient.campaigns("on-behalf-of-user", company_id=company_id).delete(campaign_id)

        # Then: Request was made
        assert route.called

    @respx.mock
    def test_delete_campaign_not_found(self, vclient, base_url):
        """Verify deleting non-existent campaign raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "user123"
        campaign_id = "nonexistent"
        respx.delete(
            f"{base_url}{Endpoints.CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(404, json={"detail": "Campaign not found"})

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.campaigns("on-behalf-of-user", company_id=company_id).delete(campaign_id)


class TestCampaignsServiceGetStatistics:
    """Tests for CampaignsService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, vclient, base_url, statistics_response_data):
        """Verify getting campaign statistics."""
        # Given: A mocked statistics endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.CAMPAIGN_STATISTICS.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}",
            params={"num_top_traits": "5"},
        ).respond(200, json=statistics_response_data)

        # When: Getting statistics
        result = vclient.campaigns("on-behalf-of-user", company_id=company_id).get_statistics(
            campaign_id
        )

        # Then: Returns RollStatistics object
        assert route.called
        assert isinstance(result, RollStatistics)
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0
