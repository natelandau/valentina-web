"""Service for interacting with the Campaign Books Chapters API."""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, ChapterInclude
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    CampaignChapter,
    CampaignChapterDetail,
    ChapterCreate,
    ChapterUpdate,
    PaginatedResponse,
    _ChapterRenumber,
)
from vweb.api_client.services._assets import AssetsMixin
from vweb.api_client.services._notes import NotesMixin

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class ChaptersService(NotesMixin, AssetsMixin):
    """Service for managing campaign book chapters within a campaign book in the Valentina API.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.
    """

    _parent_id_param = "chapter_id"
    _notes_endpoint = Endpoints.BOOK_CHAPTER_NOTES
    _note_endpoint = Endpoints.BOOK_CHAPTER_NOTE
    _assets_endpoint = Endpoints.BOOK_CHAPTER_ASSETS
    _asset_endpoint = Endpoints.BOOK_CHAPTER_ASSET
    _asset_upload_endpoint = Endpoints.BOOK_CHAPTER_ASSET_UPLOAD

    def __init__(
        self,
        client: "VClient",
        company_id: str,
        campaign_id: str,
        book_id: str,
        on_behalf_of: str,
    ) -> None:
        """Initialize the service scoped to a specific company, campaign, and book.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            campaign_id: The ID of the campaign to operate within.
            book_id: The ID of the book to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(
            client,
            on_behalf_of=on_behalf_of,
            company_id=company_id,
            campaign_id=campaign_id,
            book_id=book_id,
        )

    # -------------------------------------------------------------------------
    # Chapter CRUD Methods
    # -------------------------------------------------------------------------

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[CampaignChapter]:
        """Retrieve a paginated page of campaign book chapters."""
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BOOK_CHAPTERS),
            CampaignChapter,
            limit=limit,
            offset=offset,
        )

    def list_all(self) -> list[CampaignChapter]:
        """Retrieve all campaign book chapters."""
        return list(self.iter_all())

    def iter_all(
        self,
        *,
        limit: int = 100,
    ) -> Iterator[CampaignChapter]:
        """Iterate through all campaign book chapters."""
        yield from self._iter_all_pages_as(
            self._format_endpoint(Endpoints.BOOK_CHAPTERS),
            CampaignChapter,
            limit=limit,
        )

    def get(
        self,
        chapter_id: str,
        *,
        include: Sequence[ChapterInclude] | None = None,
    ) -> CampaignChapterDetail:
        """Retrieve detailed information about a specific campaign book chapter.

        Fetches the chapter and optionally embeds child resources directly in the
        response, avoiding follow-up requests.

        Args:
            chapter_id: The ID of the chapter to retrieve.
            include: Child resources to embed in the response. Valid values are
                ``"notes"`` and ``"assets"``.

        Returns:
            The CampaignChapterDetail object with full details and any requested embeds.

        Raises:
            NotFoundError: If the chapter does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(
            self._format_endpoint(Endpoints.BOOK_CHAPTER, chapter_id=chapter_id),
            params=self._build_params(include=list(include) if include else None),
        )
        return CampaignChapterDetail.model_validate(response.json())

    def create(
        self,
        request: ChapterCreate | None = None,
        **kwargs,
    ) -> CampaignChapter:
        """Create a new campaign book chapter.

        Args:
            request: A ChapterCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for ChapterCreate if request is not provided.
                Accepts: name (str, required), description (str | None), character_ids (list[str] | None).
        """
        body = request if request is not None else ChapterCreate(**kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.BOOK_CHAPTERS),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CampaignChapter.model_validate(response.json())

    def update(
        self,
        chapter_id: str,
        request: ChapterUpdate | None = None,
        **kwargs,
    ) -> CampaignChapter:
        """Update a campaign book chapter.

        Args:
            chapter_id: The ID of the chapter to update.
            request: A ChapterUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for ChapterUpdate if request is not provided.
                Accepts: name (str | None), description (str | None), character_ids (list[str] | None).
        """
        body = request if request is not None else ChapterUpdate(**kwargs)
        response = self._patch(
            self._format_endpoint(Endpoints.BOOK_CHAPTER, chapter_id=chapter_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CampaignChapter.model_validate(response.json())

    def delete(self, chapter_id: str) -> None:
        """Delete a campaign book chapter."""
        self._delete(self._format_endpoint(Endpoints.BOOK_CHAPTER, chapter_id=chapter_id))

    def renumber(self, chapter_id: str, number: int) -> CampaignChapter:
        """Renumber a campaign book chapter."""
        response = self._put(
            self._format_endpoint(Endpoints.BOOK_CHAPTER_NUMBER, chapter_id=chapter_id),
            json=_ChapterRenumber(number=number).model_dump(
                exclude_none=True, exclude_unset=True, mode="json"
            ),
        )
        return CampaignChapter.model_validate(response.json())
