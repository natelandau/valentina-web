"""Integration tests for DicerollService."""

import pytest

from tests.api_client.payloads import page, sent_json, sent_params, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import Diceroll
from vweb.api_client.testing import DicerollFactory

COMPANY_ID = "company123"
DICEROLLS = Endpoints.DICEROLLS.format(company_id=COMPANY_ID)
FILTERS = {
    "userid": "user123",
    "characterid": "character123",
    "campaignid": "campaign123",
    "character_type": "PLAYER",
}


@pytest.fixture
def service(vclient):
    """Return the dicerolls service for the test company."""
    return vclient.dicerolls("on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def diceroll() -> Diceroll:
    """Return a diceroll to serve from the mocked API."""
    return DicerollFactory.build(id="diceroll123")


@pytest.mark.parametrize(
    ("fetch", "pagination"),
    [
        pytest.param(
            lambda svc, **filters: svc.get_page(limit=25, offset=50, **filters).items,
            {"limit": "25", "offset": "50"},
            id="get_page",
        ),
        pytest.param(
            lambda svc, **filters: svc.list_all(**filters),
            {"limit": "100", "offset": "0"},
            id="list_all",
        ),
        pytest.param(
            lambda svc, **filters: list(svc.iter_all(**filters)),
            {"limit": "100", "offset": "0"},
            id="iter_all",
        ),
    ],
)
@pytest.mark.parametrize(
    "filters",
    [
        pytest.param({}, id="unfiltered"),
        pytest.param(FILTERS, id="all-filters"),
        pytest.param({"character_type": "STORYTELLER"}, id="character-type-only"),
    ],
)
def test_list_dicerolls(service, mock_api, diceroll, fetch, pagination, filters):
    """Verify each listing method sends only the given filters and parses the rolls."""
    # Given: A dicerolls endpoint returning one roll
    route = mock_api.get(DICEROLLS).respond(200, json=page(diceroll))

    # When: Listing rolls
    result = fetch(service, **filters)

    # Then: Pagination and filters are the whole query, and the roll is parsed
    assert sent_params(route) == {**pagination, **filters}
    assert result == [diceroll]


def test_get_diceroll(service, mock_api, diceroll):
    """Verify get fetches one roll by id."""
    route = mock_api.get(
        Endpoints.DICEROLL.format(company_id=COMPANY_ID, diceroll_id="diceroll123")
    ).respond(200, json=wire(diceroll))

    assert service.get("diceroll123") == diceroll
    assert route.called


def test_create_diceroll(service, mock_api, diceroll):
    """Verify create POSTs the roll's fields and parses the rolled result."""
    # Given: A create endpoint
    route = mock_api.post(DICEROLLS).respond(200, json=wire(diceroll))
    fields = {
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

    # When: Rolling dice
    result = service.create(**fields)

    # Then: The body carries exactly the given fields
    assert sent_json(route) == fields
    assert result == diceroll


@pytest.mark.parametrize(
    ("kwargs", "expected_body"),
    [
        pytest.param(
            {"comment": "A test comment"},
            {
                "comment": "A test comment",
                "difficulty": 6,
                "num_desperation_dice": 0,
                "dice_modifier": 0,
            },
            id="defaults",
        ),
        pytest.param(
            {"difficulty": 7, "num_desperation_dice": 2, "dice_modifier": -1},
            {"difficulty": 7, "num_desperation_dice": 2, "dice_modifier": -1},
            id="overrides",
        ),
    ],
)
def test_create_from_quickroll(service, mock_api, diceroll, kwargs, expected_body):
    """Verify create_from_quickroll POSTs the quickroll and character with roll defaults."""
    route = mock_api.post(Endpoints.DICEROLL_QUICKROLL.format(company_id=COMPANY_ID)).respond(
        200, json=wire(diceroll)
    )

    result = service.create_from_quickroll(
        quickroll_id="quickroll123", character_id="character123", **kwargs
    )

    assert sent_json(route) == {
        "quickroll_id": "quickroll123",
        "character_id": "character123",
        **expected_body,
    }
    assert result == diceroll
