"""Tests for the request body size limit set in the application factory."""

from __future__ import annotations

import io

from tests.conftest import get_csrf
from vweb.constants import MAX_IMAGE_SIZE, MAX_REQUEST_BODY_BYTES


def test_cap_leaves_room_for_the_largest_upload(app) -> None:
    """Verify the body cap is set and still admits a maximum-size image upload."""
    assert app.config["MAX_CONTENT_LENGTH"] == MAX_REQUEST_BODY_BYTES
    assert MAX_REQUEST_BODY_BYTES > MAX_IMAGE_SIZE


def test_oversized_body_is_rejected_with_413(client) -> None:
    """Verify a request body over the cap is refused before a view reads the upload."""
    # Given a multipart upload larger than the cap
    oversized = io.BytesIO(b"x" * (MAX_REQUEST_BODY_BYTES + 1))

    # When it is posted to an upload route
    response = client.post(
        "/profile/test-user-id",
        data={"avatar": (oversized, "big.png", "image/png"), "csrf_token": get_csrf(client)},
        content_type="multipart/form-data",
    )

    # Then the server answers 413 instead of buffering it
    assert response.status_code == 413


def test_oversized_htmx_upload_flashes_instead_of_silent_413(client) -> None:
    """Verify an oversized HTMX upload gets a swappable 200 carrying a flash message."""
    # Given a multipart upload larger than the cap sent by htmx
    oversized = io.BytesIO(b"x" * (MAX_REQUEST_BODY_BYTES + 1))

    # When it is posted to an upload route
    response = client.post(
        "/profile/test-user-id",
        data={"avatar": (oversized, "big.png", "image/png"), "csrf_token": get_csrf(client)},
        content_type="multipart/form-data",
        headers={"HX-Request": "true"},
    )

    # Then htmx receives a 200 that swaps in only the flash container
    assert response.status_code == 200
    assert response.headers.get("HX-Reswap") == "none"
    assert "too large" in response.get_data(as_text=True)
