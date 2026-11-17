"""Tests for the fake client's request recording helpers."""

import pytest

from vweb.api_client.testing._recording import encode_query


class TestEncodeQuery:
    """encode_query should encode filters the way the client sends them."""

    def test_encodes_scalar_values(self):
        """Verify scalars encode to their wire strings."""
        assert encode_query({"active": True, "limit": 10}) == {"active": "true", "limit": "10"}

    def test_rejects_multi_value_filter(self):
        """Verify a list filter raises instead of silently matching only its last value."""
        with pytest.raises(TypeError, match="one value per key"):
            encode_query({"ids": ["a", "b"]})
