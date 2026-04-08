"""Shared validation helpers for image upload and delete handlers.

Book, chapter, and character image routes run the same validation ladder
(file presence, MIME check, size check, vclient call, flash) and the same
delete-with-flash pattern. These helpers centralize that work so each view
only needs to handle authentication, lookups, and re-rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from flask import flash
from vclient.exceptions import APIError

from vweb.constants import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE

if TYPE_CHECKING:
    from vclient.models import Asset
    from werkzeug.datastructures import FileStorage


MAX_IMAGE_SIZE_MB: int = MAX_IMAGE_SIZE // (1024 * 1024)


class AssetService(Protocol):
    """Structural type of any vclient sync service that manages image assets.

    The parent-id parameter is positional-only because concrete sync services
    name it differently (``book_id``, ``chapter_id``, ``character_id``), and
    structural matching on parameter names would otherwise fail.
    """

    def upload_asset(
        self,
        parent_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = ...,
        /,
    ) -> Asset:
        """Upload a new image asset for the given parent resource."""

    def delete_asset(self, parent_id: str, asset_id: str, /) -> None:
        """Delete an image asset owned by the given parent resource."""

    def list_all_assets(self, parent_id: str, /) -> list[Asset]:
        """List all image assets for the given parent resource."""


def handle_image_upload(
    *,
    svc: AssetService,
    parent_id: str,
    file: FileStorage | None,
) -> Asset | None:
    """Validate and persist an uploaded image, flashing the outcome.

    Returns the newly-created Asset on success so callers can append it to a
    pre-fetched asset list without re-querying — ``list_all_assets`` has been
    observed to return stale results immediately after an upload.
    """
    if file is None or not file.filename:
        flash("No image selected.", "error")
        return None
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        flash("Invalid image type. Allowed: JPEG, PNG, WebP, GIF.", "error")
        return None

    content = file.read()
    if len(content) > MAX_IMAGE_SIZE:
        flash(f"Image is too large (max {MAX_IMAGE_SIZE_MB} MB).", "error")
        return None

    try:
        asset = svc.upload_asset(parent_id, file.filename, content, file.content_type)
    except APIError:
        flash("Failed to upload image. Please try again.", "error")
        return None

    flash("Image uploaded successfully.", "success")
    return asset


def upload_and_append_asset(
    *,
    svc: AssetService,
    parent_id: str,
    file: FileStorage | None,
) -> list[Asset]:
    """Snapshot the current asset list, upload, and return the combined list.

    ``list_all_assets`` returns stale data immediately after an upload, so the
    existing assets must be captured *before* calling ``upload_asset``.
    """
    existing = svc.list_all_assets(parent_id)
    new_asset = handle_image_upload(svc=svc, parent_id=parent_id, file=file)
    return [*existing, new_asset] if new_asset is not None else existing


def handle_image_delete(
    *,
    svc: AssetService,
    parent_id: str,
    asset_id: str,
) -> None:
    """Delete an image asset via ``svc.delete_asset`` and flash the outcome."""
    try:
        svc.delete_asset(parent_id, asset_id)
    except APIError:
        flash("Failed to delete image. Please try again.", "error")
        return

    flash("Image deleted.", "success")
