"""Tests for CompaniesService audit log methods."""

import pytest
import respx

from tests.api_client.payloads import page, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import AuditLog, AuditLogDetail, PaginatedResponse
from vweb.api_client.testing import AuditLogDetailFactory, AuditLogFactory

COMPANY_ID = "company123"


@pytest.fixture
def audit_log_response_data() -> dict:
    """Return audit log response data."""
    return wire(AuditLogFactory.build(entity_type="CAMPAIGN", operation="CREATE"))


@pytest.fixture
def audit_log_detail_response_data() -> dict:
    """Return audit log detail response data with request forensics."""
    return wire(AuditLogDetailFactory.build(method="POST", request_json={"name": "Test Campaign"}))


@pytest.fixture
def paginated_audit_logs_response(audit_log_response_data) -> dict:
    """Return a one-item paginated audit logs response."""
    return page(audit_log_response_data)


class TestCompaniesServiceGetAuditLogPage:
    """Tests for CompaniesService.get_audit_log_page method."""

    @respx.mock
    def test_get_audit_log_page(self, vclient, base_url, paginated_audit_logs_response):
        """Verify get_audit_log_page returns paginated AuditLog objects."""
        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_audit_logs_response)

        result = vclient.companies.get_audit_log_page(COMPANY_ID)

        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], AuditLog)
        assert result.items[0].entity_type == "CAMPAIGN"
        assert result.items[0].operation == "CREATE"

    @respx.mock
    def test_get_audit_log_page_with_filters(
        self, vclient, base_url, paginated_audit_logs_response
    ):
        """Verify get_audit_log_page passes filter parameters."""
        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={
                "limit": "10",
                "offset": "0",
                "entity_type": "CAMPAIGN",
                "operation": "CREATE",
                "acting_user_id": "user111",
            },
        ).respond(200, json=paginated_audit_logs_response)

        result = vclient.companies.get_audit_log_page(
            COMPANY_ID,
            entity_type="CAMPAIGN",
            operation="CREATE",
            acting_user_id="user111",
        )

        assert route.called
        assert isinstance(result, PaginatedResponse)

    @respx.mock
    def test_get_audit_log_page_with_date_filters(
        self, vclient, base_url, paginated_audit_logs_response
    ):
        """Verify get_audit_log_page serializes datetime filters to ISO 8601."""
        from datetime import UTC, datetime

        date_from = datetime(2024, 1, 1, tzinfo=UTC)
        date_to = datetime(2024, 12, 31, tzinfo=UTC)

        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={
                "limit": "10",
                "offset": "0",
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        ).respond(200, json=paginated_audit_logs_response)

        result = vclient.companies.get_audit_log_page(
            COMPANY_ID,
            date_from=date_from,
            date_to=date_to,
        )

        assert route.called
        assert isinstance(result, PaginatedResponse)

    @respx.mock
    def test_get_audit_log_page_with_include_returns_detail(
        self, vclient, base_url, audit_log_detail_response_data
    ):
        """Verify get_audit_log_page returns AuditLogDetail when include has request_details."""
        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={"limit": "10", "offset": "0", "include": "request_details"},
        ).respond(
            200,
            json=page(audit_log_detail_response_data),
        )

        result = vclient.companies.get_audit_log_page(COMPANY_ID, include=["request_details"])

        assert route.called
        assert isinstance(result.items[0], AuditLogDetail)
        assert result.items[0].method == "POST"
        assert result.items[0].request_json == {"name": "Test Campaign"}


class TestCompaniesServiceListAllAuditLogs:
    """Tests for CompaniesService.list_all_audit_logs method."""

    @respx.mock
    def test_list_all_audit_logs(self, vclient, base_url, audit_log_response_data):
        """Verify list_all_audit_logs returns all audit logs across pages."""
        respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json=page(audit_log_response_data, limit=100),
        )

        result = vclient.companies.list_all_audit_logs(COMPANY_ID)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], AuditLog)


class TestCompaniesServiceIterAllAuditLogs:
    """Tests for CompaniesService.iter_all_audit_logs method."""

    @respx.mock
    def test_iter_all_audit_logs(self, vclient, base_url, audit_log_response_data):
        """Verify iter_all_audit_logs yields AuditLog objects across pages."""
        respx.get(
            f"{base_url}{Endpoints.COMPANY_AUDIT_LOGS.format(company_id=COMPANY_ID)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json=page(audit_log_response_data, limit=100),
        )

        logs = list(vclient.companies.iter_all_audit_logs(COMPANY_ID))

        assert len(logs) == 1
        assert isinstance(logs[0], AuditLog)


class TestCompaniesServiceAuditLogFilters:
    """Tests for audit log filter validation."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda svc: svc.get_audit_log_page(COMPANY_ID, not_a_filter="x"),
            lambda svc: svc.list_all_audit_logs(COMPANY_ID, limit=5),
            lambda svc: svc.iter_all_audit_logs(COMPANY_ID, not_a_filter="x"),
        ],
    )
    def test_unknown_filter_raises_type_error(self, vclient, call):
        """Verify an unknown keyword raises TypeError before any request is sent."""
        with pytest.raises(TypeError):
            call(vclient.companies)
