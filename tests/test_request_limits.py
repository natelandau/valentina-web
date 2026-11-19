"""Tests for the request body size limit set in the application factory."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from tests.conftest import get_csrf
from vweb.constants import (
    MAX_AVATAR_SIZE,
    MAX_IMAGE_SIZE,
    MAX_IMAGE_SIZE_MB,
    MAX_REQUEST_BODY_BYTES,
)

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

API_BODY_LIMIT_BYTES = 5_242_880
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def test_upload_limits_fit_between_the_body_cap_and_the_api_limit() -> None:
    """Verify a maximum-size upload passes the body cap and, with overhead, the API's limit."""
    assert MAX_REQUEST_BODY_BYTES > MAX_IMAGE_SIZE
    assert MAX_IMAGE_SIZE + MULTIPART_OVERHEAD_BYTES <= API_BODY_LIMIT_BYTES
    assert MAX_AVATAR_SIZE + MULTIPART_OVERHEAD_BYTES <= API_BODY_LIMIT_BYTES


def _post_oversized(client: FlaskClient, headers: dict[str, str] | None = None) -> TestResponse:
    oversized = io.BytesIO(b"x" * (MAX_REQUEST_BODY_BYTES + 1))
    return client.post(
        "/profile/test-user-id",
        data={"avatar": (oversized, "big.png", "image/png"), "csrf_token": get_csrf(client)},
        content_type="multipart/form-data",
        headers=headers or {},
    )


def test_oversized_body_is_rejected_with_413(client) -> None:
    """Verify a request body over the cap is refused before a view reads the upload."""
    assert _post_oversized(client).status_code == 413


def test_oversized_htmx_upload_flashes_instead_of_silent_413(client) -> None:
    """Verify an oversized HTMX upload gets a swappable 200 flashing the size limit.

    htmx discards 4xx responses, so a plain 413 would give the user no feedback.
    """
    response = _post_oversized(client, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.headers.get("HX-Reswap") == "none"
    assert f"{MAX_IMAGE_SIZE_MB} MB" in response.get_data(as_text=True)
