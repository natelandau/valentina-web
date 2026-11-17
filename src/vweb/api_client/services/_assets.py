"""Asset methods shared by every service whose resource owns image assets."""

import mimetypes
from collections.abc import Iterator
from typing import ClassVar

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT
from vweb.api_client.models import Asset, PaginatedResponse
from vweb.api_client.services.base import BaseService


class AssetsMixin(BaseService):
    """Add image asset methods for a parent resource (campaign, book, chapter, character, or user).

    Subclasses set the endpoint templates and the name of the parent-id placeholder
    those templates use.
    """

    _assets_endpoint: ClassVar[str]
    _asset_endpoint: ClassVar[str]
    _asset_upload_endpoint: ClassVar[str]
    _parent_id_param: ClassVar[str]

    def _asset_path(self, endpoint: str, parent_id: str, **kwargs: str) -> str:
        return self._format_endpoint(endpoint, **{self._parent_id_param: parent_id}, **kwargs)

    def get_assets_page(
        self,
        parent_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Asset]:
        """Retrieve a paginated page of assets for the parent resource.

        Args:
            parent_id: The ID of the resource whose assets to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Asset objects and pagination metadata.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._get_paginated_as(
            self._asset_path(self._assets_endpoint, parent_id),
            Asset,
            limit=limit,
            offset=offset,
        )

    def list_all_assets(self, parent_id: str) -> list[Asset]:
        """Retrieve all assets for the parent resource.

        Args:
            parent_id: The ID of the resource whose assets to list.

        Returns:
            A list of all Asset objects.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_assets(parent_id))

    def iter_all_assets(self, parent_id: str, *, limit: int = 100) -> Iterator[Asset]:
        """Iterate through all assets for the parent resource, fetching pages as needed.

        Args:
            parent_id: The ID of the resource whose assets to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Asset objects.
        """
        yield from self._iter_all_pages_as(
            self._asset_path(self._assets_endpoint, parent_id), Asset, limit=limit
        )

    def get_asset(self, parent_id: str, asset_id: str) -> Asset:
        """Retrieve details of a specific asset including its URL and metadata.

        Args:
            parent_id: The ID of the resource that owns the asset.
            asset_id: The ID of the asset to retrieve.

        Returns:
            The Asset object with full details.

        Raises:
            NotFoundError: If the asset does not exist.
            AuthorizationError: If you don't have access.
        """
        response = self._get(self._asset_path(self._asset_endpoint, parent_id, asset_id=asset_id))
        return Asset.model_validate(response.json())

    def delete_asset(self, parent_id: str, asset_id: str) -> None:
        """Delete an asset. The file is permanently removed and this cannot be undone.

        Args:
            parent_id: The ID of the resource that owns the asset.
            asset_id: The ID of the asset to delete.

        Raises:
            NotFoundError: If the asset does not exist or belongs to a different resource.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(self._asset_path(self._asset_endpoint, parent_id, asset_id=asset_id))

    def upload_asset(
        self,
        parent_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> Asset:
        """Upload a new image asset to S3 storage and attach it to the parent resource.

        Only PNG, JPEG, GIF, and WEBP files are accepted. Any other upload, or an image
        over 24 megapixels (width x height), is rejected with 400 Bad Request. The API
        detects the stored ``mime_type`` from the file's bytes and ignores
        ``content_type``, so uploaded assets always have ``asset_type == "image"``.

        Args:
            parent_id: The ID of the resource to upload the asset for.
            filename: The original filename of the asset.
            content: The raw bytes of the file to upload.
            content_type: The MIME type of the file. If not provided, inferred from filename.

        Returns:
            The created Asset object with the public URL and metadata.

        Raises:
            NotFoundError: If the parent resource does not exist.
            AuthorizationError: If you don't have appropriate access.
            ValidationError: If the file is invalid or exceeds size limits.
        """
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        response = self._post_file(
            self._asset_path(self._asset_upload_endpoint, parent_id),
            file=(filename, content, content_type),
        )
        return Asset.model_validate(response.json())
