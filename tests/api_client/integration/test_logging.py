"""Tests for structured logging across the vclient package."""

import contextlib
import logging
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
import respx
from loguru import logger

from vweb.api_client import VClient
from vweb.api_client.exceptions import APIError, NotFoundError
from vweb.api_client.services.base import BaseService

# Loguru's TRACE level maps to stdlib levelno 5 (below DEBUG)
TRACE_LEVEL = 5


class ConcreteService(BaseService):
    """Concrete implementation of BaseService for testing."""


@pytest.fixture
def enable_vclient_logging():
    """Enable vclient logging for the test, disable on teardown."""
    logger.enable("vweb.api_client")
    yield
    logger.disable("vweb.api_client")


@pytest.fixture
def mock_sleep(mocker):
    """Patch the retry sleep so retries run instantly."""
    return mocker.patch("vweb.api_client.services.base.time.sleep")


def _vclient_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return all caplog records from the vclient namespace."""
    return [r for r in caplog.records if r.name.startswith("vweb.api_client")]


def _find_record(caplog: pytest.LogCaptureFixture, message: str) -> Any:
    """Find the first vclient record matching the given message."""
    for r in caplog.records:
        if r.name.startswith("vweb.api_client") and r.message == message:
            return r
    return None


def _call(
    caplog: pytest.LogCaptureFixture,
    base_url: str,
    api_key: str,
    call: Callable[[ConcreteService], object],
    *,
    level: int = logging.DEBUG,
    **client_kwargs: Any,
) -> VClient:
    """Run one service call with log capture on, swallowing any API error it raises."""
    with (
        caplog.at_level(level, logger="vweb.api_client"),
        VClient(base_url=base_url, api_key=api_key, **client_kwargs) as client,
        contextlib.suppress(APIError),
    ):
        call(ConcreteService(client))
    return client


class TestLoggingInitialization:
    """Tests for logging initialization and default behavior."""

    @respx.mock
    def test_logging_disabled_by_default(self, base_url, api_key, caplog):
        """Verify no vclient logs appear without explicit enable."""
        # Given: A client with logging at default state (disabled)
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a request
        _call(caplog, base_url, api_key, lambda s: s._get("/test"))

        # Then: No vclient log records appear
        assert _vclient_records(caplog) == []


@pytest.mark.usefixtures("enable_vclient_logging")
class TestRequestLogging:
    """Tests for HTTP request lifecycle logging."""

    @respx.mock
    def test_log_request_start_and_response(self, base_url, api_key, caplog):
        """Verify 'Send request' logs at TRACE and 'Request complete' at DEBUG with fields."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request with TRACE captured
        _call(caplog, base_url, api_key, lambda s: s._get("/test"), level=TRACE_LEVEL)

        # Then: "Send request" is present at TRACE with correct structured fields
        send = _find_record(caplog, "Send request")
        assert send.levelno == TRACE_LEVEL
        assert send.extra["method"] == "GET"
        assert send.extra["url"] == "/test"

        # Then: "Request complete" is present at DEBUG with correct structured fields
        receive = _find_record(caplog, "Request complete")
        assert receive.levelno == logging.DEBUG
        assert receive.extra["method"] == "GET"
        assert receive.extra["url"] == "/test"
        assert receive.extra["status"] == 200

    @pytest.mark.parametrize("params", [{"limit": 50, "offset": 100}, None])
    @respx.mock
    def test_log_request_carries_query_params(self, base_url, api_key, caplog, params):
        """Verify the send and complete lines carry the params so paginated calls differ."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request with or without params
        _call(
            caplog, base_url, api_key, lambda s: s._get("/test", params=params), level=TRACE_LEVEL
        )

        # Then: Both lines carry the params, or None when absent
        assert _find_record(caplog, "Send request").extra["params"] == params
        assert _find_record(caplog, "Request complete").extra["params"] == params

    @respx.mock
    def test_log_send_request_hidden_at_debug(self, base_url, api_key, caplog):
        """Verify 'Send request' is suppressed when capturing only at DEBUG and above."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request
        _call(caplog, base_url, api_key, lambda s: s._get("/test"))

        # Then: only the single "Request complete" line shows; no "Send request" noise
        assert _find_record(caplog, "Send request") is None
        assert _find_record(caplog, "Request complete") is not None

    @pytest.mark.parametrize(
        ("failure", "message", "fields"),
        [
            pytest.param(
                lambda: respx.MockResponse(
                    429, json={"detail": "Rate limited"}, headers={"RateLimit": '"d";r=0;t=1'}
                ),
                "Retry after rate limit",
                {},
                id="rate-limit",
            ),
            pytest.param(
                lambda: respx.MockResponse(500, json={"detail": "Server error"}),
                "Retry after server error",
                {"status": 500},
                id="server-error",
            ),
            pytest.param(
                lambda: httpx2.ConnectError("Connection refused"),
                "Retry after network error",
                {"error_type": "ConnectError"},
                id="network-error",
            ),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_log_retry(self, base_url, api_key, caplog, failure, message, fields):
        """Verify each retry cause logs a WARNING with structured fields."""
        # Given: An endpoint that fails once, then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[failure(), respx.MockResponse(200, json={"ok": True})]
        )

        # When: Making a request that is retried
        _call(caplog, base_url, api_key, lambda s: s._get("/test"))

        # Then: The retry warning is present with structured fields
        record = _find_record(caplog, message)
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"
        for key, value in fields.items():
            assert record.extra[key] == value

    @respx.mock
    def test_log_retry_on_idempotency_in_progress(self, base_url, api_key, caplog, mock_sleep):
        """Verify an in-progress 409 retry logs one WARNING with structured fields."""
        # Given: An endpoint that reports the idempotent request in progress, then succeeds
        respx.post(f"{base_url}/test").mock(
            side_effect=[
                respx.MockResponse(
                    409,
                    json={"detail": "In progress", "code": "IDEMPOTENCY_IN_PROGRESS"},
                    headers={"Retry-After": "1"},
                ),
                respx.MockResponse(201, json={"ok": True}),
            ]
        )

        # When: Making a POST request with an idempotency key
        client = _call(
            caplog,
            base_url,
            api_key,
            lambda s: s._post("/test", json={"data": "value"}, idempotency_key="key-1"),
        )

        # Then: The retry warning is present with structured fields
        record = _find_record(caplog, "Retry after idempotency conflict")
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "POST"
        assert record.extra["url"] == "/test"
        assert record.extra["status"] == 409
        assert record.extra["attempt"] == 1
        assert record.extra["max_attempts"] == client._config.max_retries + 1
        assert 1.0 <= record.extra["delay"] <= 1.25
        mock_sleep.assert_called_once_with(record.extra["delay"])

        # Then: The expected conflict itself is logged at DEBUG, not as a second WARNING
        assert _find_record(caplog, "Return 409 conflict").levelno == logging.DEBUG

    @pytest.mark.parametrize(
        ("auto_retry", "message", "level", "absent"),
        [
            (True, "Exhaust retries", logging.ERROR, "Fail with automatic retries off"),
            (False, "Fail with automatic retries off", logging.WARNING, "Exhaust retries"),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_log_final_failure(self, base_url, api_key, caplog, auto_retry, message, level, absent):
        """Verify a final failure is reported as exhausted retries only when retries ran."""
        # Given: An endpoint that always returns 429
        respx.get(f"{base_url}/test").respond(
            429, json={"detail": "Rate limited"}, headers={"RateLimit": '"d";r=0;t=1'}
        )

        # When: Making a request that keeps failing
        _call(
            caplog, base_url, api_key, lambda s: s._get("/test"), auto_retry_rate_limit=auto_retry
        )

        # Then: Only the matching failure line is logged, with structured fields
        record = _find_record(caplog, message)
        assert record.levelno == level
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"
        assert _find_record(caplog, absent) is None


@pytest.mark.usefixtures("enable_vclient_logging")
class TestErrorClassificationLogging:
    """Tests for error classification logging in _raise_for_status."""

    @pytest.mark.parametrize(
        ("status", "message", "level"),
        [
            (401, "Fail authentication", logging.ERROR),
            (403, "Deny authorization", logging.ERROR),
            (404, "Return 404", logging.DEBUG),
            (400, "Reject with validation error", logging.WARNING),
            (409, "Return 409 conflict", logging.WARNING),
            (413, "Reject request body as too large", logging.WARNING),
            (422, "Reject with unprocessable entity error", logging.WARNING),
        ],
    )
    @respx.mock
    def test_log_error_status(self, base_url, api_key, caplog, status, message, level):
        """Verify each error status logs its own line, level, and request context."""
        # Given: An endpoint that returns the error with a request id header
        respx.get(f"{base_url}/test").respond(
            status, json={"detail": "Error"}, headers={"X-Request-Id": "req_error456"}
        )
        params = {"limit": 25, "offset": 0}

        # When: Making a paginated request that fails
        _call(caplog, base_url, api_key, lambda s: s._get("/test", params=params))

        # Then: The error line carries the level and identifying fields
        record = _find_record(caplog, message)
        assert record.levelno == level
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"
        assert record.extra["status"] == status
        assert record.extra["params"] == params
        assert record.extra["request_id"] == "req_error456"


@pytest.mark.usefixtures("enable_vclient_logging")
class TestClientLifecycleLogging:
    """Tests for VClient lifecycle logging."""

    @pytest.mark.parametrize("message", ["Initialize VClient", "Close VClient"])
    def test_log_client_lifecycle(self, base_url, api_key, caplog, message):
        """Verify client creation and close each log at INFO with the base URL."""
        # When: Creating and closing a client
        with caplog.at_level(logging.DEBUG, logger="vweb.api_client"):
            VClient(base_url=base_url, api_key=api_key).close()

        # Then: The lifecycle line is present at INFO with structured fields
        record = _find_record(caplog, message)
        assert record.levelno == logging.INFO
        assert record.extra["base_url"] == base_url


class TestRequestIdLogging:
    """Tests for request_id in structured log output and raised errors."""

    @pytest.mark.parametrize(
        ("headers", "logged"),
        [({"X-Request-Id": "req_success123"}, "req_success123"), ({}, None)],
    )
    @respx.mock
    @pytest.mark.usefixtures("enable_vclient_logging")
    def test_success_response_logs_request_id(self, base_url, api_key, caplog, headers, logged):
        """Verify the success log carries X-Request-Id only when the header is sent."""
        # Given: An endpoint that returns 200 with or without X-Request-Id
        respx.get(f"{base_url}/test").respond(200, json={"ok": True}, headers=headers)

        # When: Making a successful request
        _call(caplog, base_url, api_key, lambda s: s._get("/test"))

        # Then: The request id is present only when the header was sent
        assert _find_record(caplog, "Request complete").extra.get("request_id") == logged

    @pytest.mark.parametrize(
        ("body", "headers", "expected"),
        [
            pytest.param({"request_id": "req_body789"}, {}, "req_body789", id="body"),
            pytest.param({}, {"X-Request-Id": "req_header"}, "req_header", id="header-fallback"),
            pytest.param({}, {}, None, id="absent"),
        ],
    )
    @respx.mock
    def test_error_exception_request_id(self, base_url, api_key, body, headers, expected):
        """Verify a raised error takes request_id from the body, falling back to the header."""
        # Given: An endpoint that returns 404 with the request id in the body, header, or neither
        respx.get(f"{base_url}/test").respond(
            404, json={"detail": "Not found", **body}, headers=headers
        )

        # When: Making a request that returns 404
        with (
            VClient(base_url=base_url, api_key=api_key) as client,
            pytest.raises(NotFoundError) as exc_info,
        ):
            ConcreteService(client)._get("/test")

        # Then: The error carries the expected request id
        assert exc_info.value.request_id == expected
