"""Service for interacting with the Companies API."""

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any, TypedDict, Unpack

from vweb.api_client.constants import (
    DEFAULT_PAGE_LIMIT,
    AuditEntityType,
    AuditLogInclude,
    AuditOperation,
    PermissionLevel,
)
from vweb.api_client.models import (
    AuditLog,
    AuditLogDetail,
    Company,
    CompanyCreate,
    CompanyPermissions,
    CompanyUpdate,
    NewCompanyResponse,
    PaginatedResponse,
    RollStatistics,
    _GrantAccess,
)
from vweb.api_client.routes import Routes, RouteSpec
from vweb.api_client.services.base import BaseService


class AuditLogFilters(TypedDict, total=False):
    """Filters accepted by the company audit log methods.

    Attributes:
        acting_user_id: Filter by the user who performed the action.
        user_id: Filter by the user affected by the action.
        campaign_id: Filter by campaign ID.
        book_id: Filter by book ID.
        chapter_id: Filter by chapter ID.
        character_id: Filter by character ID.
        entity_type: Filter by entity type (e.g., "CAMPAIGN", "CHARACTER").
        operation: Filter by operation type (CREATE, UPDATE, DELETE).
        date_from: Return logs on or after this datetime.
        date_to: Return logs on or before this datetime.
        include: Additional data to include. Pass ["request_details"] for HTTP forensics.
    """

    acting_user_id: str | None
    user_id: str | None
    campaign_id: str | None
    book_id: str | None
    chapter_id: str | None
    character_id: str | None
    entity_type: AuditEntityType | None
    operation: AuditOperation | None
    date_from: datetime | None
    date_to: datetime | None
    include: Sequence[AuditLogInclude] | None


