"""Tests for the Redis cache backend's handling of entries it cannot load."""

from __future__ import annotations

import pickle
from http import HTTPStatus
from unittest.mock import patch

import vweb
from vweb.app import create_app
from vweb.config import RedisSettings, Settings
from vweb.extensions import cache
from vweb.lib.cache.backend import TolerantRedisCache, TolerantRedisSerializer


def _pickle_of_missing_module() -> bytes:
    """Build a Redis cache value whose pickle names a module that is not installed."""
    payload = pickle.dumps(len).replace(b"builtins", b"gone_mod")
    return b"!" + payload


class TestTolerantRedisSerializer:
    """Tests for TolerantRedisSerializer.loads."""

    def test_round_trips_a_value(self) -> None:
        """Verify a value written by dumps loads back unchanged."""
        # Given a serializer and a pickled value
        serializer = TolerantRedisSerializer()
        stored = serializer.dumps({"a": [1, 2]})

        # When loading it
        result = serializer.loads(stored)

        # Then the original value returns
        assert result == {"a": [1, 2]}

    def test_missing_module_is_a_miss(self) -> None:
        """Verify an entry pickled from a module that no longer exists loads as None."""
        # Given a value pickled from a module that is not installed
        stored = _pickle_of_missing_module()

        # When loading it
        result = TolerantRedisSerializer().loads(stored)

        # Then it reads as a cache miss instead of raising
        assert result is None

    def test_missing_attribute_is_a_miss(self) -> None:
        """Verify an entry whose class was renamed or removed loads as None."""
        # Given a value pickled from a class the module no longer defines
        stored = b"!" + pickle.dumps(len).replace(b"len", b"zzz")

        # When loading it
        result = TolerantRedisSerializer().loads(stored)

        # Then it reads as a cache miss instead of raising
        assert result is None

    def test_dropped_enum_value_is_a_miss(self) -> None:
        """Verify an entry holding an enum value the enum no longer defines loads as None."""
        # Given a value pickled from an enum member whose value no longer exists
        stored = b"!" + pickle.dumps(HTTPStatus.OK).replace(b"K\xc8", b"K\x01")

        # When loading it
        result = TolerantRedisSerializer().loads(stored)

        # Then it reads as a cache miss instead of raising
        assert result is None

    def test_logs_the_unloadable_entry(self) -> None:
        """Verify an unloadable entry logs a warning that names the error."""
        # Given a value pickled from a module that is not installed
        stored = _pickle_of_missing_module()

        # When loading it
        with patch("vweb.lib.cache.backend.logger") as mock_logger:
            TolerantRedisSerializer().loads(stored)

        # Then a warning names the failure
        mock_logger.warning.assert_called_once()
        assert "gone_mod" in str(mock_logger.warning.call_args)


class TestCacheConfig:
    """Tests for the cache settings create_app applies."""

    def test_redis_cache_uses_tolerant_backend_and_versioned_prefix(
        self, test_settings: Settings
    ) -> None:
        """Verify Redis caching loads through the tolerant backend under a per-release prefix."""
        # Given settings with a Redis URL
        settings = test_settings.model_copy(
            update={"redis": RedisSettings(url="redis://127.0.0.1:1/0")}
        )

        # When the app is created
        app = create_app(settings_override=settings)

        # Then the cache uses the tolerant backend and a prefix scoped to this release
        backend = app.extensions["cache"][cache]
        assert isinstance(backend, TolerantRedisCache)
        assert isinstance(backend.serializer, TolerantRedisSerializer)
        assert backend.key_prefix == f"vweb:{vweb.__version__}:"
