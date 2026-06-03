"""Tests for the shared cache primitive."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from vweb.lib.cache import base

if TYPE_CHECKING:
    from flask import Flask


def test_pure_ttl_is_always_fresh() -> None:
    """Verify PureTTL always reports a cached value as fresh."""
    strategy = base.PureTTL(ttl=60)
    assert strategy.is_fresh(strategy.wrap("value")) is True
    assert strategy.unwrap(strategy.wrap("value")) == "value"


def test_timestamp_validated_freshness_tracks_stamp() -> None:
    """Verify TimestampValidated reports stale after the stamp advances."""
    current = {"stamp": "a"}
    strategy = base.TimestampValidated(ttl=60, current_stamp=lambda: current["stamp"])
    stored = strategy.wrap("value")
    assert strategy.is_fresh(stored) is True
    assert strategy.unwrap(stored) == "value"
    current["stamp"] = "b"  # stamp advanced -> stale
    assert strategy.is_fresh(stored) is False


def test_cached_fetch_serves_warm_value_without_refetching(app: Flask) -> None:
    """Verify cached_fetch calls fetch exactly once when the cache is warm."""
    calls = {"n": 0}

    def fetch() -> str:
        calls["n"] += 1
        return "value"

    with app.app_context():
        first = base.cached_fetch("t:warm", fetch, base.PureTTL(ttl=60))
        second = base.cached_fetch("t:warm", fetch, base.PureTTL(ttl=60))

    assert first == second == "value"
    assert calls["n"] == 1


def test_single_flight_collapses_concurrent_cold_fetches(app: Flask) -> None:
    """Under contention, exactly one thread runs the fetch."""
    calls = {"n": 0}
    lock = threading.Lock()

    def fetch() -> str:
        with lock:
            calls["n"] += 1
        time.sleep(0.05)  # widen the race window
        return "value"

    results: list[str] = []
    results_lock = threading.Lock()
    start = threading.Barrier(8)

    def worker() -> None:
        start.wait()
        with app.app_context():
            value = base.cached_fetch("t:cold", fetch, base.PureTTL(ttl=60))
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["value"] * 8
    assert calls["n"] == 1


def test_timestamp_validated_treats_non_tuple_as_stale() -> None:
    """Verify a malformed (non-tuple) cached entry is treated as stale, not a crash."""
    strategy = base.TimestampValidated(ttl=60, current_stamp=lambda: "a")
    # Given a legacy/malformed cached value that is not a (stamp, value) tuple
    # Then is_fresh returns False instead of raising
    assert strategy.is_fresh("legacy-plain-string") is False
    assert strategy.is_fresh(("a", "value", "extra")) is False


def test_clear_key_removes_entries(app: Flask) -> None:
    """Verify clear_key forces a fresh fetch on the next access."""
    with app.app_context():
        base.cached_fetch("t:clear", lambda: "v", base.PureTTL(ttl=60))
        base.clear_key("t:clear")
        calls = {"n": 0}

        def fetch() -> str:
            calls["n"] += 1
            return "v2"

        assert base.cached_fetch("t:clear", fetch, base.PureTTL(ttl=60)) == "v2"
        assert calls["n"] == 1
