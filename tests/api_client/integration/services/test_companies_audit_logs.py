"""Tests for CompaniesService audit log methods."""

from datetime import UTC, datetime

import pytest

from tests.api_client.payloads import page, sent_params
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import AuditLog, AuditLogDetail
from vweb.api_client.testing import AuditLogDetailFactory, AuditLogFactory

COMPANY_ID = "company123"
AUDIT_LOGS = Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)

FETCHES = [
    pytest.param(
        lambda svc, **filters: svc.get_audit_log_page(COMPANY_ID, **filters).items,
        "10",
        id="get_page",
    ),
    pytest.param(
        lambda svc, **filters: svc.list_all_audit_logs(COMPANY_ID, **filters), "100", id="list_all"
    ),
    pytest.param(
        lambda svc, **filters: list(svc.iter_all_audit_logs(COMPANY_ID, **filters)),
        "100",
        id="iter_all",
    ),
]


@pytest.mark.parametrize(("fetch", "limit"), FETCHES)
@pytest.mark.parametrize(
    ("filters", "entry", "expected_type"),
    [
        pytest.param({}, AuditLogFactory.build(), AuditLog, id="summary"),
        pytest.param(
            {"include": ["request_details"]},
            AuditLogDetailFactory.build(method="POST", request_json={"name": "Test Campaign"}),
            AuditLogDetail,
            id="request-details",
        ),
    ],
)
def test_fetch_audit_logs(vclient, mock_api, fetch, limit, filters, entry, expected_type):
    """Verify each audit log method parses request details only when they are included."""
    # Given: An audit log endpoint returning one entry
    route = mock_api.get(AUDIT_LOGS).respond(200, json=page(entry))

    # When: Fetching audit logs
    result = fetch(vclient.companies, **filters)

    # Then: The include is sent and entries parse as the matching model
    sent = sent_params(route)
    assert sent == {
        "limit": limit,
        "offset": "0",
        **({"include": "request_details"} if filters else {}),
    }
    assert [type(log) for log in result] == [expected_type]
    assert result[0] == entry


def test_audit_log_filters_are_sent_as_query_params(vclient, mock_api):
    """Verify filters are sent as query params, with datetimes in ISO 8601."""
    # Given: An audit log endpoint
    route = mock_api.get(AUDIT_LOGS).respond(200, json=page())
    date_from = datetime(2024, 1, 1, tzinfo=UTC)
    date_to = datetime(2024, 12, 31, tzinfo=UTC)

    # When: Fetching a page with filters
    vclient.companies.get_audit_log_page(
        COMPANY_ID,
        entity_type="CAMPAIGN",
        operation="CREATE",
        acting_user_id="user111",
        date_from=date_from,
        date_to=date_to,
    )

    # Then: Every filter reaches the query string
    assert sent_params(route) == {
        "limit": "10",
        "offset": "0",
        "entity_type": "CAMPAIGN",
        "operation": "CREATE",
        "acting_user_id": "user111",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }


@pytest.mark.parametrize(
    "call",
    [
        lambda svc: svc.get_audit_log_page(COMPANY_ID, not_a_filter="x"),
        lambda svc: svc.list_all_audit_logs(COMPANY_ID, limit=5),
        lambda svc: svc.iter_all_audit_logs(COMPANY_ID, not_a_filter="x"),
    ],
)
def test_unknown_filter_raises_type_error(vclient, mock_api, call):
    """Verify an unknown keyword raises TypeError before any request is sent."""
    with pytest.raises(TypeError):
        call(vclient.companies)
    assert not mock_api.calls
