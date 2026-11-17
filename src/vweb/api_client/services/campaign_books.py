"""Service for interacting with the Campaign Books API."""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, BookInclude
from vweb.api_client.models import (
    BookCreate,
    BookUpdate,
    CampaignBook,
    CampaignBookDetail,
    PaginatedResponse,
    _BookRenumber,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services._assets import AssetRoutes, AssetsMixin
from vweb.api_client.services._notes import NoteRoutes, NotesMixin

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class BooksService(NotesMixin, AssetsMixin):
    """Service for managing campaign books within a campaign in the Valentina API.

    This service is scoped to a specific company and campaign at initialization time.
    All methods operate within that context.

    Provides methods to create, retrieve, update, and delete campaign books,
    as well as access book notes and assets.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            books = client.books("company_id", "campaign_id")
            all_books = books.list_all()
            book = books.get("book_id")
    """

    _parent_id_param = "book_id"
    _note_routes = NoteRoutes(
        page=Routes.BOOKS_NOTES_LIST,
        get=Routes.BOOKS_NOTES_GET,
        create=Routes.BOOKS_NOTES_CREATE,
        update=Routes.BOOKS_NOTES_UPDATE,
        delete=Routes.BOOKS_NOTES_DELETE,
    )
    _asset_routes = AssetRoutes(
        page=Routes.BOOKS_ASSETS_LIST,
        get=Routes.BOOKS_ASSETS_GET,
        delete=Routes.BOOKS_ASSETS_DELETE,
        upload=Routes.BOOKS_ASSETS_UPLOAD,
    )

    def __init__(
        self,
        client: "VClient",
        company_id: str,
        campaign_id: str,
        on_behalf_of: str,
    ) -> None:
        """Initialize the service scoped to a specific company and campaign.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            campaign_id: The ID of the campaign to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(
            client, on_behalf_of=on_behalf_of, company_id=company_id, campaign_id=campaign_id
        )

    # -------------------------------------------------------------------------
    # Book CRUD Methods
    # -------------------------------------------------------------------------

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[CampaignBook]:
        """Retrieve a paginated page of campaign books.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing CampaignBook objects and pagination metadata.
        """
        return self._page(Routes.BOOKS_LIST, limit=limit, offset=offset)

    def list_all(self) -> list[CampaignBook]:
        """Retrieve all campaign books.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Returns:
            A list of all CampaignBook objects.
        """
        return list(self.iter_all())

    def iter_all(
        self,
        *,
        limit: int = 100,
    ) -> Iterator[CampaignBook]:
        """Iterate through all campaign books.

        Yields individual books, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual CampaignBook objects.

        Example:
            for book in books.iter_all():
                print(book.name)
        """
        yield from self._iter(Routes.BOOKS_LIST, limit=limit)

    def get(
        self,
        book_id: str,
        *,
        include: Sequence[BookInclude] | None = None,
    ) -> CampaignBookDetail:
        """Retrieve detailed information about a specific campaign book.

        Fetches the book and optionally embeds child resources directly in the
        response, avoiding follow-up requests.

        Args:
            book_id: The ID of the book to retrieve.
            include: Child resources to embed in the response. Valid values are
                ``"chapters"``, ``"notes"``, and ``"assets"``.

        Returns:
            The CampaignBookDetail object with full details and any requested embeds.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            Routes.BOOKS_GET,
            params=self._build_params(include=list(include) if include else None),
            book_id=book_id,
        )

    def create(
        self,
        request: BookCreate | None = None,
        **kwargs,
    ) -> CampaignBook:
        """Create a new campaign book.

        Args:
            request: A BookCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for BookCreate if request is not provided.
                Accepts: name (str, required), description (str | None).

        Returns:
            The newly created CampaignBook object.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            AuthorizationError: If you don't have book management privileges.
        """
        body = request if request is not None else self._validate_request(BookCreate, **kwargs)
        return self._call(
            Routes.BOOKS_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

    def update(
        self,
        book_id: str,
        request: BookUpdate | None = None,
        **kwargs,
    ) -> CampaignBook:
        """Modify a campaign book's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            book_id: The ID of the book to update.
            request: A BookUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for BookUpdate if request is not provided.
                Accepts: name (str | None), description (str | None).

        Returns:
            The updated CampaignBook object.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have book management privileges.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(BookUpdate, **kwargs)
        return self._call(
            Routes.BOOKS_UPDATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            book_id=book_id,
        )

    def delete(self, book_id: str) -> None:
        """Remove a campaign book from the system.

        Associated notes and assets will no longer be accessible.
        This action cannot be undone.

        Args:
            book_id: The ID of the book to delete.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have book management privileges.
        """
        self._send(Routes.BOOKS_DELETE, book_id=book_id)

    def renumber(self, book_id: str, number: int) -> CampaignBook:
        """Change the book's position number within the campaign.

        Renumbering a book will shift other books as needed to maintain
        a contiguous sequence.

        Args:
            book_id: The ID of the book to renumber.
            number: New book number (must be >= 1).

        Returns:
            The updated CampaignBook object with the new number.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have book management privileges.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = self._validate_request(_BookRenumber, number=number)
        return self._call(
            Routes.BOOKS_RENUMBER,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            book_id=book_id,
        )
