"""Tests for structured logging across the vclient package."""

import logging
from typing import Any

import httpx
import httpx2
import pytest
import respx
from loguru import logger

from vweb.api_client import VClient
from vweb.api_client.exceptions import NotFoundError
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


def _vclient_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return all caplog records from the vclient namespace."""
    return [r for r in caplog.records if r.name.startswith("vweb.api_client")]


def _find_record(caplog: pytest.LogCaptureFixture, message: str) -> Any:
    """Find the first vclient record matching the given message."""
    for r in caplog.records:
        if r.name.startswith("vweb.api_client") and r.message == message:
            return r
    return None


class TestLoggingInitialization:
    """Tests for logging initialization and default behavior."""

    @respx.mock
    def test_logging_disabled_by_default(self, base_url, api_key, caplog):
        """Verify no vclient logs appear without explicit enable."""
        # Given: A client with logging at default state (disabled)
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: No vclient log records appear
        assert len(_vclient_records(caplog)) == 0

    @respx.mock
    def test_logging_enabled_captures_request_logs(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify logs appear after explicit enable."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a request with logging enabled
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: vclient log records appear
        assert len(_vclient_records(caplog)) > 0


class TestRequestLogging:
    """Tests for HTTP request lifecycle logging."""

    @respx.mock
    def test_log_request_start_and_response(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify 'Send request' logs at TRACE and 'Request complete' at DEBUG with fields."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # TRACE (loguru level 5) so the send line is captured alongside DEBUG records
        # When: Making a GET request
        with (
            caplog.at_level(TRACE_LEVEL, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: "Send request" is present at TRACE with correct structured fields
        send = _find_record(caplog, "Send request")
        assert send is not None
        assert send.levelno == TRACE_LEVEL
        assert send.extra["method"] == "GET"
        assert send.extra["url"] == "/test"

        # Then: "Request complete" is present at DEBUG with correct structured fields
        receive = _find_record(caplog, "Request complete")
        assert receive is not None
        assert receive.levelno == logging.DEBUG
        assert receive.extra["method"] == "GET"
        assert receive.extra["url"] == "/test"
        assert receive.extra["status"] == 200

    @respx.mock
    def test_log_request_includes_query_params(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify query params appear in request logs so paginated calls are distinguishable."""
        # Given: A mocked endpoint that accepts pagination params
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request with limit/offset params
        with (
            caplog.at_level(TRACE_LEVEL, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test", params={"limit": 50, "offset": 100})

        # Then: Both the send and complete lines carry the params for disambiguation
        send = _find_record(caplog, "Send request")
        assert send is not None
        assert send.extra["params"] == {"limit": 50, "offset": 100}

        receive = _find_record(caplog, "Request complete")
        assert receive is not None
        assert receive.extra["params"] == {"limit": 50, "offset": 100}

    @respx.mock
    def test_log_request_params_none_when_absent(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify the params field is present (None) when no query params are sent."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request without params
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: The params field is present and None
        receive = _find_record(caplog, "Request complete")
        assert receive is not None
        assert receive.extra["params"] is None

    @respx.mock
    def test_log_error_includes_query_params(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify error logs carry query params so a failing paginated call is identifiable."""
        # Given: An endpoint that returns 404
        respx.get(f"{base_url}/test").respond(404, json={"detail": "Not found"})

        # When: Making a paginated request that returns 404
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test", params={"limit": 25, "offset": 0})

        # Then: The 404 log carries the params
        record = _find_record(caplog, "Return 404")
        assert record is not None
        assert record.extra["params"] == {"limit": 25, "offset": 0}

    @respx.mock
    def test_log_send_request_hidden_at_debug(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify 'Send request' is suppressed when capturing only at DEBUG and above."""
        # Given: A mocked endpoint
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a GET request
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: only the single "Request complete" line shows; no "Send request" noise
        assert _find_record(caplog, "Send request") is None
        assert _find_record(caplog, "Request complete") is not None

    @respx.mock
    def test_log_retry_on_rate_limit(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify 'Retry after rate limit' logged at WARNING with structured fields."""
        # Given: Sleep is mocked to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 429 then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(
                    429,
                    json={"detail": "Rate limited"},
                    headers={"RateLimit": '"default";r=0;t=3'},
                ),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        # When: Making a request that gets rate limited
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: Rate limit retry warning is present with structured fields
        record = _find_record(caplog, "Retry after rate limit")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"

        # Then: The wait was the header's 3 seconds plus at most 25% jitter
        mock_sleep.assert_called_once()
        assert 3.0 <= mock_sleep.call_args[0][0] <= 3.75

    @respx.mock
    def test_log_retry_on_server_error(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify 'Retry after server error' logged at WARNING with structured fields."""
        # Given: Sleep is mocked to avoid delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        # When: Making a request that hits a server error
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: Server error retry warning is present with structured fields
        record = _find_record(caplog, "Retry after server error")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"
        assert record.extra["status"] == 500

    @respx.mock
    def test_log_retry_on_network_error(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify 'Retry after network error' logged at WARNING with structured fields."""
        # Given: Sleep is mocked to avoid delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx2.ConnectError("Connection refused"),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        # When: Making a request that hits a network error
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: Network error retry warning is present with structured fields
        record = _find_record(caplog, "Retry after network error")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"
        assert record.extra["error_type"] == "ConnectError"

    @respx.mock
    def test_log_retry_on_idempotency_in_progress(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify an in-progress 409 retry logs one WARNING with structured fields."""
        # Given: Sleep is mocked to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports the idempotent request in progress, then succeeds
        respx.post(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(
                    409,
                    json={"detail": "In progress", "code": "IDEMPOTENCY_IN_PROGRESS"},
                    headers={"Retry-After": "3"},
                ),
                httpx.Response(201, json={"ok": True}),
            ]
        )

        # When: Making a POST request with an idempotency key
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._post("/test", json={"data": "value"}, idempotency_key="key-1")

        # Then: The retry warning is present with structured fields
        record = _find_record(caplog, "Retry after idempotency conflict")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "POST"
        assert record.extra["url"] == "/test"
        assert record.extra["status"] == 409
        assert record.extra["attempt"] == 1
        assert record.extra["max_attempts"] == client._config.max_retries + 1
        assert 3.0 <= record.extra["delay"] <= 3.75
        mock_sleep.assert_called_once_with(record.extra["delay"])

        # Then: The expected conflict itself is logged at DEBUG, not as a second WARNING
        conflict_record = _find_record(caplog, "Return 409 conflict")
        assert conflict_record is not None
        assert conflict_record.levelno == logging.DEBUG

    @respx.mock
    def test_log_max_retries_exhausted(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify 'Exhaust retries' logged at ERROR with structured fields."""
        # Given: Sleep is mocked to avoid delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that always returns 429
        respx.get(f"{base_url}/test").respond(
            429,
            json={"detail": "Rate limited"},
            headers={"RateLimit": '"default";r=0;t=1'},
        )

        # When: Making a request that exhausts retries
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: Exhaust retries error is present with structured fields
        record = _find_record(caplog, "Exhaust retries")
        assert record is not None
        assert record.levelno == logging.ERROR
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"

    @respx.mock
    def test_log_failure_without_retries(
        self, base_url, api_key, caplog, mocker, enable_vclient_logging
    ):
        """Verify a failure with retries off is not reported as exhausted retries."""
        # Given: Sleep is mocked and an endpoint that always returns 429
        mocker.patch("vweb.api_client.services.base.time.sleep")
        respx.get(f"{base_url}/test").respond(429, json={"detail": "Rate limited"})

        # When: Making a request with automatic retries off
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key, auto_retry_rate_limit=False) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: A single warning is logged and no exhausted-retries error
        assert _find_record(caplog, "Exhaust retries") is None
        record = _find_record(caplog, "Fail with automatic retries off")
        assert record is not None
        assert record.levelno == logging.WARNING


class TestErrorClassificationLogging:
    """Tests for error classification logging in _raise_for_status."""

    @respx.mock
    def test_log_authentication_error(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Fail authentication' logged at ERROR with structured fields for 401."""
        # Given: An endpoint that returns 401
        respx.get(f"{base_url}/test").respond(401, json={"detail": "Unauthorized"})

        # When: Making a request that fails authentication
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: Authentication error is present at ERROR with structured fields
        record = _find_record(caplog, "Fail authentication")
        assert record is not None
        assert record.levelno == logging.ERROR
        assert record.extra["status"] == 401

    @respx.mock
    def test_log_authorization_error(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Deny authorization' logged at ERROR with structured fields for 403."""
        # Given: An endpoint that returns 403
        respx.get(f"{base_url}/test").respond(403, json={"detail": "Forbidden"})

        # When: Making a request that fails authorization
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: Authorization error is present at ERROR with structured fields
        record = _find_record(caplog, "Deny authorization")
        assert record is not None
        assert record.levelno == logging.ERROR
        assert record.extra["status"] == 403

    @respx.mock
    def test_log_not_found_at_debug(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Return 404' logged at DEBUG with structured fields."""
        # Given: An endpoint that returns 404
        respx.get(f"{base_url}/test").respond(404, json={"detail": "Not found"})

        # When: Making a request to a missing resource
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: 404 message is present at DEBUG with structured fields
        record = _find_record(caplog, "Return 404")
        assert record is not None
        assert record.levelno == logging.DEBUG
        assert record.extra["status"] == 404
        assert record.extra["method"] == "GET"
        assert record.extra["url"] == "/test"

    @respx.mock
    def test_log_validation_error(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Reject with validation error' logged at WARNING with structured fields."""
        # Given: An endpoint that returns 400
        respx.post(f"{base_url}/test").respond(400, json={"detail": "Validation failed"})

        # When: Making a request that fails validation
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._post("/test", json={"bad": "data"})

        # Then: Validation error warning is present with structured fields
        record = _find_record(caplog, "Reject with validation error")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "POST"
        assert record.extra["url"] == "/test"

    @respx.mock
    def test_log_conflict_error(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Return 409 conflict' logged at WARNING with structured fields."""
        # Given: An endpoint that returns 409
        respx.post(f"{base_url}/test").respond(409, json={"detail": "Conflict"})

        # When: Making a request that conflicts
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._post("/test", json={"data": "value"})

        # Then: Conflict warning is present with structured fields
        record = _find_record(caplog, "Return 409 conflict")
        assert record is not None
        assert record.levelno == logging.WARNING
        assert record.extra["method"] == "POST"
        assert record.extra["url"] == "/test"


class TestClientLifecycleLogging:
    """Tests for VClient lifecycle logging."""

    def test_log_client_initialization(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Initialize VClient' logged at INFO with structured fields."""
        # When: Creating a client
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key),
        ):
            pass

        # Then: Initialization message is present at INFO with structured fields
        record = _find_record(caplog, "Initialize VClient")
        assert record is not None
        assert record.levelno == logging.INFO
        assert record.extra["base_url"] == base_url

    def test_log_client_close(self, base_url, api_key, caplog, enable_vclient_logging):
        """Verify 'Close VClient' logged at INFO with structured fields."""
        with caplog.at_level(logging.DEBUG, logger="vweb.api_client"):
            # When: Closing a client
            client = VClient(base_url=base_url, api_key=api_key)
            client.close()

        # Then: Close message is present at INFO with structured fields
        record = _find_record(caplog, "Close VClient")
        assert record is not None
        assert record.levelno == logging.INFO
        assert record.extra["base_url"] == base_url


class TestRequestIdLogging:
    """Tests for request_id in structured log output."""

    @respx.mock
    def test_success_response_logs_request_id(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify request_id from X-Request-Id header appears in success log."""
        # Given: An endpoint that returns 200 with X-Request-Id header
        respx.get(f"{base_url}/test").respond(
            200,
            json={"ok": True},
            headers={"X-Request-Id": "req_success123"},
        )

        # When: Making a successful request
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: Request complete log includes request_id
        record = _find_record(caplog, "Request complete")
        assert record is not None
        assert record.extra["request_id"] == "req_success123"

    @respx.mock
    def test_success_response_without_request_id_header(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify success log omits request_id when header is absent."""
        # Given: An endpoint that returns 200 without X-Request-Id header
        respx.get(f"{base_url}/test").respond(200, json={"ok": True})

        # When: Making a successful request
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            service._get("/test")

        # Then: Request complete log does not include request_id
        record = _find_record(caplog, "Request complete")
        assert record is not None
        assert "request_id" not in record.extra

    @respx.mock
    def test_error_response_logs_request_id(
        self, base_url, api_key, caplog, enable_vclient_logging
    ):
        """Verify request_id appears in error log for 404 via header fallback."""
        # Given: An endpoint that returns 404 with X-Request-Id header but no body request_id
        respx.get(f"{base_url}/test").respond(
            404,
            json={"detail": "Not found"},
            headers={"X-Request-Id": "req_error456"},
        )

        # When: Making a request that returns 404
        with (
            caplog.at_level(logging.DEBUG, logger="vweb.api_client"),
            VClient(base_url=base_url, api_key=api_key) as client,
        ):
            service = ConcreteService(client)
            with pytest.raises(Exception):  # noqa: B017
                service._get("/test")

        # Then: Error log includes request_id
        record = _find_record(caplog, "Return 404")
        assert record is not None
        assert record.extra["request_id"] == "req_error456"

    @respx.mock
    def test_error_exception_has_request_id_from_body(self, base_url, api_key):
        """Verify raised exception has request_id from response body."""
        # Given: An endpoint that returns 404 with request_id in body
        respx.get(f"{base_url}/test").respond(
            404,
            json={
                "detail": "Not found",
                "request_id": "req_body789",
            },
        )

        # When: Making a request that returns 404
        with VClient(base_url=base_url, api_key=api_key) as client:
            service = ConcreteService(client)
            with pytest.raises(NotFoundError) as exc_info:
                service._get("/test")

        # Then: Exception has request_id from body
        assert exc_info.value.request_id == "req_body789"

    @respx.mock
    def test_error_exception_falls_back_to_header(self, base_url, api_key):
        """Verify raised exception gets request_id from header when body lacks it."""
        # Given: An endpoint that returns 404 with header but no body request_id
        respx.get(f"{base_url}/test").respond(
            404,
            json={"detail": "Not found"},
            headers={"X-Request-Id": "req_header_fallback"},
        )

        # When: Making a request that returns 404
        with VClient(base_url=base_url, api_key=api_key) as client:
            service = ConcreteService(client)
            with pytest.raises(NotFoundError) as exc_info:
                service._get("/test")

        # Then: Exception has request_id from header fallback
        assert exc_info.value.request_id == "req_header_fallback"

    @respx.mock
    def test_error_exception_no_request_id(self, base_url, api_key):
        """Verify raised exception has no request_id when neither body nor header has it."""
        # Given: An endpoint that returns 404 without any request_id
        respx.get(f"{base_url}/test").respond(
            404,
            json={"detail": "Not found"},
        )

        # When: Making a request that returns 404
        with VClient(base_url=base_url, api_key=api_key) as client:
            service = ConcreteService(client)
            with pytest.raises(NotFoundError) as exc_info:
                service._get("/test")

        # Then: Exception has no request_id
        assert exc_info.value.request_id is None
