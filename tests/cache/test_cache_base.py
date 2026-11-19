"""Tests for the shared cache primitive."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import pytest

from vweb.lib.cache import base

if TYPE_CHECKING:
    from flask import Flask


def test_pure_ttl_round_trips_and_stays_fresh() -> None:
    """Verify PureTTL leaves expiry to the TTL and returns the stored value."""
    strategy = base.PureTTL(ttl=60)

    assert strategy.is_fresh(strategy.wrap("value")) is True
    assert strategy.unwrap(strategy.wrap("value")) == "value"


def test_timestamp_validated_freshness_tracks_stamp() -> None:
    """Verify TimestampValidated reports stale once the external stamp advances."""
    current = {"stamp": "a"}
    strategy = base.TimestampValidated(ttl=60, current_stamp=lambda: current["stamp"])
    stored = strategy.wrap("value")

    assert strategy.is_fresh(stored) is True
    assert strategy.unwrap(stored) == "value"
    current["stamp"] = "b"
    assert strategy.is_fresh(stored) is False


@pytest.mark.parametrize("stored", ["legacy-plain-string", ("a", "value", "extra")])
def test_timestamp_validated_treats_malformed_entry_as_stale(stored: object) -> None:
    """Verify a malformed cached entry reads as stale instead of crashing."""
    strategy = base.TimestampValidated(ttl=60, current_stamp=lambda: "a")

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


@pytest.mark.parametrize(
    ("first", "second", "equal"),
    [
        pytest.param(("a", "b", 25), ("a", "b", 25), True, id="deterministic"),
        pytest.param(("a", "b"), ("a", "c"), False, id="different-parts"),
        pytest.param(("a", "b"), ("b", "a"), False, id="order-sensitive"),
        pytest.param(("ab", "c"), ("a", "bc"), False, id="boundaries-kept"),
        pytest.param(("x", None), ("x", ""), True, id="none-is-empty"),
    ],
)
def test_hash_key_identity(first: tuple, second: tuple, *, equal: bool) -> None:
    """Verify equal part lists share a key and any other difference changes it."""
    assert (base.hash_key(*first) == base.hash_key(*second)) is equal


def test_hash_key_is_one_token() -> None:
    """Verify empty parts still yield a single non-empty token with no colon runs."""
    digest = base.hash_key("", "", "campaign-1", "", 25)

    assert digest
    assert ":" not in digest


def test_lock_registry_evicts_only_idle_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the bounded lock registry never drops a lock held by an in-flight rebuild."""
    monkeypatch.setattr(base, "_locks", {})
    monkeypatch.setattr(base, "_MAX_LOCKS", 2)
    held = base._lock_for("held")
    idle = base._lock_for("idle")

    with held:
        base._lock_for("new")

        assert base._lock_for("held") is held
        assert base._lock_for("idle") is not idle


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
