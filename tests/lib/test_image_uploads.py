"""Tests for the shared image upload validation helpers."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from flask import get_flashed_messages
from PIL import Image
from werkzeug.datastructures import FileStorage

from tests.helpers import make_image_bytes
from vweb.api_client.exceptions import PayloadTooLargeError, ServerError
from vweb.constants import MAX_IMAGE_SIZE_MB
from vweb.lib.image_uploads import (
    handle_avatar_delete,
    handle_avatar_upload,
    handle_image_delete,
    handle_image_upload,
    image_dimensions_error,
)


def _png() -> FileStorage:
    return FileStorage(
        stream=io.BytesIO(make_image_bytes()), filename="a.png", content_type="image/png"
    )


@pytest.mark.parametrize(
    ("content", "valid"),
    [
        pytest.param(make_image_bytes(1, 1), True, id="tiny"),
        pytest.param(make_image_bytes(6000, 4000), True, id="exactly-24mp"),
        pytest.param(make_image_bytes(6000, 4001), False, id="over-24mp"),
        pytest.param(b"not-an-image", False, id="unreadable"),
        pytest.param(make_image_bytes(image_format="BMP"), False, id="disallowed-format"),
    ],
)
def test_image_dimensions_error(content: bytes, valid: bool) -> None:  # noqa: FBT001
    """Verify only readable images of an allowed type within 24 megapixels pass."""
    assert (image_dimensions_error(content) is None) is valid


def test_decompression_bomb_is_rejected_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify an image Pillow flags as a decompression bomb is refused instead of crashing."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    assert image_dimensions_error(make_image_bytes(10, 10)) is not None


def test_413_from_api_flashes_upload_limit(app) -> None:
    """Verify a 413 from the API flashes the upload size limit instead of a generic failure."""
    svc = MagicMock()
    svc.upload_asset.side_effect = PayloadTooLargeError("Request body too large", 413, {})

    with app.test_request_context():
        uploaded = handle_image_upload(svc=svc, parent_id="p1", file=_png())
        messages = get_flashed_messages(category_filter=["error"])

    assert uploaded is False
    assert len(messages) == 1
    assert f"{MAX_IMAGE_SIZE_MB} MB" in messages[0]


@pytest.mark.parametrize(
    ("method", "call", "reports_success"),
    [
        pytest.param(
            "upload_asset",
            lambda svc: handle_image_upload(svc=svc, parent_id="p1", file=_png()),
            True,
            id="image-upload",
        ),
        pytest.param(
            "delete_asset",
            lambda svc: handle_image_delete(svc=svc, parent_id="p1", asset_id="a1"),
            False,
            id="image-delete",
        ),
        pytest.param(
            "upload_avatar",
            lambda svc: handle_avatar_upload(svc=svc, user_id="u1", file=_png()),
            True,
            id="avatar-upload",
        ),
        pytest.param(
            "delete_avatar",
            lambda svc: handle_avatar_delete(svc=svc, user_id="u1"),
            True,
            id="avatar-delete",
        ),
    ],
)
@pytest.mark.parametrize("fails", [False, True])
def test_api_outcome_is_flashed(
    app, method: str, call, *, reports_success: bool, fails: bool
) -> None:
    """Verify each handler flashes success, or an error when the API call fails.

    Handlers that report success return whether the API call succeeded.
    """
    svc = MagicMock()
    if fails:
        getattr(svc, method).side_effect = ServerError("boom", 500, {})

    with app.test_request_context():
        result = call(svc)
        flashes = get_flashed_messages(with_categories=True)

    assert [category for category, _ in flashes] == ["error" if fails else "success"]
    assert result == ((not fails) if reports_success else None)


def test_empty_avatar_field_is_silent(app) -> None:
    """Verify a form saved without a new avatar neither uploads nor flashes."""
    svc = MagicMock()

    with app.test_request_context():
        uploaded = handle_avatar_upload(svc=svc, user_id="u1", file=None)
        flashes = get_flashed_messages()

    assert uploaded is False
    assert flashes == []
    svc.upload_avatar.assert_not_called()
