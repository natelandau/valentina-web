"""Tests for the fake client's request recording helpers."""

import httpx2
import pytest

from vweb.api_client.testing._recording import RecordedFile, encode_query, record


class TestEncodeQuery:
    """encode_query should encode filters the way the client sends them."""

    def test_encodes_scalar_values(self):
        """Verify scalars encode to their wire strings."""
        assert encode_query({"active": True, "limit": 10}) == {"active": "true", "limit": "10"}

    def test_rejects_multi_value_filter(self):
        """Verify a list filter raises instead of silently matching only its last value."""
        with pytest.raises(TypeError, match="one value per key"):
            encode_query({"ids": ["a", "b"]})


@pytest.mark.parametrize(
    ("request_kwargs", "form", "files"),
    [
        pytest.param({"data": {"name": "Ada"}}, {"name": "Ada"}, {}, id="urlencoded"),
        pytest.param(
            {"data": {"note": "hi"}, "files": {"data": ("a.png", b"png", "image/png")}},
            {"note": "hi"},
            {"data": RecordedFile(filename="a.png", content_type="image/png", content=b"png")},
            id="multipart-field-and-file",
        ),
    ],
)
def test_record_splits_form_bodies(
    request_kwargs: dict, form: dict, files: dict[str, RecordedFile]
) -> None:
    """Verify form and multipart bodies are recorded as form fields and file parts."""
    request = httpx2.Request("POST", "https://fake.test/api/v1/x", **request_kwargs)

    recorded = record(request, path="/api/v1/x", route=None, params={})

    assert recorded.form == form
    assert recorded.files == files
    assert recorded.json is None
