"""Service for interacting with the Campaign Books Chapters API."""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, ChapterInclude
from vweb.api_client.models import (
    CampaignChapter,
    CampaignChapterDetail,
    ChapterCreate,
    ChapterUpdate,
    PaginatedResponse,
    _ChapterRenumber,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services._assets import AssetRoutes, AssetsMixin
from vweb.api_client.services._notes import NoteRoutes, NotesMixin

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class ChaptersService(NotesMixin, AssetsMixin):
    """Service for managing campaign book chapters within a campaign book in the Valentina API.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.
    """

    _parent_id_param = "chapter_id"
    _note_routes = NoteRoutes(
        page=Routes.CHAPTERS_NOTES_LIST,
        get=Routes.CHAPTERS_NOTES_GET,
        create=Routes.CHAPTERS_NOTES_CREATE,
        update=Routes.CHAPTERS_NOTES_UPDATE,
        delete=Routes.CHAPTERS_NOTES_DELETE,
    )
    _asset_routes = AssetRoutes(
        page=Routes.CHAPTERS_ASSETS_LIST,
        get=Routes.CHAPTERS_ASSETS_GET,
        delete=Routes.CHAPTERS_ASSETS_DELETE,
        upload=Routes.CHAPTERS_ASSETS_UPLOAD,
    )

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
        return self._page(Routes.CHAPTERS_LIST, limit=limit, offset=offset)

    def list_all(self) -> list[CampaignChapter]:
        """Retrieve all campaign book chapters."""
        return self._list_all(Routes.CHAPTERS_LIST)

    def iter_all(
        self,
        *,
        limit: int = 100,
    ) -> Iterator[CampaignChapter]:
        """Iterate through all campaign book chapters."""
        yield from self._iter(Routes.CHAPTERS_LIST, limit=limit)

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
        return self._call(
            Routes.CHAPTERS_GET,
            params=self._build_params(include=list(include) if include else None),
            chapter_id=chapter_id,
        )

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
        return self._call(
            Routes.CHAPTERS_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

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
        return self._call(
            Routes.CHAPTERS_UPDATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            chapter_id=chapter_id,
        )

    def delete(self, chapter_id: str) -> None:
        """Delete a campaign book chapter."""
        self._send(Routes.CHAPTERS_DELETE, chapter_id=chapter_id)

    def renumber(self, chapter_id: str, number: int) -> CampaignChapter:
        """Renumber a campaign book chapter."""
        return self._call(
            Routes.CHAPTERS_RENUMBER,
            json=_ChapterRenumber(number=number).model_dump(
                exclude_none=True, exclude_unset=True, mode="json"
            ),
            chapter_id=chapter_id,
        )
