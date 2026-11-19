"""Tests for vweb.api_client.services.companies."""

import pytest

from tests.api_client.payloads import page, sent_json, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import Company, CompanySettingsCreate, CompanySettingsUpdate
from vweb.api_client.testing import CompanyFactory, UserFactory

COMPANY_ID = "company123"
COMPANY = Endpoints.COMPANY.format(company_id=COMPANY_ID)


@pytest.fixture
def company() -> Company:
    """Return a company to serve from the mocked API."""
    return CompanyFactory.build(id=COMPANY_ID)


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
def test_list_companies(vclient, mock_api, company, fetch, params):
    """Verify each listing method pages the companies and parses them."""
    route = mock_api.get(Endpoints.COMPANIES, params=params).respond(200, json=page(company))

    result = fetch(vclient.companies)

    assert route.called
    assert result == [company]


def test_get_company(vclient, mock_api, company):
    """Verify get fetches one company by id."""
    route = mock_api.get(COMPANY).respond(200, json=wire(company))

    assert vclient.companies.get(COMPANY_ID) == company
    assert route.called


@pytest.mark.parametrize(
    ("kwargs", "expected_body"),
    [
        pytest.param(
            {"name": "Test Company", "email": "test@example.com"},
            {"name": "Test Company", "email": "test@example.com"},
            id="minimal",
        ),
        pytest.param(
            {
                "name": "Test Company",
                "email": "test@example.com",
                "description": "A test company",
                "settings": CompanySettingsCreate(
                    character_autogen_xp_cost=15,
                    character_autogen_num_choices=5,
                    permission_manage_campaign="STORYTELLER",
                    permission_manage_npc="STORYTELLER",
                    permission_grant_xp="PLAYER",
                    permission_free_trait_changes="WITHIN_24_HOURS",
                ),
            },
            {
                "name": "Test Company",
                "email": "test@example.com",
                "description": "A test company",
                "settings": {
                    "character_autogen_xp_cost": 15,
                    "character_autogen_num_choices": 5,
                    "permission_manage_campaign": "STORYTELLER",
                    "permission_manage_npc": "STORYTELLER",
                    "permission_grant_xp": "PLAYER",
                    "permission_free_trait_changes": "WITHIN_24_HOURS",
                },
            },
            id="all-fields",
        ),
    ],
)
def test_create_company(vclient, mock_api, company, kwargs, expected_body):
    """Verify create POSTs only the given fields and parses the company and its admin user."""
    # Given: A create endpoint returning the new company and its admin user
    admin = UserFactory.build()
    route = mock_api.post(Endpoints.COMPANIES).respond(
        201, json={"company": wire(company), "admin_user": wire(admin)}
    )

    # When: Creating a company
    result = vclient.companies.create(**kwargs)

    # Then: Only the given fields are sent and both parts of the response are parsed
    assert sent_json(route) == expected_body
    assert result.company == company
    assert result.admin_user == admin


@pytest.mark.parametrize(
    ("kwargs", "expected_body"),
    [
        pytest.param({"name": "Updated Name"}, {"name": "Updated Name"}, id="name"),
        pytest.param({"description": None}, {"description": None}, id="clear-description"),
        pytest.param(
            {
                "settings": CompanySettingsUpdate(
                    character_autogen_xp_cost=20, permission_manage_campaign="STORYTELLER"
                )
            },
            {
                "settings": {
                    "character_autogen_xp_cost": 20,
                    "permission_manage_campaign": "STORYTELLER",
                }
            },
            id="settings",
        ),
    ],
)
def test_update_company(vclient, mock_api, company, kwargs, expected_body):
    """Verify update PATCHes only the given fields, sending null to clear the description."""
    route = mock_api.patch(COMPANY).respond(200, json=wire(company))

    result = vclient.companies.update(COMPANY_ID, **kwargs)

    assert sent_json(route) == expected_body
    assert result == company


def test_delete_company(vclient, mock_api):
    """Verify delete sends a DELETE to the company."""
    route = mock_api.delete(COMPANY).respond(204)

    assert vclient.companies.delete(COMPANY_ID) is None
    assert route.called


@pytest.mark.parametrize("permission", ["USER", "ADMIN", "REVOKE"])
def test_grant_access(vclient, mock_api, permission):
    """Verify grant_access POSTs the developer and permission and parses the result."""
    # Given: An access endpoint echoing the permission
    route = mock_api.post(Endpoints.COMPANY_ACCESS.format(company_id=COMPANY_ID)).respond(
        201, json={"company_id": COMPANY_ID, "name": "Test Company", "permission": permission}
    )

    # When: Setting the developer's access
    result = vclient.companies.grant_access(COMPANY_ID, "developer123", permission)

    # Then: The body names the developer and permission
    assert sent_json(route) == {
        "developer_id": "developer123",
        "permission": permission,
    }
    assert result.company_id == COMPANY_ID
    assert result.permission == permission


@pytest.mark.parametrize(
    ("kwargs", "num_top_traits"),
    [pytest.param({}, "5", id="default"), pytest.param({"num_top_traits": 10}, "10", id="custom")],
)
def test_get_company_statistics(
    vclient, mock_api, statistics_response_data, kwargs, num_top_traits
):
    """Verify get_statistics sends num_top_traits and parses the result."""
    route = mock_api.get(
        Endpoints.COMPANY_STATISTICS.format(company_id=COMPANY_ID),
        params={"num_top_traits": num_top_traits},
    ).respond(200, json=statistics_response_data)

    result = vclient.companies.get_statistics(COMPANY_ID, **kwargs)

    assert route.called
    assert result.total_rolls == 100
