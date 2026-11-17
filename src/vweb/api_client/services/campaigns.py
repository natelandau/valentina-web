"""Service for interacting with the Campaigns API."""

import mimetypes
from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    Asset,
    Campaign,
    CampaignCreate,
    CampaignUpdate,
    Note,
    NoteCreate,
    NoteUpdate,
    PaginatedResponse,
    RollStatistics,
)
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class CampaignsService(BaseService):
    """Service for managing campaigns within a company in the Valentina API.

    This service is scoped to a specific company at initialization time.
    All methods operate within that context.

    Provides methods to create, retrieve, update, and delete campaigns,
    as well as access campaign statistics, assets, and notes.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.

    Example:
        with VClient() as client:
            campaigns = client.campaigns("company_id")
            all_campaigns = campaigns.list_all()
            campaign = campaigns.get("campaign_id")
    """

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CAMPAIGNS),
            Campaign,
            limit=limit,
            offset=offset,
        )

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
        yield from self._iter_all_pages_as(
            self._format_endpoint(Endpoints.CAMPAIGNS),
            Campaign,
            limit=limit,
        )

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
        response = self._get(self._format_endpoint(Endpoints.CAMPAIGN, campaign_id=campaign_id))
        return Campaign.model_validate(response.json())

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
        response = self._post(
            self._format_endpoint(Endpoints.CAMPAIGNS),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Campaign.model_validate(response.json())

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
        response = self._patch(
            self._format_endpoint(Endpoints.CAMPAIGN, campaign_id=campaign_id),
            json=payload,
        )
        return Campaign.model_validate(response.json())

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
        self._delete(self._format_endpoint(Endpoints.CAMPAIGN, campaign_id=campaign_id))

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
        response = self._get(
            self._format_endpoint(Endpoints.CAMPAIGN_STATISTICS, campaign_id=campaign_id),
            params={"num_top_traits": num_top_traits},
        )
        return RollStatistics.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Asset Methods
    # -------------------------------------------------------------------------

    def get_assets_page(
        self,
        campaign_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Asset]:
        """Retrieve a paginated page of assets for a campaign.

        Args:
            campaign_id: The ID of the campaign whose assets to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Asset objects and pagination metadata.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CAMPAIGN_ASSETS, campaign_id=campaign_id),
            Asset,
            limit=limit,
            offset=offset,
        )

    def list_all_assets(
        self,
        campaign_id: str,
    ) -> list[Asset]:
        """Retrieve all assets for a campaign.

        Automatically paginates through all results. Use `get_assets_page()` for paginated
        access or `iter_all_assets()` for memory-efficient streaming of large datasets.

        Args:
            campaign_id: The ID of the campaign whose assets to list.

        Returns:
            A list of all Asset objects.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_assets(campaign_id))

    def iter_all_assets(
        self,
        campaign_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Asset]:
        """Iterate through all assets for a campaign.

        Yields individual assets, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            campaign_id: The ID of the campaign whose assets to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Asset objects.

        Example:
            for asset in campaigns.iter_all_assets("campaign_id"):
                print(asset.original_filename)
        """
        yield from self._iter_all_pages_as(
            self._format_endpoint(Endpoints.CAMPAIGN_ASSETS, campaign_id=campaign_id),
            Asset,
            limit=limit,
        )

    def get_asset(
        self,
        campaign_id: str,
        asset_id: str,
    ) -> Asset:
        """Retrieve details of a specific asset including its URL and metadata.

        Args:
            campaign_id: The ID of the campaign that owns the asset.
            asset_id: The ID of the asset to retrieve.

        Returns:
            The Asset object with full details.

        Raises:
            NotFoundError: If the asset does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(
            self._format_endpoint(
                Endpoints.CAMPAIGN_ASSET, campaign_id=campaign_id, asset_id=asset_id
            )
        )
        return Asset.model_validate(response.json())

    def delete_asset(
        self,
        campaign_id: str,
        asset_id: str,
    ) -> None:
        """Delete an asset from a campaign.

        This action cannot be undone. The asset file is permanently removed.

        Args:
            campaign_id: The ID of the campaign that owns the asset.
            asset_id: The ID of the asset to delete.

        Raises:
            NotFoundError: If the asset does not exist or belongs to a different campaign.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(
            self._format_endpoint(
                Endpoints.CAMPAIGN_ASSET, campaign_id=campaign_id, asset_id=asset_id
            )
        )

    def upload_asset(
        self,
        campaign_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> Asset:
        """Upload a new image asset for a campaign.

        Uploads an image to S3 storage and associates it with the campaign.

        Only image files are accepted: PNG, JPEG, GIF, and WEBP. Any other
        upload (documents, audio, video, archives, SVG, or a non-image payload
        mislabeled as an image) is rejected with 400 Bad Request, as are
        images over 24 megapixels (width x height). The stored
        ``mime_type`` is detected from the file's bytes; the ``content_type``
        argument is ignored server-side and cannot change or bypass the stored
        type. Uploaded assets therefore always have ``asset_type == "image"``.

        Args:
            campaign_id: The ID of the campaign to upload the asset for.
            filename: The original filename of the asset.
            content: The raw bytes of the file to upload.
            content_type: The MIME type of the file. If not provided, inferred from filename.

        Returns:
            The created Asset object with the public URL and metadata.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have appropriate access.
            ValidationError: If the file is invalid or exceeds size limits.
        """
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        response = self._post_file(
            self._format_endpoint(Endpoints.CAMPAIGN_ASSET_UPLOAD, campaign_id=campaign_id),
            file=(filename, content, content_type),
        )
        return Asset.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Notes Methods
    # -------------------------------------------------------------------------

    def get_notes_page(
        self,
        campaign_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Note]:
        """Retrieve a paginated page of notes for a campaign.

        Args:
            campaign_id: The ID of the campaign whose notes to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Note objects and pagination metadata.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CAMPAIGN_NOTES, campaign_id=campaign_id),
            Note,
            limit=limit,
            offset=offset,
        )

    def list_all_notes(
        self,
        campaign_id: str,
    ) -> list[Note]:
        """Retrieve all notes for a campaign.

        Automatically paginates through all results. Use `get_notes_page()` for paginated
        access or `iter_all_notes()` for memory-efficient streaming of large datasets.

        Args:
            campaign_id: The ID of the campaign whose notes to list.

        Returns:
            A list of all Note objects.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_notes(campaign_id))

    def iter_all_notes(
        self,
        campaign_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Note]:
        """Iterate through all notes for a campaign.

        Yields individual notes, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            campaign_id: The ID of the campaign whose notes to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Note objects.

        Example:
            for note in campaigns.iter_all_notes("campaign_id"):
                print(note.title)
        """
        yield from self._iter_all_pages_as(
            self._format_endpoint(Endpoints.CAMPAIGN_NOTES, campaign_id=campaign_id),
            Note,
            limit=limit,
        )

    def get_note(
        self,
        campaign_id: str,
        note_id: str,
    ) -> Note:
        """Retrieve a specific note including its content and metadata.

        Args:
            campaign_id: The ID of the campaign that owns the note.
            note_id: The ID of the note to retrieve.

        Returns:
            The Note object with full details.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(
            self._format_endpoint(Endpoints.CAMPAIGN_NOTE, campaign_id=campaign_id, note_id=note_id)
        )
        return Note.model_validate(response.json())

    def create_note(
        self,
        campaign_id: str,
        request: NoteCreate | None = None,
        **kwargs,
    ) -> Note:
        """Create a new note for a campaign.

        Notes support markdown formatting for rich text content.

        Args:
            campaign_id: The ID of the campaign to create the note for.
            request: A NoteCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteCreate if request is not provided.
                Accepts: title (str, required), content (str, required).

        Returns:
            The newly created Note object.

        Raises:
            NotFoundError: If the campaign does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.CAMPAIGN_NOTES, campaign_id=campaign_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def update_note(
        self,
        campaign_id: str,
        note_id: str,
        request: NoteUpdate | None = None,
        **kwargs,
    ) -> Note:
        """Modify a note's content.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            campaign_id: The ID of the campaign that owns the note.
            note_id: The ID of the note to update.
            request: A NoteUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteUpdate if request is not provided.
                Accepts: title (str | None), content (str | None).

        Returns:
            The updated Note object.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteUpdate, **kwargs)
        response = self._patch(
            self._format_endpoint(
                Endpoints.CAMPAIGN_NOTE, campaign_id=campaign_id, note_id=note_id
            ),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def delete_note(
        self,
        campaign_id: str,
        note_id: str,
    ) -> None:
        """Remove a note from a campaign.

        This action cannot be undone.

        Args:
            campaign_id: The ID of the campaign that owns the note.
            note_id: The ID of the note to delete.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(
            self._format_endpoint(Endpoints.CAMPAIGN_NOTE, campaign_id=campaign_id, note_id=note_id)
        )
