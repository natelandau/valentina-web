"""Tests for client log enablement."""

import logging

import pytest
from loguru import logger

from vweb.api_client import users_service
from vweb.api_client.testing import FakeVClient, Routes, UserFactory
from vweb.lib.log_config import InterceptHandler

PREFIX = "vweb.api_client"


@pytest.fixture
def captured_names():
    """Capture the logger name of every record emitted while the test runs."""
    names: list[str | None] = []
    sink_id = logger.add(lambda message: names.append(message.record["name"]), level="TRACE")
    yield names
    logger.remove(sink_id)


def _trigger_client_log(fake_vclient: FakeVClient) -> None:
    fake_vclient.set_response(Routes.USERS_GET, model=UserFactory.build(id="u1"))
    users_service(on_behalf_of="u1").get("u1")


def test_client_logs_disabled_by_default(fake_vclient, captured_names):
    """Verify the client package emits no logs unless enabled."""
    _trigger_client_log(fake_vclient)

    assert not [n for n in captured_names if n and n.startswith(PREFIX)]


def test_client_logs_enabled_by_setting(fake_vclient, captured_names):
    """Verify enabling the client logger lets its records through."""
    logger.enable(PREFIX)
    try:
        _trigger_client_log(fake_vclient)
    finally:
        logger.disable(PREFIX)

    assert [n for n in captured_names if n and n.startswith(PREFIX)]


def test_client_log_emitted_once_when_enabled():
    """Verify a client log reaches loguru once when stdlib logging is routed back into loguru."""
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    stdlib_records: list[logging.LogRecord] = []
    spy = logging.Handler()
    spy.emit = stdlib_records.append  # ty:ignore[invalid-assignment]
    logging.basicConfig(handlers=[InterceptHandler(), spy], level=0, force=True)
    messages: list[str] = []
    # No name filter: a forwarded copy re-enters loguru under a different logger name
    sink_id = logger.add(lambda message: messages.append(message.record["message"]), level="TRACE")
    logger.enable(PREFIX)
    try:
        # Not the `fake_vclient` fixture: it builds the app, which resets loguru's sinks
        with FakeVClient() as fake_vclient:
            _trigger_client_log(fake_vclient)
    finally:
        logger.disable(PREFIX)
        logger.remove(sink_id)
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])

    assert messages.count("Send request") == 1
    assert not [r for r in stdlib_records if r.name.startswith(PREFIX)]


def test_custom_stdlib_level_reaches_loguru():
    """Verify a stdlib record at a level loguru does not know is forwarded by its number."""
    messages: list[tuple[int, str]] = []
    sink_id = logger.add(
        lambda m: messages.append((m.record["level"].no, m.record["message"])), level=0
    )
    record = logging.LogRecord("lib", 7, __file__, 1, "custom level", None, None)
    try:
        InterceptHandler().emit(record)
    finally:
        logger.remove(sink_id)

    assert messages == [(7, "custom level")]
