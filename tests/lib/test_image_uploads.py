"""Tests for the shared image upload validation helpers."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from flask import get_flashed_messages
from vclient.exceptions import APIError
from werkzeug.datastructures import FileStorage

from tests.helpers import make_image_bytes
from vweb.lib.image_uploads import handle_image_upload, image_dimensions_error


class TestImageDimensionsError:
    """Tests for image_dimensions_error."""

    @pytest.mark.parametrize(
        ("width", "height"),
        [(1, 1), (6000, 4000)],
        ids=["tiny", "exactly-24mp"],
    )
    def test_accepts_images_within_the_pixel_cap(self, width: int, height: int) -> None:
        """Verify images at or under 24 megapixels pass."""
        # Given an image within the cap
        content = make_image_bytes(width, height)

        # When checking its dimensions
        result = image_dimensions_error(content)

        # Then no error is returned
        assert result is None

    def test_rejects_images_over_the_pixel_cap(self) -> None:
        """Verify an image one row over 24 megapixels is rejected."""
        # Given a 6000 x 4001 image
        content = make_image_bytes(6000, 4001)

        # When checking its dimensions
        result = image_dimensions_error(content)

        # Then the too-large message is returned
        assert result == "Image is too large (max 24 megapixels)."

    def test_rejects_unreadable_bytes(self) -> None:
        """Verify bytes Pillow cannot identify are reported as an invalid image."""
        # When checking bytes that are not an image
        result = image_dimensions_error(b"not-an-image")

        # Then the invalid-image message is returned
        assert result == "File is not a valid image."

    def test_rejects_formats_outside_the_allowed_types(self) -> None:
        """Verify a readable image in a format the upload types do not allow is rejected."""
        # When checking a BMP image
        result = image_dimensions_error(make_image_bytes(image_format="BMP"))

        # Then the invalid-image message is returned
        assert result == "File is not a valid image."


def test_413_from_api_flashes_upload_limit(app) -> None:
    """Verify a 413 from the API flashes the upload size limit instead of a generic failure."""
    # Given an upload service whose API call is rejected as too large
    svc = MagicMock()
    svc.upload_asset.side_effect = APIError("Request body too large", 413, {})
    file = FileStorage(
        stream=io.BytesIO(make_image_bytes()), filename="a.png", content_type="image/png"
    )

    # When the image is uploaded
    with app.test_request_context():
        result = handle_image_upload(svc=svc, parent_id="p1", file=file)
        messages = get_flashed_messages(category_filter=["error"])

    # Then nothing is returned and the flash names the limit
    assert result is None
    assert messages == ["Upload is too large (max 4 MB)."]
