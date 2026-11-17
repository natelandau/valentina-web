"""Asset methods shared by every service whose resource owns image assets."""

from collections.abc import Iterator
from typing import Any, ClassVar, NamedTuple

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT
from vweb.api_client.models import Asset, PaginatedResponse
from vweb.api_client.routes import RouteSpec
from vweb.api_client.services.base import BaseService


class AssetRoutes(NamedTuple):
    """The asset routes of one parent resource."""

    page: RouteSpec[Asset]
    get: RouteSpec[Asset]
    delete: RouteSpec[Any]
    upload: RouteSpec[Asset]


class AssetsMixin(BaseService):
    """Add image asset methods for a parent resource (campaign, book, chapter, character, or user).

    Subclasses set the parent's asset routes and the name of the parent-id placeholder
    those routes use.
    """

    _asset_routes: ClassVar[AssetRoutes]
    _parent_id_param: ClassVar[str]

    def _asset_parent(self, parent_id: str) -> dict[str, str]:
        return {self._parent_id_param: parent_id}

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
        return self._page(
            self._asset_routes.page,
            limit=limit,
            offset=offset,
            path_ids=self._asset_parent(parent_id),
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
        return self._list_all(self._asset_routes.page, path_ids=self._asset_parent(parent_id))

    def iter_all_assets(self, parent_id: str, *, limit: int = 100) -> Iterator[Asset]:
        """Iterate through all assets for the parent resource, fetching pages as needed.

        Args:
            parent_id: The ID of the resource whose assets to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Asset objects.
        """
        yield from self._iter(
            self._asset_routes.page, limit=limit, path_ids=self._asset_parent(parent_id)
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
        return self._call(
            self._asset_routes.get, asset_id=asset_id, path_ids=self._asset_parent(parent_id)
        )

    def delete_asset(self, parent_id: str, asset_id: str) -> None:
        """Delete an asset. The file is permanently removed and this cannot be undone.

        Args:
            parent_id: The ID of the resource that owns the asset.
            asset_id: The ID of the asset to delete.

        Raises:
            NotFoundError: If the asset does not exist or belongs to a different resource.
            AuthorizationError: If you don't have appropriate access.
        """
        self._send(
            self._asset_routes.delete, asset_id=asset_id, path_ids=self._asset_parent(parent_id)
        )

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
        return self._call(
            self._asset_routes.upload,
            file=(filename, content, content_type),
            path_ids=self._asset_parent(parent_id),
        )
