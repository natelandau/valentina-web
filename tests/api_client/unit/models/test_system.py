"""Tests for vweb.api_client.api.models.system."""

import pytest
from pydantic import ValidationError

from vweb.api_client.models.system import SystemHealth


class TestSystemHealth:
    """Tests for SystemHealth model."""

    def test_valid_health_response(self):
        """Verify parsing a valid health response."""
        # Given: Valid health response data
        data = {
            "database_status": "online",
            "cache_status": "online",
            "database_latency_ms": 1.5,
            "cache_latency_ms": 0.8,
            "uptime": "3d 12h 45m",
            "version": "1.0.0",
        }

        # When: Parsing the data
        health = SystemHealth.model_validate(data)

        # Then: All fields are correctly parsed
        assert health.database_status == "online"
        assert health.cache_status == "online"
        assert health.database_latency_ms == 1.5
        assert health.cache_latency_ms == 0.8
        assert health.uptime == "3d 12h 45m"
        assert health.version == "1.0.0"

    def test_health_with_offline_status(self):
        """Verify parsing health response with offline services."""
        # Given: Health response with offline services
        data = {
            "database_status": "offline",
            "cache_status": "offline",
            "database_latency_ms": None,
            "cache_latency_ms": None,
            "uptime": "0d 0h 5m",
            "version": "1.0.0",
        }

        # When: Parsing the data
        health = SystemHealth.model_validate(data)

        # Then: Offline status is correctly parsed
        assert health.database_status == "offline"
        assert health.cache_status == "offline"
        assert health.database_latency_ms is None
        assert health.cache_latency_ms is None

    def test_health_with_null_latency(self):
        """Verify parsing health response with null latency values."""
        # Given: Health response with null latency
        data = {
            "database_status": "online",
            "cache_status": "online",
            "database_latency_ms": None,
            "cache_latency_ms": None,
            "uptime": "1d 0h 0m",
            "version": "1.0.0",
        }

        # When: Parsing the data
        health = SystemHealth.model_validate(data)

        # Then: Null latency values are correctly parsed
        assert health.database_latency_ms is None
        assert health.cache_latency_ms is None

    @pytest.mark.parametrize(
        ("data", "missing_field"),
        [
            (
                {
                    "cache_status": "online",
                    "database_latency_ms": 1.0,
                    "cache_latency_ms": 0.5,
                    "uptime": "1d",
                    "version": "1.0.0",
                },
                "database_status",
            ),
            (
                {
                    "database_status": "online",
                    "database_latency_ms": 1.0,
                    "cache_latency_ms": 0.5,
                    "uptime": "1d",
                    "version": "1.0.0",
                },
                "cache_status",
            ),
            (
                {
                    "database_status": "online",
                    "cache_status": "online",
                    "database_latency_ms": 1.0,
                    "cache_latency_ms": 0.5,
                    "version": "1.0.0",
                },
                "uptime",
            ),
        ],
    )
    def test_health_missing_required_field_raises(self, data, missing_field):
        """Verify missing required fields raise ValidationError."""
        # When/Then: Parsing raises ValidationError with field name
        with pytest.raises(ValidationError) as exc_info:
            SystemHealth.model_validate(data)

        assert missing_field in str(exc_info.value)
