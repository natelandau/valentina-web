"""Shared caching primitives for every API-response cache.

All cached reads route through :func:`cached_fetch`, which provides one
get -> freshness-check -> single-flight-on-miss -> set path. Single-flight is
always on: on a cold or stale key exactly one thread rebuilds while concurrent
callers for the same key wait and reuse the result, preventing a thundering herd
of redundant API calls.

Two axes are modeled independently:
    * scope     -> the cache key string (built by each caller)
    * freshness -> a Strategy object (PureTTL / ShortTTL / TimestampValidated)
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from vweb.extensions import cache

if TYPE_CHECKING:
    from collections.abc import Callable

# ASCII unit separator: cannot appear in IDs or filter values, so joining parts with
# it keeps field boundaries unambiguous — ("ab", "c") and ("a", "bc") never collide.
_HASH_FIELD_SEP = "\x1f"
# blake2b 16-byte digest -> 32 hex chars; collision-free at our cardinalities.
_HASH_DIGEST_SIZE = 16


def hash_key(*parts: object) -> str:
    """Fold an ordered set of cache-key parts into one stable, fixed-length digest.

    Use this for the variable/optional tail of a key (filters, scopes, paging) so the
    key stays a fixed length and never grows runs of empty ``::`` segments when some
    parts are blank. Compose it after the readable prefix, e.g.
    ``f"dicerolls:{company_id}:{hash_key(user_id, campaign_id, limit)}"``.

    Order-significant: pass parts in a fixed order at each call site so the same inputs
    always map to the same key. ``None`` hashes identically to ``""`` (an absent filter
    and an empty one are the same scope). Uses blake2b rather than the builtin ``hash``,
    which is per-process salted and would yield different keys across workers/restarts.
    """
    raw = _HASH_FIELD_SEP.join("" if part is None else str(part) for part in parts)
    return hashlib.blake2b(raw.encode(), digest_size=_HASH_DIGEST_SIZE).hexdigest()


class Strategy(Protocol):
    """Freshness policy for a cached value (the invalidation axis)."""

    ttl: int

    def is_fresh(self, cached: object) -> bool:
        """Return True when a cache hit may be served without refetching."""
        ...

    def wrap(self, value: object) -> object:
        """Transform a freshly fetched value into its stored form."""
        ...

    def unwrap(self, cached: object) -> object:
        """Recover the value from its stored form."""
        ...


_STAMP_TUPLE_LEN = 2  # TimestampValidated stores entries as (stamp, value) pairs


@dataclass(frozen=True)
class PureTTL:
    """Serve any unexpired hit; rely entirely on the backend TTL for freshness."""

    ttl: int

    def is_fresh(self, cached: object) -> bool:  # noqa: ARG002
        """Return True unconditionally; rely on the backend TTL for eviction."""
        return True

    def wrap(self, value: object) -> object:
        """Return the value unchanged; no envelope needed for pure-TTL caches."""
        return value

    def unwrap(self, cached: object) -> object:
        """Return the cached value unchanged."""
        return cached


@dataclass(frozen=True)
class ShortTTL(PureTTL):
    """PureTTL with intent-naming for eventually-consistent, low-TTL caches."""


@dataclass(frozen=True)
class TimestampValidated:
    """Serve a hit only while a caller-supplied stamp matches the stored stamp.

    The stored form is a ``(stamp, value)`` tuple. ``current_stamp`` is resolved on
    every read (e.g. from the request-scoped global context), so a bumped stamp
    invalidates the entry without an explicit clear.
    """

    ttl: int
    current_stamp: Callable[[], str]

    def is_fresh(self, cached: object) -> bool:
        """Return True only while the stored stamp still matches the live stamp."""
        if (
            not isinstance(cached, tuple) or len(cached) != _STAMP_TUPLE_LEN
        ):  # legacy/malformed entry
            return False
        stamp, _value = cached
        return stamp == self.current_stamp()

    def wrap(self, value: object) -> object:
        """Store the value as a (stamp, value) tuple."""
        return (self.current_stamp(), value)

    def unwrap(self, cached: object) -> object:
        """Extract the value from a (stamp, value) tuple."""
        _stamp, value = cached  # ty:ignore[not-iterable]
        return value


# Per-key single-flight locks shared by cached_fetch and bespoke callers
# (e.g. global_context). One lock per distinct cache key collapses a cold-cache
# stampede. Some keys are high-cardinality (dicerolls embeds user x scope x
# limit; audit logs embed a full filter set), so the dict is bounded: once it
# exceeds _MAX_LOCKS we drop currently-unheld locks. A held lock is mid-single-
# flight and is never evicted, so a hot key is always protected; dropping an
# idle lock only risks a rare redundant rebuild (the in-lock double-check keeps
# the cached result correct), never a stampede. Raw threading.Lock objects are
# not weak-referenceable, so a WeakValueDictionary is not an option here.
_MAX_LOCKS = 1024
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    """Return the shared single-flight lock for a key, creating it once."""
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            if len(_locks) >= _MAX_LOCKS:
                # Reclaim only idle locks; a locked() entry is an in-flight rebuild.
                for idle_key in [k for k, existing in _locks.items() if not existing.locked()]:
                    del _locks[idle_key]
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def single_flight[T](key: str, rebuild: Callable[[], T]) -> T:
    """Run ``rebuild`` under the key's single-flight lock.

    Concurrent callers for the same key serialize here; the first rebuilds and
    warms the cache, later callers re-read the warm value. ``rebuild`` is
    responsible for its own double-check of the cache. If ``rebuild`` raises,
    the lock is released and nothing is cached, so waiting callers will each
    retry ``rebuild`` sequentially (safe, but a persistent upstream error is
    not collapsed).
    """
    with _lock_for(key):
        return rebuild()


def cached_fetch[T](key: str, fetch: Callable[[], T], strategy: Strategy) -> T:
    """Return a cached value, fetching once under single-flight on a miss/stale read.

    A lock-free fast path serves fresh hits. On a miss or stale read, exactly one
    caller fetches while others wait and reuse the result.

    Args:
        key: The fully-qualified cache key (scope axis).
        fetch: Callable that produces the value on a cold/stale cache.
        strategy: Freshness policy (invalidation axis).

    Returns:
        The cached or freshly fetched value.
    """
    # Callers must not cache a None value: cache.get returns None for both a miss and a stored None, so a cached None is re-fetched every call.
    cached = cache.get(key)
    if cached is not None and strategy.is_fresh(cached):
        return strategy.unwrap(cached)  # ty:ignore[invalid-return-type]

    def rebuild() -> T:
        # Double-check inside the lock: another caller may have just built it.
        again = cache.get(key)
        if again is not None and strategy.is_fresh(again):
            return strategy.unwrap(again)  # ty:ignore[invalid-return-type]
        value = fetch()
        cache.set(key, strategy.wrap(value), timeout=strategy.ttl)
        return value

    return single_flight(key, rebuild)


def clear_key(*keys: str) -> None:
    """Delete one or more cache keys, forcing a fresh fetch on next access."""
    for key in keys:
        cache.delete(key)
