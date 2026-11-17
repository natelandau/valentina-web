"""Service for interacting with the Campaign Books API."""

import mimetypes
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, BookInclude
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    Asset,
    BookCreate,
    BookUpdate,
    CampaignBook,
    CampaignBookDetail,
    Note,
    NoteCreate,
    NoteUpdate,
    PaginatedResponse,
    _BookRenumber,
)
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class BooksService(BaseService):
    """Service for managing campaign books within a campaign in the Valentina API.

    This service is scoped to a specific company and campaign at initialization time.
    All methods operate within that context.

    Provides methods to create, retrieve, update, and delete campaign books,
    as well as access book notes and assets.

    Requests return 403 (``AuthorizationError``) when the ``on_behalf_of`` user is
    UNAPPROVED or DEACTIVATED.

    Example:
        >>> with VClient() as client:
        ...     books = client.books("company_id", "campaign_id")
        ...     all_books = books.list_all()
        ...     book = books.get("book_id")
    """

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
        super().__init__(client)
        self._company_id = company_id
        self._campaign_id = campaign_id
        self._on_behalf_of = on_behalf_of

    def _format_endpoint(self, endpoint: str, **kwargs: str) -> str:
        """Format an endpoint with the scoped company_id and campaign_id plus any extra params."""
        return endpoint.format(
            company_id=self._company_id,
            campaign_id=self._campaign_id,
            **kwargs,
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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOKS),
            CampaignBook,
            limit=limit,
            offset=offset,
        )

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
            >>> for book in books.iter_all():
            ...     print(book.name)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOKS),
            limit=limit,
        ):
            yield CampaignBook.model_validate(item)

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
        response = self._get(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOK, book_id=book_id),
            params=self._build_params(include=list(include) if include else None),
        )
        return CampaignBookDetail.model_validate(response.json())

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
        response = self._post(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOKS),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CampaignBook.model_validate(response.json())

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
        response = self._patch(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOK, book_id=book_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CampaignBook.model_validate(response.json())

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
        self._delete(self._format_endpoint(Endpoints.CAMPAIGN_BOOK, book_id=book_id))

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
        response = self._put(
            self._format_endpoint(Endpoints.CAMPAIGN_BOOK_NUMBER, book_id=book_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CampaignBook.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Notes Methods
    # -------------------------------------------------------------------------

    def get_notes_page(
        self,
        book_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Note]:
        """Retrieve a paginated page of notes for a book.

        Args:
            book_id: The ID of the book whose notes to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Note objects and pagination metadata.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BOOK_NOTES, book_id=book_id),
            Note,
            limit=limit,
            offset=offset,
        )

    def list_all_notes(
        self,
        book_id: str,
    ) -> list[Note]:
        """Retrieve all notes for a book.

        Automatically paginates through all results. Use `get_notes_page()` for paginated
        access or `iter_all_notes()` for memory-efficient streaming of large datasets.

        Args:
            book_id: The ID of the book whose notes to list.

        Returns:
            A list of all Note objects.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_notes(book_id))

    def iter_all_notes(
        self,
        book_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Note]:
        """Iterate through all notes for a book.

        Yields individual notes, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            book_id: The ID of the book whose notes to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Note objects.

        Example:
            >>> for note in books.iter_all_notes("book_id"):
            ...     print(note.title)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.BOOK_NOTES, book_id=book_id),
            limit=limit,
        ):
            yield Note.model_validate(item)

    def get_note(
        self,
        book_id: str,
        note_id: str,
    ) -> Note:
        """Retrieve a specific note including its content and metadata.

        Args:
            book_id: The ID of the book that owns the note.
            note_id: The ID of the note to retrieve.

        Returns:
            The Note object with full details.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(
            self._format_endpoint(Endpoints.BOOK_NOTE, book_id=book_id, note_id=note_id)
        )
        return Note.model_validate(response.json())

    def create_note(
        self,
        book_id: str,
        request: NoteCreate | None = None,
        **kwargs,
    ) -> Note:
        """Create a new note for a book.

        Notes support markdown formatting for rich text content.

        Args:
            book_id: The ID of the book to create the note for.
            request: A NoteCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteCreate if request is not provided.
                Accepts: title (str, required), content (str, required).

        Returns:
            The newly created Note object.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.BOOK_NOTES, book_id=book_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def update_note(
        self,
        book_id: str,
        note_id: str,
        request: NoteUpdate | None = None,
        **kwargs,
    ) -> Note:
        """Modify a note's content.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            book_id: The ID of the book that owns the note.
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
            self._format_endpoint(Endpoints.BOOK_NOTE, book_id=book_id, note_id=note_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def delete_note(
        self,
        book_id: str,
        note_id: str,
    ) -> None:
        """Remove a note from a book.

        This action cannot be undone.

        Args:
            book_id: The ID of the book that owns the note.
            note_id: The ID of the note to delete.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(self._format_endpoint(Endpoints.BOOK_NOTE, book_id=book_id, note_id=note_id))

    # -------------------------------------------------------------------------
    # Asset Methods
    # -------------------------------------------------------------------------

    def get_assets_page(
        self,
        book_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Asset]:
        """Retrieve a paginated page of assets for a book.

        Args:
            book_id: The ID of the book whose assets to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Asset objects and pagination metadata.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BOOK_ASSETS, book_id=book_id),
            Asset,
            limit=limit,
            offset=offset,
        )

    def list_all_assets(
        self,
        book_id: str,
    ) -> list[Asset]:
        """Retrieve all assets for a book.

        Automatically paginates through all results. Use `get_assets_page()` for paginated
        access or `iter_all_assets()` for memory-efficient streaming of large datasets.

        Args:
            book_id: The ID of the book whose assets to list.

        Returns:
            A list of all Asset objects.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_assets(book_id))

    def iter_all_assets(
        self,
        book_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Asset]:
        """Iterate through all assets for a book.

        Yields individual assets, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            book_id: The ID of the book whose assets to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Asset objects.

        Example:
            >>> for asset in books.iter_all_assets("book_id"):
            ...     print(asset.original_filename)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.BOOK_ASSETS, book_id=book_id),
            limit=limit,
        ):
            yield Asset.model_validate(item)

    def get_asset(
        self,
        book_id: str,
        asset_id: str,
    ) -> Asset:
        """Retrieve details of a specific asset including its URL and metadata.

        Args:
            book_id: The ID of the book that owns the asset.
            asset_id: The ID of the asset to retrieve.

        Returns:
            The Asset object with full details.

        Raises:
            NotFoundError: If the asset does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(
            self._format_endpoint(Endpoints.BOOK_ASSET, book_id=book_id, asset_id=asset_id)
        )
        return Asset.model_validate(response.json())

    def upload_asset(
        self,
        book_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> Asset:
        """Upload a new image asset for a book.

        Uploads an image to S3 storage and associates it with the book.

        Only image files are accepted: PNG, JPEG, GIF, and WEBP. Any other
        upload (documents, audio, video, archives, SVG, or a non-image payload
        mislabeled as an image) is rejected with 400 Bad Request, as are
        images over 24 megapixels (width x height). The stored
        ``mime_type`` is detected from the file's bytes; the ``content_type``
        argument is ignored server-side and cannot change or bypass the stored
        type. Uploaded assets therefore always have ``asset_type == "image"``.

        Args:
            book_id: The ID of the book to upload the asset for.
            filename: The original filename of the asset.
            content: The raw bytes of the file to upload.
            content_type: The MIME type of the file. If not provided, inferred from filename.

        Returns:
            The created Asset object with the public URL and metadata.

        Raises:
            NotFoundError: If the book does not exist.
            AuthorizationError: If you don't have appropriate access.
            ValidationError: If the file is invalid or exceeds size limits.
        """
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        response = self._post_file(
            self._format_endpoint(Endpoints.BOOK_ASSET_UPLOAD, book_id=book_id),
            file=(filename, content, content_type),
        )
        return Asset.model_validate(response.json())

    def delete_asset(
        self,
        book_id: str,
        asset_id: str,
    ) -> None:
        """Delete an asset from a book.

        This action cannot be undone. The asset file is permanently removed.

        Args:
            book_id: The ID of the book that owns the asset.
            asset_id: The ID of the asset to delete.

        Raises:
            NotFoundError: If the asset does not exist or belongs to a different book.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(
            self._format_endpoint(Endpoints.BOOK_ASSET, book_id=book_id, asset_id=asset_id)
        )
