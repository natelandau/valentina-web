"""Tests for CompaniesService audit log methods."""

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import AuditLog, AuditLogDetail, PaginatedResponse

COMPANY_ID = "company123"


@pytest.fixture
def audit_log_response_data() -> dict:
    """Return sample audit log response data."""
    return {
        "id": "log123",
        "date_created": "2024-01-15T10:30:00Z",
        "entity_type": "CAMPAIGN",
        "operation": "CREATE",
        "target_entity_id": "campaign456",
        "description": "Created campaign 'Test Campaign'",
        "changes": None,
        "company_id": COMPANY_ID,
        "acting_user_id": "user111",
        "user_id": None,
        "campaign_id": "campaign456",
        "book_id": None,
        "chapter_id": None,
        "character_id": None,
        "request_id": "req789",
    }


@pytest.fixture
def audit_log_detail_response_data(audit_log_response_data) -> dict:
    """Return sample audit log detail response data with request forensics."""
    return {
        **audit_log_response_data,
        "method": "POST",
        "url": "/api/v1/companies/company123/users/user111/campaigns",
        "request_json": {"name": "Test Campaign"},
        "request_body": '{"name": "Test Campaign"}',
        "path_params": {"company_id": "company123", "user_id": "user111"},
        "query_params": {},
        "operation_id": "create_campaign",
        "handler_name": "CampaignsHandler.create",
        "name": "Create Campaign",
        "summary": "Create a new campaign",
    }


@pytest.fixture
def paginated_audit_logs_response(audit_log_response_data) -> dict:
    """Return sample paginated audit logs response."""
    return {
        "items": [audit_log_response_data],
        "limit": 10,
        "offset": 0,
        "total": 1,
    }


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
            json={
                "items": [audit_log_detail_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
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
            json={
                "items": [audit_log_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
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
            json={
                "items": [audit_log_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
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
