"""Service for interacting with the Campaigns API."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT
from vweb.api_client.models import (
    Campaign,
    CampaignCreate,
    CampaignUpdate,
    PaginatedResponse,
    RollStatistics,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services._assets import AssetRoutes, AssetsMixin
from vweb.api_client.services._notes import NoteRoutes, NotesMixin

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class CampaignsService(NotesMixin, AssetsMixin):
    """Service for managing campaigns within a company in the Valentina API.

    This service is scoped to a specific company at initialization time.
    All methods operate within that context.

    Provides methods to create, retrieve, update, and delete campaigns,
    as well as access campaign statistics, assets, and notes.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            campaigns = client.campaigns("company_id")
            all_campaigns = campaigns.list_all()
            campaign = campaigns.get("campaign_id")
    """

    _parent_id_param = "campaign_id"
    _note_routes = NoteRoutes(
        page=Routes.CAMPAIGNS_NOTES_LIST,
        get=Routes.CAMPAIGNS_NOTES_GET,
        create=Routes.CAMPAIGNS_NOTES_CREATE,
        update=Routes.CAMPAIGNS_NOTES_UPDATE,
        delete=Routes.CAMPAIGNS_NOTES_DELETE,
    )
    _asset_routes = AssetRoutes(
        page=Routes.CAMPAIGNS_ASSETS_LIST,
        get=Routes.CAMPAIGNS_ASSETS_GET,
        delete=Routes.CAMPAIGNS_ASSETS_DELETE,
        upload=Routes.CAMPAIGNS_ASSETS_UPLOAD,
    )

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str) -> None:
        """Initialize the service scoped to a specific company.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client, on_behalf_of=on_behalf_of, company_id=company_id)

    # -------------------------------------------------------------------------
    # Campaign CRUD Methods
    # -------------------------------------------------------------------------

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Campaign]:
        """Retrieve a paginated page of campaigns.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Campaign objects and pagination metadata.
        """
        return self._page(Routes.CAMPAIGNS_LIST, limit=limit, offset=offset)

    def list_all(self) -> list[Campaign]:
        """Retrieve all campaigns.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Returns:
            A list of all Campaign objects.
        """
        return list(self.iter_all())

    def iter_all(
        self,
        *,
        limit: int = 100,
    ) -> Iterator[Campaign]:
        """Iterate through all campaigns.

        Yields individual campaigns, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Campaign objects.

        Example:
            for campaign in campaigns.iter_all():
                print(campaign.name)
        """
        yield from self._iter(Routes.CAMPAIGNS_LIST, limit=limit)

    def get(self, campaign_id: str) -> Campaign:
        """Retrieve detailed information about a specific campaign.

        Fetches the campaign including desperation and danger levels.

        Args:
            campaign_id: The ID of the campaign to retrieve.

        Returns:
            The Campaign object with full details.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(Routes.CAMPAIGNS_GET, campaign_id=campaign_id)

    def create(
        self,
        request: CampaignCreate | None = None,
        **kwargs,
    ) -> Campaign:
        """Create a new campaign.

        Args:
            request: A CampaignCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CampaignCreate if request is not provided.
                Accepts: name (str, required), description (str | None),
                in_game_date (datetime.date | None, ISO 8601 calendar date),
                desperation (int, default 0), danger (int, default 0).

        Returns:
            The newly created Campaign object.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            AuthorizationError: If you don't have campaign management privileges.
        """
        body = request if request is not None else self._validate_request(CampaignCreate, **kwargs)
        return self._call(
            Routes.CAMPAIGNS_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

    def update(
        self,
        campaign_id: str,
        request: CampaignUpdate | None = None,
        **kwargs,
    ) -> Campaign:
        """Modify a campaign's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            campaign_id: The ID of the campaign to update.
            request: A CampaignUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CampaignUpdate if request is not provided.
                Accepts: name (str | None), description (str | None),
                in_game_date (datetime.date | None, ISO 8601 calendar date;
                pass None to clear it), desperation (int | None), danger (int | None).

        Returns:
            The updated Campaign object.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have campaign management privileges.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(CampaignUpdate, **kwargs)
        payload = body.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # The API distinguishes an omitted key (leave unchanged) from an explicit null (clear).
        # exclude_none drops None, so re-add in_game_date when the caller set it to None to clear it.
        if "in_game_date" in body.model_fields_set and body.in_game_date is None:
            payload["in_game_date"] = None
        return self._call(Routes.CAMPAIGNS_UPDATE, json=payload, campaign_id=campaign_id)

    def delete(self, campaign_id: str) -> None:
        """Remove a campaign from the system.

        Associated characters, books, and other content will no longer be accessible.
        This action cannot be undone.

        Args:
            campaign_id: The ID of the campaign to delete.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have campaign management privileges.
        """
        self._send(Routes.CAMPAIGNS_DELETE, campaign_id=campaign_id)

    def get_statistics(
        self,
        campaign_id: str,
        *,
        num_top_traits: int = 5,
    ) -> RollStatistics:
        """Retrieve aggregated dice roll statistics for a specific campaign.

        Includes success rates, critical frequencies, most-used traits, etc.

        Args:
            campaign_id: The ID of the campaign to get statistics for.
            num_top_traits: Number of top traits to include (default 5).

        Returns:
            RollStatistics object with aggregated statistics.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            Routes.CAMPAIGNS_STATISTICS,
            params={"num_top_traits": num_top_traits},
            campaign_id=campaign_id,
        )
