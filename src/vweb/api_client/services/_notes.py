"""Notes methods shared by every service whose resource owns notes."""

from collections.abc import Iterator
from typing import Any, ClassVar, NamedTuple

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT
from vweb.api_client.models import Note, NoteCreate, NoteUpdate, PaginatedResponse
from vweb.api_client.routes import RouteSpec
from vweb.api_client.services.base import BaseService


class NoteRoutes(NamedTuple):
    """The note routes of one parent resource."""

    page: RouteSpec[Note]
    get: RouteSpec[Note]
    create: RouteSpec[Note]
    update: RouteSpec[Note]
    delete: RouteSpec[Any]


class NotesMixin(BaseService):
    """Add note CRUD for a parent resource (campaign, book, chapter, character, or user).

    Subclasses set the parent's note routes and the name of the parent-id placeholder
    those routes use.
    """

    _note_routes: ClassVar[NoteRoutes]
    _parent_id_param: ClassVar[str]

    def _note_parent(self, parent_id: str) -> dict[str, str]:
        return {self._parent_id_param: parent_id}

    def get_notes_page(
        self,
        parent_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Note]:
        """Retrieve a paginated page of notes for the parent resource.

        Args:
            parent_id: The ID of the resource whose notes to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Note objects and pagination metadata.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._page(
            self._note_routes.page,
            limit=limit,
            offset=offset,
            path_ids=self._note_parent(parent_id),
        )

    def list_all_notes(self, parent_id: str) -> list[Note]:
        """Retrieve all notes for the parent resource.

        Args:
            parent_id: The ID of the resource whose notes to list.

        Returns:
            A list of all Note objects.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_notes(parent_id))

    def iter_all_notes(self, parent_id: str, *, limit: int = 100) -> Iterator[Note]:
        """Iterate through all notes for the parent resource, fetching pages as needed.

        Args:
            parent_id: The ID of the resource whose notes to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Note objects.
        """
        yield from self._iter(
            self._note_routes.page, limit=limit, path_ids=self._note_parent(parent_id)
        )

    def get_note(self, parent_id: str, note_id: str) -> Note:
        """Retrieve a specific note including its content and metadata.

        Args:
            parent_id: The ID of the resource that owns the note.
            note_id: The ID of the note to retrieve.

        Returns:
            The Note object with full details.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            self._note_routes.get, note_id=note_id, path_ids=self._note_parent(parent_id)
        )

    def create_note(
        self,
        parent_id: str,
        request: NoteCreate | None = None,
        **kwargs,
    ) -> Note:
        """Create a new markdown note for the parent resource.

        Args:
            parent_id: The ID of the resource to create the note for.
            request: A NoteCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteCreate if request is not provided.
                Accepts: title (str, required), content (str, required).

        Returns:
            The newly created Note object.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteCreate, **kwargs)
        return self._call(
            self._note_routes.create,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            path_ids=self._note_parent(parent_id),
        )

    def update_note(
        self,
        parent_id: str,
        note_id: str,
        request: NoteUpdate | None = None,
        **kwargs,
    ) -> Note:
        """Modify a note's content; omitted fields remain unchanged.

        Args:
            parent_id: The ID of the resource that owns the note.
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
        return self._call(
            self._note_routes.update,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            note_id=note_id,
            path_ids=self._note_parent(parent_id),
        )

    def delete_note(self, parent_id: str, note_id: str) -> None:
        """Remove a note. This action cannot be undone.

        Args:
            parent_id: The ID of the resource that owns the note.
            note_id: The ID of the note to delete.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._send(self._note_routes.delete, note_id=note_id, path_ids=self._note_parent(parent_id))
