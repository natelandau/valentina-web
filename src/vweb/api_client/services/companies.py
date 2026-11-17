"""Service for interacting with the Companies API."""

from collections.abc import Iterator, Sequence
from datetime import datetime

from vweb.api_client.constants import (
    DEFAULT_PAGE_LIMIT,
    AuditEntityType,
    AuditLogInclude,
    AuditOperation,
    PermissionLevel,
)
from vweb.api_client.endpoints import Endpoints
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
from vweb.api_client.services._audit_params import _build_audit_params
from vweb.api_client.services.base import BaseService


class CompaniesService(BaseService):
    """Service for managing companies in the Valentina API.

    Provides methods to create, retrieve, update, and delete companies,
    as well as manage developer access permissions.

    Example:
        with VClient() as client:
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
        return self._get_paginated_as(
            Endpoints.COMPANIES,
            Company,
            limit=limit,
            offset=offset,
        )

    def list_all(self) -> list[Company]:
        """Retrieve all companies you have access to.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Returns:
            A list of all Company objects.
        """
        return list(self.iter_all())

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
        for item in self._iter_all_pages(Endpoints.COMPANIES, limit=limit):
            yield Company.model_validate(item)

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
        response = self._get(Endpoints.COMPANY.format(company_id=company_id))
        return Company.model_validate(response.json())

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
        response = self._post(
            Endpoints.COMPANIES,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return NewCompanyResponse.model_validate(response.json())

    def update(
        self,
        company_id: str,
        request: CompanyUpdate | None = None,
        **kwargs,
    ) -> Company:
        """Modify a company's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.

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
        response = self._patch(
            Endpoints.COMPANY.format(company_id=company_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Company.model_validate(response.json())

    def delete(self, company_id: str) -> None:
        """Delete a company from the system.

        This is a destructive action that archives the company and all associated data.

        Args:
            company_id: The ID of the company to delete.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have owner-level access.
        """
        self._delete(Endpoints.COMPANY.format(company_id=company_id))

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
        response = self._post(
            Endpoints.COMPANY_ACCESS.format(company_id=company_id),
            json=body.model_dump(mode="json"),
        )
        return CompanyPermissions.model_validate(response.json())

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
        response = self._get(
            Endpoints.COMPANY_STATISTICS.format(company_id=company_id),
            params={"num_top_traits": num_top_traits},
        )
        return RollStatistics.model_validate(response.json())

    def get_audit_log_page(
        self,
        company_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        acting_user_id: str | None = None,
        user_id: str | None = None,
        campaign_id: str | None = None,
        book_id: str | None = None,
        chapter_id: str | None = None,
        character_id: str | None = None,
        entity_type: AuditEntityType | None = None,
        operation: AuditOperation | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include: Sequence[AuditLogInclude] | None = None,
    ) -> PaginatedResponse[AuditLog] | PaginatedResponse[AuditLogDetail]:
        """Retrieve a paginated page of audit log entries for a company.

        Use filter parameters to narrow results by entity, operation, user, or time range.
        Pass ``include=["request_details"]`` to receive full HTTP request forensics in each
        entry (returns AuditLogDetail instead of AuditLog).

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).
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

        Returns:
            A PaginatedResponse containing AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        model = AuditLogDetail if include and "request_details" in include else AuditLog
        params = _build_audit_params(
            acting_user_id=acting_user_id,
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            chapter_id=chapter_id,
            character_id=character_id,
            entity_type=entity_type,
            operation=operation,
            date_from=date_from,
            date_to=date_to,
            include=include,
        )
        return self._get_paginated_as(
            Endpoints.COMPANY_AUDIT_LOGS.format(company_id=company_id),
            model,
            limit=limit,
            offset=offset,
            params=params,
        )

    def list_all_audit_logs(
        self,
        company_id: str,
        *,
        acting_user_id: str | None = None,
        user_id: str | None = None,
        campaign_id: str | None = None,
        book_id: str | None = None,
        chapter_id: str | None = None,
        character_id: str | None = None,
        entity_type: AuditEntityType | None = None,
        operation: AuditOperation | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include: Sequence[AuditLogInclude] | None = None,
    ) -> list[AuditLog] | list[AuditLogDetail]:
        """Retrieve all audit log entries for a company.

        Automatically paginates through all results. Use ``get_audit_log_page()`` for
        paginated access or ``iter_all_audit_logs()`` for memory-efficient streaming.

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
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

        Returns:
            A list of all AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return list(
            self.iter_all_audit_logs(
                company_id,
                acting_user_id=acting_user_id,
                user_id=user_id,
                campaign_id=campaign_id,
                book_id=book_id,
                chapter_id=chapter_id,
                character_id=character_id,
                entity_type=entity_type,
                operation=operation,
                date_from=date_from,
                date_to=date_to,
                include=include,
            )
        )

    def iter_all_audit_logs(
        self,
        company_id: str,
        *,
        limit: int = 100,
        acting_user_id: str | None = None,
        user_id: str | None = None,
        campaign_id: str | None = None,
        book_id: str | None = None,
        chapter_id: str | None = None,
        character_id: str | None = None,
        entity_type: AuditEntityType | None = None,
        operation: AuditOperation | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include: Sequence[AuditLogInclude] | None = None,
    ) -> Iterator[AuditLog] | Iterator[AuditLogDetail]:
        """Iterate through all audit log entries for a company.

        Yields individual audit log entries, automatically fetching subsequent pages
        until all matching entries have been retrieved.

        Args:
            company_id: The ID of the company whose audit logs to retrieve.
            limit: Items per page (default 100 for efficiency).
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

        Yields:
            Individual AuditLog (or AuditLogDetail) objects.

        Raises:
            NotFoundError: If the company does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        model = AuditLogDetail if include and "request_details" in include else AuditLog
        params = _build_audit_params(
            acting_user_id=acting_user_id,
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            chapter_id=chapter_id,
            character_id=character_id,
            entity_type=entity_type,
            operation=operation,
            date_from=date_from,
            date_to=date_to,
            include=include,
        )
        for item in self._iter_all_pages(
            Endpoints.COMPANY_AUDIT_LOGS.format(company_id=company_id),
            limit=limit,
            params=params,
        ):
            yield model.model_validate(item)
