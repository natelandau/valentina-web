"""Tests for vweb.api_client.services.companies."""

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import AuthorizationError, NotFoundError, RequestValidationError
from vweb.api_client.models import (
    Company,
    CompanyPermissions,
    CompanySettingsCreate,
    CompanySettingsUpdate,
    NewCompanyResponse,
    PaginatedResponse,
    RollStatistics,
)


@pytest.fixture
def new_company_response_data(company_response_data: dict, user_response_data: dict) -> dict:
    """Return sample new company response data."""
    return {
        "company": company_response_data,
        "admin_user": user_response_data,
    }


class TestCompaniesServiceGetPage:
    """Tests for CompaniesService.get_page method."""

    @respx.mock
    def test_get_page_companies(self, vclient, base_url, paginated_companies_response):
        """Verify get_page returns paginated Company objects."""
        # Given: A mocked companies list endpoint
        route = respx.get(
            f"{base_url}{Endpoints.COMPANIES}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_companies_response)

        # When: Getting a page of companies
        result = vclient.companies.get_page()

        # Then: Returns PaginatedResponse with Company objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Company)
        assert result.items[0].name == "Test Company"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, company_response_data):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        route = respx.get(
            f"{base_url}{Endpoints.COMPANIES}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json={
                "items": [company_response_data],
                "limit": 25,
                "offset": 50,
                "total": 100,
            },
        )

        # When: Getting a page with custom pagination
        result = vclient.companies.get_page(limit=25, offset=50)

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestCompaniesServiceListAll:
    """Tests for CompaniesService.list_all method."""

    @respx.mock
    def test_list_all_companies(self, vclient, base_url, company_response_data):
        """Verify list_all returns all companies across pages."""
        # Given: Mocked endpoints for multiple pages
        respx.get(
            f"{base_url}{Endpoints.COMPANIES}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [company_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all
        result = vclient.companies.list_all()

        # Then: Returns list of Company objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Company)


class TestCompaniesServiceIterAll:
    """Tests for CompaniesService.iter_all method."""

    @respx.mock
    def test_iter_all_companies(self, vclient, base_url, company_response_data):
        """Verify iter_all yields Company objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company2 = {**company_response_data, "id": "507f1f77bcf86cd799439012", "name": "Company 2"}
        respx.get(
            f"{base_url}{Endpoints.COMPANIES}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [company_response_data],
                "limit": 1,
                "offset": 0,
                "total": 2,
            },
        )
        respx.get(
            f"{base_url}{Endpoints.COMPANIES}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json={
                "items": [company2],
                "limit": 1,
                "offset": 1,
                "total": 2,
            },
        )

        # When: Iterating through all companies
        companies = list(vclient.companies.iter_all(limit=1))

        # Then: All companies are yielded as Company objects
        assert len(companies) == 2
        assert all(isinstance(c, Company) for c in companies)
        assert companies[0].name == "Test Company"
        assert companies[1].name == "Company 2"


class TestCompaniesServiceGet:
    """Tests for CompaniesService.get method."""

    @respx.mock
    def test_get_company(self, vclient, base_url, company_response_data):
        """Verify getting a company returns Company object."""
        # Given: A mocked company endpoint
        company_id = "507f1f77bcf86cd799439011"
        route = respx.get(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            200, json=company_response_data
        )

        # When: Getting the company
        result = vclient.companies.get(company_id)

        # Then: Returns Company object with correct data
        assert route.called
        assert isinstance(result, Company)
        assert result.id == company_id
        assert result.name == "Test Company"
        assert result.email == "test@example.com"

    @respx.mock
    def test_get_company_not_found(self, vclient, base_url):
        """Verify getting non-existent company raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "nonexistent"
        respx.get(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            404, json={"detail": "Company not found"}
        )

        # When/Then: Getting the company raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.companies.get(company_id)


class TestCompaniesServiceCreate:
    """Tests for CompaniesService.create method."""

    @respx.mock
    def test_create_company_minimal(self, vclient, base_url, new_company_response_data):
        """Verify creating company with minimal data."""
        # Given: A mocked create endpoint
        route = respx.post(f"{base_url}{Endpoints.COMPANIES}").respond(
            201, json=new_company_response_data
        )

        # When: Creating a company with minimal data
        result = vclient.companies.create(
            name="Test Company",
            email="test@example.com",
        )

        # Then: Returns created Company object
        assert route.called
        assert isinstance(result, NewCompanyResponse)
        assert result.company.name == "Test Company"
        assert result.admin_user.name_first == "Test"
        assert result.admin_user.name_last == "User"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Company"
        assert body["email"] == "test@example.com"
        assert "description" not in body

    @respx.mock
    def test_create_company_with_all_options(self, vclient, base_url, new_company_response_data):
        """Verify creating company with all options."""
        # Given: A mocked create endpoint
        route = respx.post(f"{base_url}{Endpoints.COMPANIES}").respond(
            201, json=new_company_response_data
        )

        # When: Creating a company with all options using string values
        settings = CompanySettingsCreate(
            character_autogen_xp_cost=15,
            character_autogen_num_choices=5,
            permission_manage_campaign="STORYTELLER",
            permission_manage_npc="STORYTELLER",
            permission_grant_xp="PLAYER",
            permission_free_trait_changes="WITHIN_24_HOURS",
        )
        result = vclient.companies.create(
            name="Test Company",
            email="test@example.com",
            description="A test company",
            settings=settings,
        )

        # Then: Returns created Company object
        assert route.called
        assert isinstance(result, NewCompanyResponse)
        assert result.company.name == "Test Company"
        assert result.admin_user.name_first == "Test"
        assert result.admin_user.name_last == "User"

        # Verify request body includes all options
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name"] == "Test Company"
        assert body["email"] == "test@example.com"
        assert body["description"] == "A test company"
        assert body["settings"]["character_autogen_xp_cost"] == 15
        assert body["settings"]["character_autogen_num_choices"] == 5
        assert body["settings"]["permission_manage_campaign"] == "STORYTELLER"
        assert body["settings"]["permission_manage_npc"] == "STORYTELLER"
        assert body["settings"]["permission_grant_xp"] == "PLAYER"
        assert body["settings"]["permission_free_trait_changes"] == "WITHIN_24_HOURS"

    def test_create_company_validation_error(self, vclient):
        """Verify validation error on invalid data raises RequestValidationError."""
        # When/Then: Creating with invalid data raises RequestValidationError (client-side validation)
        with pytest.raises(RequestValidationError) as exc_info:
            vclient.companies.create(name="AB", email="test@example.com")

        # Verify error details are accessible
        assert len(exc_info.value.errors) == 1
        assert exc_info.value.errors[0]["loc"] == ("name",)


class TestCompaniesServiceUpdate:
    """Tests for CompaniesService.update method."""

    @respx.mock
    def test_update_company_name(self, vclient, base_url, company_response_data):
        """Verify updating company name."""
        # Given: A mocked update endpoint
        company_id = "507f1f77bcf86cd799439011"
        updated_data = {**company_response_data, "name": "Updated Name"}
        route = respx.patch(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            200, json=updated_data
        )

        # When: Updating the company name
        result = vclient.companies.update(company_id, name="Updated Name")

        # Then: Returns updated Company object
        assert route.called
        assert isinstance(result, Company)
        assert result.name == "Updated Name"

        # Verify only name is in request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"name": "Updated Name"}

    @respx.mock
    def test_update_company_with_settings(self, vclient, base_url, company_response_data):
        """Verify updating company with settings object."""
        # Given: A mocked update endpoint
        company_id = "507f1f77bcf86cd799439011"
        route = respx.patch(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            200, json=company_response_data
        )

        # When: Updating with settings object using string values
        settings = CompanySettingsUpdate(
            character_autogen_xp_cost=20,
            permission_manage_campaign="STORYTELLER",
        )
        result = vclient.companies.update(company_id, settings=settings)

        # Then: Returns updated Company object
        assert route.called
        assert isinstance(result, Company)

        # Verify settings in request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["settings"]["character_autogen_xp_cost"] == 20
        assert body["settings"]["permission_manage_campaign"] == "STORYTELLER"

    @respx.mock
    def test_update_company_not_found(self, vclient, base_url):
        """Verify updating non-existent company raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "nonexistent"
        respx.patch(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            404, json={"detail": "Company not found"}
        )

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.companies.update(company_id, name="New Name")

    @respx.mock
    def test_update_company_unauthorized(self, vclient, base_url):
        """Verify updating without permission raises AuthorizationError."""
        # Given: A mocked endpoint returning 403
        company_id = "507f1f77bcf86cd799439011"
        respx.patch(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            403, json={"detail": "Admin access required"}
        )

        # When/Then: Updating raises AuthorizationError
        with pytest.raises(AuthorizationError):
            vclient.companies.update(company_id, name="New Name")


class TestCompaniesServiceDelete:
    """Tests for CompaniesService.delete method."""

    @respx.mock
    def test_delete_company(self, vclient, base_url):
        """Verify deleting a company."""
        # Given: A mocked delete endpoint
        company_id = "507f1f77bcf86cd799439011"
        route = respx.delete(
            f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}"
        ).respond(204)

        # When: Deleting the company
        result = vclient.companies.delete(company_id)

        # Then: Request was made and returns None
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_company_not_found(self, vclient, base_url):
        """Verify deleting non-existent company raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "nonexistent"
        respx.delete(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            404, json={"detail": "Company not found"}
        )

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.companies.delete(company_id)

    @respx.mock
    def test_delete_company_unauthorized(self, vclient, base_url):
        """Verify deleting without permission raises AuthorizationError."""
        # Given: A mocked endpoint returning 403
        company_id = "507f1f77bcf86cd799439011"
        respx.delete(f"{base_url}{Endpoints.COMPANY.format(company_id=company_id)}").respond(
            403, json={"detail": "Owner access required"}
        )

        # When/Then: Deleting raises AuthorizationError
        with pytest.raises(AuthorizationError):
            vclient.companies.delete(company_id)


class TestCompaniesServiceGrantAccess:
    """Tests for CompaniesService.grant_access method."""

    @respx.mock
    def test_grant_user_access(self, vclient, base_url):
        """Verify granting user access to a company."""
        # Given: A mocked grant access endpoint
        company_id = "507f1f77bcf86cd799439011"
        developer_id = "developer123"
        route = respx.post(
            f"{base_url}{Endpoints.COMPANY_ACCESS.format(company_id=company_id)}"
        ).respond(
            201,
            json={
                "company_id": company_id,
                "name": "Test Company",
                "permission": "USER",
            },
        )

        # When: Granting user access using string value
        result = vclient.companies.grant_access(company_id, developer_id, "USER")

        # Then: Returns CompanyPermissions object
        assert route.called
        assert isinstance(result, CompanyPermissions)
        assert result.company_id == company_id
        assert result.permission == "USER"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["developer_id"] == developer_id
        assert body["permission"] == "USER"

    @respx.mock
    def test_grant_admin_access(self, vclient, base_url):
        """Verify granting admin access to a company."""
        # Given: A mocked grant access endpoint
        company_id = "507f1f77bcf86cd799439011"
        developer_id = "developer123"
        route = respx.post(
            f"{base_url}{Endpoints.COMPANY_ACCESS.format(company_id=company_id)}"
        ).respond(
            201,
            json={
                "company_id": company_id,
                "name": "Test Company",
                "permission": "ADMIN",
            },
        )

        # When: Granting admin access using string value
        result = vclient.companies.grant_access(company_id, developer_id, "ADMIN")

        # Then: Returns CompanyPermissions with ADMIN permission
        assert route.called
        assert result.permission == "ADMIN"

    @respx.mock
    def test_revoke_access(self, vclient, base_url):
        """Verify revoking access from a company."""
        # Given: A mocked grant access endpoint
        company_id = "507f1f77bcf86cd799439011"
        developer_id = "developer123"
        route = respx.post(
            f"{base_url}{Endpoints.COMPANY_ACCESS.format(company_id=company_id)}"
        ).respond(
            201,
            json={
                "company_id": company_id,
                "name": "Test Company",
                "permission": "REVOKE",
            },
        )

        # When: Revoking access using string value
        result = vclient.companies.grant_access(company_id, developer_id, "REVOKE")

        # Then: Returns CompanyPermissions with REVOKE permission
        assert route.called
        assert result.permission == "REVOKE"

    @respx.mock
    def test_grant_access_unauthorized(self, vclient, base_url):
        """Verify granting access without permission raises AuthorizationError."""
        # Given: A mocked endpoint returning 403
        company_id = "507f1f77bcf86cd799439011"
        respx.post(f"{base_url}{Endpoints.COMPANY_ACCESS.format(company_id=company_id)}").respond(
            403, json={"detail": "Owner access required"}
        )

        # When/Then: Granting access raises AuthorizationError
        with pytest.raises(AuthorizationError):
            vclient.companies.grant_access(company_id, "developer123", "USER")


class TestCompaniesServiceGetStatistics:
    """Tests for CompaniesService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, vclient, base_url, statistics_response_data):
        """Verify getting company statistics."""
        # Given: A mocked statistics endpoint
        company_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_STATISTICS.format(company_id=company_id)}",
            params={"num_top_traits": "5"},
        ).respond(200, json=statistics_response_data)

        # When: Getting company statistics
        result = vclient.companies.get_statistics(company_id)

        # Then: Returns RollStatistics object with correct data
        assert route.called
        assert isinstance(result, RollStatistics)
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0

    @respx.mock
    def test_get_statistics_custom_top_traits(self, vclient, base_url, statistics_response_data):
        """Verify getting company statistics with custom num_top_traits."""
        # Given: A mocked statistics endpoint expecting custom num_top_traits
        company_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.COMPANY_STATISTICS.format(company_id=company_id)}",
            params={"num_top_traits": "10"},
        ).respond(200, json=statistics_response_data)

        # When: Getting statistics with custom num_top_traits
        result = vclient.companies.get_statistics(company_id, num_top_traits=10)

        # Then: Request was made with correct params
        assert route.called
        assert isinstance(result, RollStatistics)

    @respx.mock
    def test_get_statistics_not_found(self, vclient, base_url):
        """Verify getting statistics for non-existent company raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "nonexistent"
        respx.get(
            f"{base_url}{Endpoints.COMPANY_STATISTICS.format(company_id=company_id)}",
            params={"num_top_traits": "5"},
        ).respond(404, json={"detail": "Company not found"})

        # When/Then: Getting statistics raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.companies.get_statistics(company_id)


class TestCompaniesServiceClientIntegration:
    """Tests for VClient.companies property."""

    def test_companies_property_returns_service(self, vclient):
        """Verify companies property returns CompaniesService instance."""
        # When: Accessing the companies property
        service = vclient.companies

        # Then: Returns a CompaniesService instance
        from vweb.api_client.services.companies import CompaniesService

        assert isinstance(service, CompaniesService)

    def test_companies_property_cached(self, vclient):
        """Verify companies property returns same instance on multiple calls."""
        # When: Accessing the companies property multiple times
        service1 = vclient.companies
        service2 = vclient.companies

        # Then: Returns the same instance
        assert service1 is service2