class CompaniesService(BaseService):
    """Service for managing companies in the Valentina API.

    Provides methods to create, retrieve, update, and delete companies,
    as well as manage developer access permissions.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            companies = client.companies.list()
            company = client.companies.get("company_id")
    """

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Company]:
        """Retrieve a paginated page of companies you have access to.

        Only companies where you have been granted at least user-level permissions are returned.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Company objects and pagination metadata.
        """
        return self._page(Routes.COMPANIES_LIST, limit=limit, offset=offset)

    def list_all(self) -> list[Company]:
        """Retrieve all companies you have access to.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Returns:
            A list of all Company objects.
        """
        return self._list_all(Routes.COMPANIES_LIST)

    def iter_all(self, *, limit: int = 100) -> Iterator[Company]:
        """Iterate through all companies you have access to.

        Yields individual companies, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Company objects.

        Example:
            for company in client.companies.iter_all():
                print(company.name)
        """
        yield from self._iter(Routes.COMPANIES_LIST, limit=limit)

    def get(self, company_id: str) -> Company:
        """Retrieve detailed information about a specific company.

        Fetches the company including its settings and configuration.

        Args:
            company_id: The ID of the company to retrieve.

        Returns:
            The Company object with full details.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return self._call(Routes.COMPANIES_GET, company_id=company_id)

    def create(
        self,
        request: CompanyCreate | None = None,
        **kwargs,
    ) -> NewCompanyResponse:
        """Create a new company in the system.

        You are automatically granted OWNER permission for the new company, giving you
        full administrative control, including the ability to grant permissions to
        other developers.

        Args:
            request: A CompanyCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CompanyCreate if request is not provided.
                Accepts: name (str, required), email (str, required),
                description (str | None), settings (CompanySettingsCreate | None).

        Returns:
            The newly created NewCompanyResponse object containing the company and admin user.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(CompanyCreate, **kwargs)
        return self._call(
            Routes.COMPANIES_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

    def update(
        self,
        company_id: str,
        request: CompanyUpdate | None = None,
        **kwargs,
    ) -> Company:
        """Modify a company's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.
        Set description to None to clear it.

        Args:
            company_id: The ID of the company to update.
            request: A CompanyUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CompanyUpdate if request is not provided.
                Accepts: name (str | None), email (str | None),
                description (str | None), settings (CompanySettingsUpdate | None).

        Returns:
            The updated Company object.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have admin-level access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(CompanyUpdate, **kwargs)
        return self._call(
            Routes.COMPANIES_UPDATE,
            json=self._update_payload(body, clearable={"description"}),
            company_id=company_id,
        )

    def delete(self, company_id: str) -> None:
        """Delete a company from the system.

        This is a destructive action that archives the company and all associated data.

        Args:
            company_id: The ID of the company to delete.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have owner-level access.
        """
        self._send(Routes.COMPANIES_DELETE, company_id=company_id)

    def grant_access(
        self,
        company_id: str,
        developer_id: str,
        permission: PermissionLevel,
    ) -> CompanyPermissions:
        """Add, update, or revoke a developer's permission level for a company.

        Valid permission levels are USER, ADMIN, and OWNER. Set permission to REVOKE
        to revoke access entirely.

        Args:
            company_id: The ID of the company.
            developer_id: The ID of the developer to grant/modify access for.
            permission: The permission level to grant (USER, ADMIN, OWNER, or REVOKE).

        Returns:
            The CompanyPermissions object confirming the granted permission.

        Raises:
            NotFoundError: If the company or developer does not exist.
            AuthorizationError: If you don't have owner-level access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If trying to remove the last owner.
        """
        body = self._validate_request(
            _GrantAccess,
            developer_id=developer_id,
            permission=permission,
        )
        return self._call(
            Routes.COMPANIES_ACCESS, json=body.model_dump(mode="json"), company_id=company_id
        )

    def get_statistics(
        self,
        company_id: str,
        *,
        num_top_traits: int = 5,
    ) -> RollStatistics:
        """Retrieve aggregated dice roll statistics for a specific company.

        Includes success rates, critical frequencies, most-used traits, etc.
        across all users and campaigns in the company.

        Args:
            company_id: The ID of the company to get statistics for.
            num_top_traits: Number of top traits to include (default 5).

        Returns:
            RollStatistics object with aggregated statistics.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return self._call(
            Routes.COMPANIES_STATISTICS,
            params={"num_top_traits": num_top_traits},
            company_id=company_id,
        )

    def get_audit_log_page(
        self,
        company_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        **filters: Unpack[AuditLogFilters],
    ) -> PaginatedResponse[AuditLog] | PaginatedResponse[AuditLogDetail]:
        """Retrieve a paginated page of audit log entries for a company.

        Pass ``include=["request_details"]`` to receive full HTTP request forensics in each
        entry (returns AuditLogDetail instead of AuditLog).

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).
            **filters: Filters that narrow the results; see ``AuditLogFilters``.

        Returns:
            A PaginatedResponse containing AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        route, params = self._audit_log_query(filters)
        return self._page(
            route,
            limit=limit,
            offset=offset,
            params=params,
            company_id=company_id,
        )

    def list_all_audit_logs(
        self,
        company_id: str,
        **filters: Unpack[AuditLogFilters],
    ) -> list[AuditLog] | list[AuditLogDetail]:
        """Retrieve all audit log entries for a company.

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
            **filters: Filters that narrow the results; see ``AuditLogFilters``.

        Returns:
            A list of all AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        route, params = self._audit_log_query(filters)
        return self._list_all(route, params=params, company_id=company_id)

    def iter_all_audit_logs(
        self,
        company_id: str,
        *,
        limit: int = 100,
        **filters: Unpack[AuditLogFilters],
    ) -> Iterator[AuditLog] | Iterator[AuditLogDetail]:
        """Iterate through all audit log entries for a company, fetching pages as needed.

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
            limit: Items per page (default 100 for efficiency).
            **filters: Filters that narrow the results; see ``AuditLogFilters``.

        Returns:
            An iterator of AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        route, params = self._audit_log_query(filters)
        return self._iter(route, limit=limit, params=params, company_id=company_id)

    def _audit_log_query(
        self, filters: AuditLogFilters
    ) -> tuple[RouteSpec[AuditLog] | RouteSpec[AuditLogDetail], dict[str, Any] | None]:
        """Pick the route variant and build query params for an audit log request.

        The API takes ``include`` as one comma-joined value and datetimes as ISO 8601.

        Args:
            filters: The caller's audit log filters.

        Returns:
            The route to call, which sets the model entries parse into, and the query params.

        Raises:
            TypeError: If ``filters`` holds a key that is not an audit log filter.
        """
        if unknown := filters.keys() - AuditLogFilters.__optional_keys__:
            msg = f"Unexpected audit log filter(s): {', '.join(sorted(unknown))}"
            raise TypeError(msg)

        include = filters.get("include")
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        route = (
            Routes.COMPANIES_AUDIT_LOGS_LIST_DETAIL
            if include and "request_details" in include
            else Routes.COMPANIES_AUDIT_LOGS_LIST
        )
        params = self._build_params(
            acting_user_id=filters.get("acting_user_id"),
            user_id=filters.get("user_id"),
            campaign_id=filters.get("campaign_id"),
            book_id=filters.get("book_id"),
            chapter_id=filters.get("chapter_id"),
            character_id=filters.get("character_id"),
            entity_type=filters.get("entity_type"),
            operation=filters.get("operation"),
            date_from=date_from.isoformat() if date_from is not None else None,
            date_to=date_to.isoformat() if date_to is not None else None,
            include=",".join(include) if include is not None else None,
        )
        return route, params
