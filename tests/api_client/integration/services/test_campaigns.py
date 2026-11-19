"""Tests for vweb.api_client.services.campaigns."""

from datetime import date

import pytest

from tests.api_client.payloads import page, sent_json, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import Campaign
from vweb.api_client.testing import CampaignFactory

COMPANY_ID = "company123"
CAMPAIGN_ID = "campaign123"
CAMPAIGNS = Endpoints.CAMPAIGNS.format(company_id=COMPANY_ID)
CAMPAIGN = Endpoints.CAMPAIGN.format(company_id=COMPANY_ID, campaign_id=CAMPAIGN_ID)


@pytest.fixture
def service(vclient):
    """Return the campaigns service for the test company."""
    return vclient.campaigns("on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def campaign() -> Campaign:
    """Return a campaign to serve from the mocked API."""
    return CampaignFactory.build(id=CAMPAIGN_ID)


@pytest.mark.parametrize(
    ("fetch", "params"),
    [
        pytest.param(
            lambda svc: svc.get_page(limit=25, offset=50).items,
            {"limit": "25", "offset": "50"},
            id="get_page",
        ),
        pytest.param(lambda svc: svc.list_all(), {"limit": "100", "offset": "0"}, id="list_all"),
        pytest.param(
            lambda svc: list(svc.iter_all()), {"limit": "100", "offset": "0"}, id="iter_all"
        ),
    ],
)
def test_list_campaigns(service, mock_api, campaign, fetch, params):
    """Verify each listing method pages the company's campaigns and parses them."""
    # Given: A campaigns endpoint expecting the method's pagination
    route = mock_api.get(CAMPAIGNS, params=params).respond(200, json=page(campaign))

    # When: Listing campaigns
    result = fetch(service)

    # Then: The campaigns are parsed
    assert route.called
    assert result == [campaign]


def test_get_campaign(service, mock_api, campaign):
    """Verify get fetches one campaign by id."""
    route = mock_api.get(CAMPAIGN).respond(200, json=wire(campaign))

    assert service.get(CAMPAIGN_ID) == campaign
    assert route.called


@pytest.mark.parametrize(
    ("kwargs", "expected_body"),
    [
        pytest.param({"name": "Test Campaign"}, {"name": "Test Campaign"}, id="minimal"),
        pytest.param(
            {
                "name": "Test Campaign",
                "description": "A test campaign description",
                "in_game_date": date(1924, 3, 15),
                "desperation": 2,
                "danger": 3,
            },
            {
                "name": "Test Campaign",
                "description": "A test campaign description",
                "in_game_date": "1924-03-15",
                "desperation": 2,
                "danger": 3,
            },
            id="all-fields",
        ),
    ],
)
def test_create_campaign(service, mock_api, campaign, kwargs, expected_body):
    """Verify create POSTs only the given fields and parses the created campaign."""
    route = mock_api.post(CAMPAIGNS).respond(201, json=wire(campaign))

    result = service.create(**kwargs)

    assert sent_json(route) == expected_body
    assert result == campaign


def test_invalid_request_raises_before_sending(service, mock_api):
    """Verify a request that fails client-side validation raises and sends nothing."""
    # Given: A create endpoint that should never be reached
    route = mock_api.post(CAMPAIGNS).respond(201, json={})

    # When/Then: A too-short name raises RequestValidationError
    with pytest.raises(RequestValidationError):
        service.create(name="AB")
    assert not route.called


@pytest.mark.parametrize(
    ("kwargs", "expected_body"),
    [
        pytest.param({"name": "Updated Name"}, {"name": "Updated Name"}, id="name"),
        pytest.param(
            {"in_game_date": date(1924, 3, 15)}, {"in_game_date": "1924-03-15"}, id="set-date"
        ),
        pytest.param({"in_game_date": None}, {"in_game_date": None}, id="clear-date"),
        pytest.param({"description": None}, {"description": None}, id="clear-description"),
    ],
)
def test_update_campaign(service, mock_api, campaign, kwargs, expected_body):
    """Verify update PATCHes only the given fields, sending null to clear a clearable one."""
    route = mock_api.patch(CAMPAIGN).respond(200, json=wire(campaign))

    result = service.update(CAMPAIGN_ID, **kwargs)

    assert sent_json(route) == expected_body
    assert result == campaign


def test_delete_campaign(service, mock_api):
    """Verify delete sends a DELETE to the campaign."""
    route = mock_api.delete(CAMPAIGN).respond(204)

    assert service.delete(CAMPAIGN_ID) is None
    assert route.called


def test_get_campaign_statistics(service, mock_api, statistics_response_data):
    """Verify get_statistics asks for five top traits by default and parses the result."""
    route = mock_api.get(
        Endpoints.CAMPAIGN_STATISTICS.format(company_id=COMPANY_ID, campaign_id=CAMPAIGN_ID),
        params={"num_top_traits": "5"},
    ).respond(200, json=statistics_response_data)

    result = service.get_statistics(CAMPAIGN_ID)

    assert route.called
    assert result.total_rolls == 100
