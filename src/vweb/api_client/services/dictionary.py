"""Service for interacting with the Dictionary API."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, MAX_REFERENCE_PAGE_LIMIT
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    DictionaryTerm,
    DictionaryTermCreate,
    DictionaryTermUpdate,
    PaginatedResponse,
)
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class DictionaryService(BaseService):
    """Service for interacting with the Dictionary API."""

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str | None = None) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client)
        self._company_id = company_id
        self._on_behalf_of = on_behalf_of

    def _format_endpoint(self, endpoint: str, **kwargs: str) -> str:
        """Format an endpoint with the scoped company_id plus any extra params."""
        return endpoint.format(company_id=self._company_id, **kwargs)

    # -------------------------------------------------------------------------
    # Dictionary Term CRUD Methods
    # -------------------------------------------------------------------------

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        term: str | None = None,
    ) -> PaginatedResponse[DictionaryTerm]:
        """Retrieve a paginated page of dictionary terms."""
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.DICTIONARY_TERMS),
            DictionaryTerm,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(term=term),
        )

    def list_all(self, *, term: str | None = None) -> list[DictionaryTerm]:
        """Retrieve all dictionary terms."""
        return list(self.iter_all(term=term))

    def iter_all(
        self, *, term: str | None = None, limit: int = MAX_REFERENCE_PAGE_LIMIT
    ) -> Iterator[DictionaryTerm]:
        """Iterate through all dictionary terms."""
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.DICTIONARY_TERMS),
            limit=limit,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(term=term),
        ):
            yield DictionaryTerm.model_validate(item)

    def get(self, term_id: str) -> DictionaryTerm:
        """Retrieve a specific dictionary term."""
        response = self._get(self._format_endpoint(Endpoints.DICTIONARY_TERM, term_id=term_id))
        return DictionaryTerm.model_validate(response.json())

    def create(
        self,
        request: DictionaryTermCreate | None = None,
        **kwargs,
    ) -> DictionaryTerm:
        """Create a new dictionary term.

        Args:
            request: A DictionaryTermCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for DictionaryTermCreate if request is not provided.
                Accepts: term (str, required), definition (str | None),
                link (str | None), synonyms (list[str]).
        """
        body = request if request is not None else DictionaryTermCreate(**kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.DICTIONARY_TERMS),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return DictionaryTerm.model_validate(response.json())

    def update(
        self,
        term_id: str,
        request: DictionaryTermUpdate | None = None,
        **kwargs,
    ) -> DictionaryTerm:
        """Update a specific dictionary term.

        Args:
            term_id: The ID of the term to update.
            request: A DictionaryTermUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for DictionaryTermUpdate if request is not provided.
                Accepts: term (str | None), definition (str | None),
                link (str | None), synonyms (list[str] | None).
        """
        body = request if request is not None else DictionaryTermUpdate(**kwargs)
        response = self._patch(
            self._format_endpoint(Endpoints.DICTIONARY_TERM, term_id=term_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return DictionaryTerm.model_validate(response.json())

    def delete(self, term_id: str) -> None:
        """Delete a specific dictionary term."""
        self._delete(self._format_endpoint(Endpoints.DICTIONARY_TERM, term_id=term_id))
