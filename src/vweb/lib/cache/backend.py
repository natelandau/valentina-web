"""Redis cache backend that treats entries it cannot unpickle as cache misses.

Pickled entries name the module and class of every object they hold. When a release
moves, renames, or removes one of those classes, or drops an enum value, entries written
by an earlier release raise on load. Reading them as misses lets the cache refill
instead of failing the request.
"""

from __future__ import annotations

from typing import Any

from cachelib.serializers import RedisSerializer
from flask_caching.backends.rediscache import RedisCache
from loguru import logger


class TolerantRedisSerializer(RedisSerializer):
    """Redis serializer that returns None for an entry that no longer unpickles."""

    def loads(self, value: bytes | None) -> Any:
        """Load a cached value, or return None when the entry no longer unpickles.

        Args:
            value: The raw bytes stored in Redis, or None on a miss.

        Returns:
            Any: The cached value, or None when the entry cannot be loaded.
        """
        try:
            return super().loads(value)
        # A stale entry raises whatever its classes raise on rebuild (ImportError,
        # AttributeError, ValueError for a dropped enum value, TypeError), not PickleError
        except Exception as e:  # noqa: BLE001
            logger.warning("Skip unloadable cache entry: {error!r}", error=e)
            return None


class TolerantRedisCache(RedisCache):
    """Flask-Caching Redis backend that loads entries through TolerantRedisSerializer."""

    serializer = TolerantRedisSerializer()
