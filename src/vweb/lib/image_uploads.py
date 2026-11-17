"""Shared validation helpers for image upload and delete handlers.

Book, chapter, and character image routes run the same validation ladder
(file presence, MIME check, size check, pixel check, vclient call, flash) and the same
delete-with-flash pattern. These helpers centralize that work so each view
only needs to handle authentication, lookups, and re-rendering.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Protocol

from flask import flash
from PIL import Image

from vweb.api_client.exceptions import APIError
from vweb.constants import (
    ALLOWED_IMAGE_TYPES,
    MAX_AVATAR_SIZE,
    MAX_AVATAR_SIZE_MB,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIZE,
    MAX_IMAGE_SIZE_MB,
)
from vweb.lib.api_errors import api_error_message

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage

    from vweb.api_client.services import AssetsMixin


MAX_IMAGE_MEGAPIXELS: int = MAX_IMAGE_PIXELS // 1_000_000
# Parse only the formats ALLOWED_IMAGE_TYPES admits, so a mislabeled file is refused here.
_ALLOWED_PILLOW_FORMATS: tuple[str, ...] = ("JPEG", "PNG", "WEBP", "GIF")


def image_dimensions_error(content: bytes) -> str | None:
    """Check the image header against the API's pixel cap without decoding the image.

    Returns a user-facing error message, or ``None`` when the image is within limits.
    """
    too_large = f"Image is too large (max {MAX_IMAGE_MEGAPIXELS} megapixels)."
    try:
        with Image.open(BytesIO(content), formats=_ALLOWED_PILLOW_FORMATS) as image:
            width, height = image.size
    except Image.DecompressionBombError:
        return too_large
    # Malformed headers surface as any of these depending on the format plugin.
    except (OSError, ValueError, EOFError):
        return "File is not a valid image."
    if width * height > MAX_IMAGE_PIXELS:
        return too_large
    return None


def handle_image_upload(
    *,
    svc: AssetsMixin,
    parent_id: str,
    file: FileStorage | None,
) -> None:
    """Validate and persist an uploaded image, flashing the outcome."""
    if file is None or not file.filename:
        flash("No image selected.", "error")
        return
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        flash("Invalid image type. Allowed: JPEG, PNG, WebP, GIF.", "error")
        return

    content = file.read()
    if len(content) > MAX_IMAGE_SIZE:
        flash(f"Image is too large (max {MAX_IMAGE_SIZE_MB} MB).", "error")
        return
    if dimensions_error := image_dimensions_error(content):
        flash(dimensions_error, "error")
        return

    try:
        svc.upload_asset(parent_id, file.filename, content, file.content_type)
    except APIError as e:
        flash(api_error_message(e, fallback="Failed to upload image. Please try again."), "error")
        return

    flash("Image uploaded successfully.", "success")


def handle_image_delete(
    *,
    svc: AssetsMixin,
    parent_id: str,
    asset_id: str,
) -> None:
    """Delete an image asset via ``svc.delete_asset`` and flash the outcome."""
    try:
        svc.delete_asset(parent_id, asset_id)
    except APIError as e:
        flash(api_error_message(e, fallback="Failed to delete image. Please try again."), "error")
        return

    flash("Image deleted.", "success")


class AvatarService(Protocol):
    """Structural type of a vclient sync users service managing avatars."""

    def upload_avatar(
        self, user_id: str, filename: str, content: bytes, content_type: str | None = ...
    ) -> object:
        """Upload a custom avatar for the given user."""

    def delete_avatar(self, user_id: str) -> object:
        """Remove the given user's custom avatar."""


def handle_avatar_upload(
    *,
    svc: AvatarService,
    user_id: str,
    file: FileStorage | None,
) -> bool:
    """Validate and upload a user avatar, flashing the outcome.

    Returns whether an avatar was uploaded. An empty avatar field is the normal
    "only edited text" case, so it returns ``False`` silently without flashing.
    """
    if file is None or not file.filename:
        return False
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        flash("Invalid image type. Allowed: JPEG, PNG, WebP, GIF.", "error")
        return False

    content = file.read()
    if len(content) > MAX_AVATAR_SIZE:
        flash(f"Avatar is too large (max {MAX_AVATAR_SIZE_MB} MB).", "error")
        return False
    if dimensions_error := image_dimensions_error(content):
        flash(dimensions_error, "error")
        return False

    try:
        svc.upload_avatar(user_id, file.filename, content, file.content_type)
    except APIError as e:
        flash(api_error_message(e, fallback="Failed to upload avatar. Please try again."), "error")
        return False

    flash("Avatar updated.", "success")
    return True


def handle_avatar_delete(*, svc: AvatarService, user_id: str) -> bool:
    """Remove a user's custom avatar via ``svc.delete_avatar``, flashing the outcome.

    Returns whether the avatar was removed.
    """
    try:
        svc.delete_avatar(user_id)
    except APIError as e:
        flash(api_error_message(e, fallback="Failed to remove avatar. Please try again."), "error")
        return False

    flash("Avatar removed.", "success")
    return True
