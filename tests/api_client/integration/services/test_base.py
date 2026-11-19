"""Tests for vweb.api_client.services.base."""

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
import respx

from tests.api_client.payloads import page, sent_params
from vweb.api_client import VClient
from vweb.api_client.constants import API_KEY_HEADER, IDEMPOTENCY_KEY_HEADER, ON_BEHALF_OF_HEADER
from vweb.api_client.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    ValidationError,
)
from vweb.api_client.services.base import BaseService

IN_PROGRESS = {
    "status": 409,
    "title": "Conflict",
    "detail": "A request with this idempotency key is still in progress.",
    "code": "IDEMPOTENCY_IN_PROGRESS",
}

Failure = Callable[[], respx.MockResponse | Exception]


def _status(code: int, headers: dict[str, str] | None = None, body: Any = None) -> Failure:
    """Return a factory for an error response, built fresh for each request."""
    return lambda: respx.MockResponse(code, json=body or {"detail": "Error"}, headers=headers)


def _raise(error: type[httpx2.TransportError], message: str = "Connection refused") -> Failure:
    """Return a factory for a transport error raised in place of a response."""
    return lambda: error(message)


RATE_LIMITED = _status(429, {"RateLimit": '"default";r=0;t=0'})
SERVER_ERROR = _status(500)
CONNECT_ERROR = _raise(httpx2.ConnectError)


def _send(service: BaseService, method: str, **kwargs: Any) -> httpx2.Response:
    """Send a request to /items through the service helper for ``method``."""
    if method in {"POST", "PUT", "PATCH"}:
        kwargs.setdefault("json", {"name": "x"})
    return getattr(service, f"_{method.lower()}")("/items", **kwargs)


@pytest.fixture
def mock_sleep(mocker):
    """Patch the retry sleep so retries run instantly and their waits are recorded."""
    return mocker.patch("vweb.api_client.services.base.time.sleep")


@pytest.fixture
def make_service(base_url, api_key):
    """Return a factory for services on clients built with the given config."""
    clients: list[VClient] = []

    def make(**client_kwargs: Any) -> BaseService:
        client = VClient(base_url=base_url, api_key=api_key, **client_kwargs)
        clients.append(client)
        return BaseService(client)

    yield make
    for client in clients:
        client.close()


def _delays(mock_sleep) -> list[float]:
    return [call[0][0] for call in mock_sleep.call_args_list]


class TestBaseServiceHTTPMethods:
    """Tests for BaseService HTTP method helpers."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "status"),
        [("GET", 200), ("POST", 201), ("PUT", 200), ("PATCH", 200), ("DELETE", 204)],
    )
    def test_http_methods(self, base_service, base_url, method, status):
        """Verify each helper sends its method, query params, and JSON body, and returns the response."""
        # Given: A mocked endpoint for the HTTP method
        route = respx.route(method=method, url=f"{base_url}/items").respond(
            status, json=None if method == "DELETE" else {"ok": True}
        )

        # When: Calling the corresponding helper with query params
        response = _send(base_service, method, params={"key": "value"})

        # Then: The request used the method, params, and body, and the response is returned
        request = route.calls.last.request
        assert request.method == method
        assert request.url.params["key"] == "value"
        if method in {"POST", "PUT", "PATCH"}:
            assert json.loads(request.content) == {"name": "x"}
        assert response.status_code == status

    @respx.mock
    def test_get_forwards_custom_headers(self, base_service, base_url):
        """Verify _get forwards caller-supplied headers such as Accept."""
        # Given: A mocked endpoint
        route = respx.get(f"{base_url}/custom").respond(200, json={})

        # When: Issuing a GET with a custom Accept header
        base_service._get("/custom", headers={"Accept": "application/zip"})

        # Then: The request carried the custom Accept header
        assert route.calls.last.request.headers["accept"] == "application/zip"


class TestBaseServiceErrorHandling:
    """Tests for BaseService error handling."""

    @pytest.mark.parametrize(
        ("status_code", "expected_exception"),
        [
            (400, ValidationError),
            (401, AuthenticationError),
            (403, AuthorizationError),
            (404, NotFoundError),
            (409, ConflictError),
            (413, PayloadTooLargeError),
            (422, UnprocessableEntityError),
            (429, RateLimitError),
            (500, ServerError),
            (502, ServerError),
            (503, ServerError),
            (418, APIError),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_error_status_codes_raise_correct_exception(
        self, base_service, base_url, status_code, expected_exception
    ):
        """Verify error status codes raise appropriate exceptions."""
        # Given: A mocked endpoint returning an error status
        respx.get(f"{base_url}/error").respond(status_code, json={"detail": "Error message"})

        # When/Then: Making a request raises the expected exception
        with pytest.raises(expected_exception) as exc_info:
            base_service._get("/error")

        assert exc_info.value.status_code == status_code
        assert "Error message" in exc_info.value.message

    @pytest.mark.parametrize(
        ("status", "body", "expected_exception"),
        [
            pytest.param(500, "Internal Server Error", ServerError, id="plain-text"),
            pytest.param(500, [{"msg": "bad gateway body"}], ServerError, id="json-list"),
            pytest.param(
                422,
                {"detail": [{"loc": ["body", "token"], "msg": "field required"}]},
                UnprocessableEntityError,
                id="list-detail",
            ),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_non_standard_error_body_gives_str_message(
        self, base_service, base_url, status, body, expected_exception
    ):
        """Verify an error body that is not an RFC 9457 object still maps to a str message."""
        # Given: An endpoint returning an unusual error body
        if isinstance(body, str):
            respx.get(f"{base_url}/error").respond(status, text=body)
        else:
            respx.get(f"{base_url}/error").respond(status, json=body)

        # When/Then: The mapped exception is raised with a str message
        with pytest.raises(expected_exception) as exc_info:
            base_service._get("/error")
        assert isinstance(exc_info.value.message, str)
        if isinstance(body, str):
            assert body in exc_info.value.message

    @respx.mock
    def test_validation_error_includes_invalid_parameters(self, base_service, base_url):
        """Verify ValidationError includes invalid_parameters from response."""
        # Given: A mocked endpoint returning a validation error with invalid_parameters
        respx.post(f"{base_url}/users").respond(
            400,
            json={
                "status": 400,
                "title": "Bad Request",
                "detail": "Validation failed for one or more fields.",
                "instance": "/api/v1/companies/abc123/users",
                "invalid_parameters": [
                    {"field": "name", "message": "Field required"},
                    {
                        "field": "role",
                        "message": "Input should be 'ADMIN', 'STORYTELLER' or 'PLAYER'",
                    },
                ],
            },
        )

        # When/Then: Making a request raises ValidationError with invalid_parameters
        with pytest.raises(ValidationError) as exc_info:
            base_service._post("/users", json={"email": "test@example.com"})

        assert exc_info.value.status_code == 400
        assert len(exc_info.value.invalid_parameters) == 2
        assert exc_info.value.invalid_parameters[0]["field"] == "name"
        assert exc_info.value.title == "Bad Request"
        assert exc_info.value.instance == "/api/v1/companies/abc123/users"

    @pytest.mark.parametrize(
        ("headers", "retry_after", "remaining"),
        [
            pytest.param({"Retry-After": "60"}, 60, None, id="retry-after"),
            pytest.param({}, None, None, id="no-headers"),
            pytest.param({"Retry-After": "invalid"}, None, None, id="invalid-retry-after"),
            pytest.param({"RateLimit": '"default";r=0;t=5'}, 5, 0, id="rate-limit-header"),
            pytest.param(
                {"RateLimit": '"default";r=0;t=10', "Retry-After": "60"},
                10,
                0,
                id="rate-limit-preferred-over-retry-after",
            ),
            pytest.param(
                {"RateLimit": '"default";r=3', "Retry-After": "30"},
                30,
                3,
                id="rate-limit-without-t-falls-back-to-retry-after",
            ),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_rate_limit_error_wait_and_remaining(
        self, base_service, base_url, headers, retry_after, remaining
    ):
        """Verify RateLimitError reads the wait and remaining tokens from the response headers."""
        # Given: A mocked endpoint returning 429 with the given headers
        respx.get(f"{base_url}/limited").respond(
            429, json={"title": "Too Many Requests", "detail": "Slow down"}, headers=headers
        )

        # When/Then: Making a request raises RateLimitError with the parsed values
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.status_code == 429
        assert exc_info.value.title == "Too Many Requests"
        assert exc_info.value.retry_after == retry_after
        assert exc_info.value.remaining == remaining


class TestBaseServiceIdempotency:
    """Tests for BaseService idempotency key support."""

    @respx.mock
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
    def test_explicit_idempotency_key(self, base_service, base_url, api_key, method):
        """Verify requests include explicit idempotency key and preserve other headers."""
        # Given: A mocked endpoint
        route = respx.route(method=method, url=f"{base_url}/items").respond(200, json={})

        # When: Making a request with explicit idempotency key
        _send(base_service, method, idempotency_key="my-key")

        # Then: Request includes the idempotency key header and other headers
        request = route.calls.last.request
        assert request.headers.get(IDEMPOTENCY_KEY_HEADER) == "my-key"
        assert request.headers.get(API_KEY_HEADER) == api_key

    @respx.mock
    def test_post_without_idempotency_key(self, base_service, base_url):
        """Verify POST request without idempotency key has no header."""
        # Given: A mocked POST endpoint
        route = respx.post(f"{base_url}/items").respond(201, json={})

        # When: Making a POST request without idempotency key
        base_service._post("/items", json={})

        # Then: Request does not include idempotency key header
        assert IDEMPOTENCY_KEY_HEADER not in route.calls.last.request.headers

    @respx.mock
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
    def test_auto_generates_unique_idempotency_keys_when_enabled(
        self, base_service_with_auto_idempotency, base_url, api_key, method
    ):
        """Verify each request gets its own generated UUID key and keeps other headers."""
        # Given: A mocked endpoint
        route = respx.route(method=method, url=f"{base_url}/items").respond(200, json={})

        # When: Making two requests without explicit idempotency keys
        _send(base_service_with_auto_idempotency, method)
        _send(base_service_with_auto_idempotency, method)

        # Then: Each request carries a distinct UUID key and the API key
        keys = [call.request.headers[IDEMPOTENCY_KEY_HEADER] for call in route.calls]
        assert len({str(uuid.UUID(key)) for key in keys}) == 2
        assert route.calls.last.request.headers.get(API_KEY_HEADER) == api_key

    @respx.mock
    def test_explicit_key_takes_precedence_over_auto(
        self, base_service_with_auto_idempotency, base_url
    ):
        """Verify explicit idempotency key takes precedence over a generated one."""
        # Given: A mocked POST endpoint
        route = respx.post(f"{base_url}/items").respond(201, json={})

        # When: Making a POST request with explicit idempotency key
        base_service_with_auto_idempotency._post("/items", json={}, idempotency_key="explicit-key")

        # Then: Request uses the explicit key
        assert route.calls.last.request.headers.get(IDEMPOTENCY_KEY_HEADER) == "explicit-key"


class TestBaseServicePagination:
    """Tests for BaseService pagination methods."""

    @respx.mock
    def test_get_paginated(self, base_service, base_url):
        """Verify _get_paginated parses the page's items and total."""
        # Given: A mocked paginated endpoint
        respx.get(f"{base_url}/items", params={"limit": "10", "offset": "0"}).respond(
            200, json=page({"id": 1}, {"id": 2})
        )

        # When: Calling _get_paginated
        result = base_service._get_paginated("/items")

        # Then: Returns a PaginatedResponse with correct data
        assert result.items == [{"id": 1}, {"id": 2}]
        assert result.total == 2

    @pytest.mark.parametrize(
        ("kwargs", "sent"),
        [
            pytest.param({"limit": 25, "offset": 50}, {"limit": "25", "offset": "50"}, id="custom"),
            pytest.param({"limit": 999}, {"limit": "100", "offset": "0"}, id="clamped"),
            pytest.param(
                {"limit": 5000, "max_limit": 1000},
                {"limit": "1000", "offset": "0"},
                id="clamped-to-custom-max",
            ),
        ],
    )
    @respx.mock
    def test_get_paginated_sends_limit_and_offset(self, base_service, base_url, kwargs, sent):
        """Verify _get_paginated sends the page window, clamping limit to max_limit."""
        # Given: A mocked endpoint
        route = respx.get(f"{base_url}/items").respond(200, json=page())

        # When: Calling _get_paginated
        base_service._get_paginated("/items", **kwargs)

        # Then: Request was made with the expected params
        assert sent_params(route) == sent

    @respx.mock
    def test_iter_all_pages(self, base_service, base_url):
        """Verify _iter_all_pages iterates through all pages."""
        # Given: Mocked endpoints for 3 pages of data
        for offset, ids in ((0, [1, 2]), (2, [3, 4]), (4, [5])):
            respx.get(f"{base_url}/items", params={"limit": "2", "offset": str(offset)}).respond(
                200,
                json=page(*({"id": i} for i in ids), limit=2, offset=offset, total=5),
            )

        # When: Iterating through all pages
        items = list(base_service._iter_all_pages("/items", limit=2))

        # Then: All items from all pages are returned
        assert [item["id"] for item in items] == [1, 2, 3, 4, 5]


class TestBaseServiceRateLimitHeaderParsing:
    """Tests for BaseService rate limit header parsing."""

    @pytest.mark.parametrize(
        ("header", "parameter", "expected"),
        [
            pytest.param('"default";r=10;t=5', "t", 5, id="t-value"),
            pytest.param('"default";r=47;t=0', "r", 47, id="r-value"),
            pytest.param('"default";r=10', "t", None, id="missing-parameter"),
            pytest.param('"burst";r=8;t=0, "sustained";r=95;t=0', "r", 8, id="first-policy"),
            pytest.param('"default";r=invalid;t=5', "r", None, id="non-numeric"),
        ],
    )
    def test_parse_rate_limit_header_value(self, header, parameter, expected):
        """Verify a RateLimit header parameter parses to an int, or None when absent or bad."""
        assert BaseService._parse_rate_limit_header_value(header, parameter) == expected


class TestBaseServiceRetry:
    """Tests for which failures are retried and how long each retry waits."""

    @pytest.mark.parametrize(
        ("client_kwargs", "method", "send_kwargs", "failure"),
        [
            pytest.param({}, "GET", {}, RATE_LIMITED, id="get-429"),
            pytest.param({}, "GET", {}, _status(500), id="get-500"),
            pytest.param({}, "GET", {}, _status(502), id="get-502"),
            pytest.param({}, "GET", {}, _status(503), id="get-503"),
            pytest.param({}, "GET", {}, _status(504), id="get-504"),
            pytest.param({}, "PUT", {}, SERVER_ERROR, id="put-500"),
            pytest.param({}, "DELETE", {}, SERVER_ERROR, id="delete-500"),
            pytest.param(
                {}, "POST", {"idempotency_key": "k"}, SERVER_ERROR, id="post-explicit-key-500"
            ),
            pytest.param(
                {"auto_idempotency_keys": True}, "POST", {}, SERVER_ERROR, id="post-auto-key-500"
            ),
            pytest.param({}, "GET", {}, CONNECT_ERROR, id="get-connect-error"),
            pytest.param({}, "GET", {}, _raise(httpx2.ReadTimeout), id="get-timeout"),
            pytest.param(
                {},
                "GET",
                {},
                _raise(httpx2.RemoteProtocolError, "Server disconnected"),
                id="get-dropped-connection",
            ),
            pytest.param(
                {}, "GET", {}, _raise(httpx2.ReadError, "Connection reset"), id="get-read-error"
            ),
            pytest.param(
                {},
                "POST",
                {"idempotency_key": "k"},
                CONNECT_ERROR,
                id="post-explicit-key-connect-error",
            ),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_retryable_failure_is_retried_then_succeeds(
        self, make_service, base_url, client_kwargs, method, send_kwargs, failure
    ):
        """Verify a transient failure on a safe-to-repeat request is retried once and succeeds."""
        # Given: An endpoint that fails once, then succeeds
        route = respx.route(method=method, url=f"{base_url}/items").mock(
            side_effect=[failure(), respx.MockResponse(200, json={"ok": True})]
        )

        # When: Sending the request
        response = _send(make_service(**client_kwargs), method, **send_kwargs)

        # Then: The request was retried and the success response is returned
        assert route.call_count == 2
        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("client_kwargs", "method", "failure", "expected_exception"),
        [
            pytest.param({}, "GET", _status(501), ServerError, id="get-501-not-retryable"),
            pytest.param({}, "POST", SERVER_ERROR, ServerError, id="post-no-key-500"),
            pytest.param({}, "PATCH", SERVER_ERROR, ServerError, id="patch-no-key-500"),
            pytest.param(
                {}, "POST", CONNECT_ERROR, APIConnectionError, id="post-no-key-connect-error"
            ),
            pytest.param(
                {},
                "GET",
                _raise(httpx2.UnsupportedProtocol, "unsupported protocol"),
                APIConnectionError,
                id="get-non-transient-transport-error",
            ),
            pytest.param(
                {"auto_idempotency_keys": True},
                "POST",
                _status(409, body={"detail": "Idempotency key reused"}),
                ConflictError,
                id="post-other-409",
            ),
            pytest.param(
                {},
                "POST",
                _status(409, {"Retry-After": "1"}, IN_PROGRESS),
                ConflictError,
                id="post-no-key-in-progress-409",
            ),
            pytest.param(
                {},
                "DELETE",
                _status(409, {"Retry-After": "1"}, IN_PROGRESS),
                ConflictError,
                id="delete-in-progress-409",
            ),
            pytest.param(
                {"auto_retry_rate_limit": False},
                "GET",
                RATE_LIMITED,
                RateLimitError,
                id="retries-off-429",
            ),
            pytest.param(
                {"auto_retry_rate_limit": False},
                "GET",
                SERVER_ERROR,
                ServerError,
                id="retries-off-500",
            ),
            pytest.param(
                {"auto_retry_rate_limit": False},
                "GET",
                CONNECT_ERROR,
                APIConnectionError,
                id="retries-off-connect-error",
            ),
            pytest.param(
                {"auto_retry_rate_limit": False, "auto_idempotency_keys": True},
                "POST",
                _status(409, {"Retry-After": "1"}, IN_PROGRESS),
                ConflictError,
                id="retries-off-in-progress-409",
            ),
        ],
    )
    @respx.mock
    def test_failure_is_raised_without_retry(
        self, make_service, base_url, mock_sleep, client_kwargs, method, failure, expected_exception
    ):
        """Verify a failure that is not safe or not allowed to retry is raised after one call."""
        # Given: An endpoint that always fails
        route = respx.route(method=method, url=f"{base_url}/items").mock(
            side_effect=lambda _request: _raise_or_return(failure)
        )

        # When/Then: Sending the request raises the mapped error
        with pytest.raises(expected_exception) as exc_info:
            _send(make_service(**client_kwargs), method)

        # Then: Only one request was made and no wait happened
        assert route.call_count == 1
        mock_sleep.assert_not_called()
        if expected_exception is APIConnectionError:
            assert isinstance(exc_info.value.__cause__, httpx2.TransportError)

    @pytest.mark.parametrize(
        ("failure", "expected_exception"),
        [
            pytest.param(_status(429, {"RateLimit": '"d";r=0;t=1'}), RateLimitError, id="429"),
            pytest.param(SERVER_ERROR, ServerError, id="500"),
            pytest.param(CONNECT_ERROR, APIConnectionError, id="connect-error"),
            pytest.param(_raise(httpx2.ReadTimeout), APIConnectionError, id="timeout"),
        ],
    )
    @respx.mock
    @pytest.mark.usefixtures("mock_sleep")
    def test_persistent_failure_exhausts_retries(
        self, vclient, base_service, base_url, failure, expected_exception
    ):
        """Verify a failure that never clears is raised after every attempt is used."""
        # Given: An endpoint that always fails
        route = respx.get(f"{base_url}/items").mock(
            side_effect=lambda _request: _raise_or_return(failure)
        )

        # When/Then: The error is raised once retries run out
        with pytest.raises(expected_exception) as exc_info:
            base_service._get("/items")

        # Then: Every attempt was used, and a transport error is kept as the cause
        assert route.call_count == vclient._config.max_retries + 1
        if expected_exception is APIConnectionError:
            assert isinstance(exc_info.value.__cause__, httpx2.TransportError)
            assert exc_info.value.status_code is None

    @respx.mock
    def test_connection_error_message_names_the_error(self, make_service, base_url):
        """Verify a connection error message carries the transport text, or its type when empty."""
        # Given: Endpoints that refuse the connection or time out with no message
        respx.get(f"{base_url}/refused").mock(side_effect=httpx2.ConnectError("Connection refused"))
        respx.get(f"{base_url}/silent").mock(side_effect=httpx2.ReadTimeout(""))
        service = make_service(auto_retry_rate_limit=False)

        # When/Then: Each message reads as a sentence about reaching the API
        with pytest.raises(
            APIConnectionError, match=r"^Could not reach the API: Connection refused$"
        ):
            service._get("/refused")
        with pytest.raises(APIConnectionError, match=r"^Could not reach the API: ReadTimeout$"):
            service._get("/silent")

    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(RATE_LIMITED, id="429"),
            pytest.param(SERVER_ERROR, id="500"),
            pytest.param(CONNECT_ERROR, id="connect-error"),
        ],
    )
    @respx.mock
    def test_backoff_doubles_between_retries(self, base_service, base_url, mock_sleep, failure):
        """Verify retries without a server wait double from the 0.5s default, plus jitter."""
        # Given: An endpoint that fails twice then succeeds
        respx.get(f"{base_url}/items").mock(
            side_effect=[failure(), failure(), respx.MockResponse(200, json={})]
        )

        # When: Making a request
        base_service._get("/items")

        # Then: The waits doubled, each with at most 25% jitter
        delays = _delays(mock_sleep)
        assert len(delays) == 2
        assert 0.5 <= delays[0] <= 0.625
        assert 1.0 <= delays[1] <= 1.25

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({"RateLimit": '"default";r=0;t=1'}, id="rate-limit-t"),
            pytest.param({"Retry-After": "1"}, id="retry-after"),
        ],
    )
    @respx.mock
    def test_rate_limit_retry_waits_the_server_time(
        self, base_service, base_url, mock_sleep, headers
    ):
        """Verify every 429 retry waits the server's time plus jitter, without doubling."""
        # Given: An endpoint that returns 429 twice then succeeds
        failure = _status(429, headers)
        respx.get(f"{base_url}/items").mock(
            side_effect=[failure(), failure(), respx.MockResponse(200, json={})]
        )

        # When: Making a request
        base_service._get("/items")

        # Then: Each wait is 1s plus at most 25% jitter
        delays = _delays(mock_sleep)
        assert len(delays) == 2
        assert all(1.0 <= delay <= 1.25 for delay in delays)


def _raise_or_return(failure: Failure) -> respx.MockResponse:
    """Return the failure's response, or raise it when it is a transport error."""
    result = failure()
    if isinstance(result, Exception):
        raise result
    return result


class TestBaseServiceIdempotencyInProgressRetry:
    """Tests for retrying the 409 the API returns while an idempotent request is in progress."""

    @respx.mock
    def test_in_progress_409_is_retried_then_succeeds(
        self, base_service_with_auto_idempotency, base_url, mock_sleep
    ):
        """Verify an in-progress 409 is retried with the same key and waits per Retry-After."""
        # Given: An endpoint that reports in progress once, then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                respx.MockResponse(
                    409,
                    json=IN_PROGRESS,
                    headers={"Retry-After": "1", "RateLimit": '"default";r=5;t=30'},
                ),
                respx.MockResponse(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request
        response = base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The retry succeeded with the same idempotency key
        assert response.json() == {"id": 1}
        keys = [call.request.headers[IDEMPOTENCY_KEY_HEADER] for call in route.calls]
        assert len(keys) == 2
        assert keys[0] == keys[1]

        # Then: The wait came from Retry-After, not the RateLimit t= value
        mock_sleep.assert_called_once()
        assert 1.0 <= mock_sleep.call_args[0][0] <= 1.25

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({"RateLimit": '"default";r=5;t=30'}, id="no-retry-after"),
            pytest.param(
                {"Retry-After": "soon", "RateLimit": '"default";r=5;t=30'},
                id="invalid-retry-after",
            ),
        ],
    )
    @respx.mock
    def test_in_progress_409_without_usable_retry_after_uses_backoff(
        self, base_service_with_auto_idempotency, base_url, mock_sleep, headers
    ):
        """Verify an in-progress 409 with no usable Retry-After waits the backoff, not t=."""
        # Given: An endpoint that reports in progress once, then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                respx.MockResponse(409, json=IN_PROGRESS, headers=headers),
                respx.MockResponse(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request
        base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The request was retried once after the 0.5s first-attempt backoff
        assert route.call_count == 2
        mock_sleep.assert_called_once()
        assert 0.5 <= mock_sleep.call_args[0][0] <= 0.625

    @respx.mock
    def test_in_progress_409_exhausts_retries(
        self,
        base_service_with_auto_idempotency,
        vclient_with_auto_idempotency,
        base_url,
        mock_sleep,
    ):
        """Verify a persistent in-progress 409 raises ConflictError after all retries."""
        # Given: An endpoint that always reports in progress
        route = respx.post(f"{base_url}/items").mock(
            return_value=respx.MockResponse(409, json=IN_PROGRESS, headers={"Retry-After": "1"})
        )

        # When: Making a POST request
        with pytest.raises(ConflictError) as exc_info:
            base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The error identifies the in-progress conflict and its wait
        assert exc_info.value.is_idempotency_in_progress
        assert exc_info.value.retry_after == 1

        # Then: Every attempt was used, each wait the 1s Retry-After plus jitter
        config = vclient_with_auto_idempotency._config
        assert route.call_count == config.max_retries + 1
        delays = _delays(mock_sleep)
        assert len(delays) == config.max_retries
        assert all(1.0 <= delay <= 1.25 for delay in delays)

    @respx.mock
    def test_in_progress_409_is_retried_for_keyed_put(self, base_service, base_url, mock_sleep):
        """Verify an in-progress 409 is retried for a PUT that carries an explicit key."""
        # Given: An endpoint that reports in progress once, then succeeds
        route = respx.put(f"{base_url}/items/1").mock(
            side_effect=[
                respx.MockResponse(409, json=IN_PROGRESS, headers={"Retry-After": "1"}),
                respx.MockResponse(200, json={"id": 1}),
            ]
        )

        # When: Making a PUT request with an explicit idempotency key
        response = base_service._put("/items/1", json={"name": "x"}, idempotency_key="k-1")

        # Then: The retry succeeded with the same key
        assert response.json() == {"id": 1}
        assert [c.request.headers[IDEMPOTENCY_KEY_HEADER] for c in route.calls] == ["k-1", "k-1"]
        mock_sleep.assert_called_once()


class ConcreteServiceWithOnBehalfOf(BaseService):
    """Concrete implementation with on_behalf_of for testing."""

    def __init__(self, client: VClient, on_behalf_of: str | None = None) -> None:
        super().__init__(client)
        self._on_behalf_of = on_behalf_of


class TestOnBehalfOfHeader:
    """Tests for On-Behalf-Of header injection."""

    @pytest.mark.parametrize("on_behalf_of", ["user-uuid-123", None])
    @respx.mock
    def test_on_behalf_of_header_sent_only_when_set(self, vclient, base_url, on_behalf_of):
        """Verify the On-Behalf-Of header carries the acting user and is absent without one."""
        # Given: A service with or without an acting user
        service = ConcreteServiceWithOnBehalfOf(vclient, on_behalf_of=on_behalf_of)
        route = respx.get(f"{base_url}/test").respond(200, json={})

        # When: Making a GET request
        service._get("/test")

        # Then: The header matches the acting user, or is absent
        assert route.calls.last.request.headers.get(ON_BEHALF_OF_HEADER) == on_behalf_of

    @respx.mock
    def test_on_behalf_of_coexists_with_idempotency_key(self, vclient, base_url):
        """Verify On-Behalf-Of header coexists with idempotency key header."""
        # Given: A service with on_behalf_of set and an explicit idempotency key
        service = ConcreteServiceWithOnBehalfOf(vclient, on_behalf_of="user-uuid-123")
        route = respx.post(f"{base_url}/test").respond(200, json={})

        # When: Making a POST request with an explicit idempotency key
        service._post("/test", json={}, idempotency_key="idem-key-456")

        # Then: Both headers are present in the request
        request = route.calls.last.request
        assert request.headers[ON_BEHALF_OF_HEADER] == "user-uuid-123"
        assert request.headers[IDEMPOTENCY_KEY_HEADER] == "idem-key-456"


class TestBaseServiceRetryLimits:
    """Tests for the per-wait cap and total time budget on retries."""

    @respx.mock
    def test_backoff_is_capped_at_max_retry_delay(self, make_service, base_url, mock_sleep):
        """Verify a backoff longer than max_retry_delay waits only max_retry_delay."""
        # Given: An endpoint that returns 503 once then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                respx.MockResponse(503, json={"detail": "Unavailable"}),
                respx.MockResponse(200, json={"success": True}),
            ]
        )

        # When: Making a GET with a base delay longer than the cap
        make_service(retry_delay=5.0, max_retry_delay=1.5)._get("/test")

        # Then: The wait was exactly the cap, jitter included
        mock_sleep.assert_called_once_with(1.5)

    @pytest.mark.parametrize(
        ("method", "kwargs", "failure", "expected_exception"),
        [
            pytest.param("GET", {}, _status(429, {"Retry-After": "30"}), RateLimitError, id="429"),
            pytest.param(
                "POST",
                {"idempotency_key": "k"},
                _status(409, {"Retry-After": "10"}, IN_PROGRESS),
                ConflictError,
                id="in-progress-409",
            ),
        ],
    )
    @respx.mock
    def test_retry_after_above_cap_raises_without_waiting(
        self, base_service, base_url, mock_sleep, method, kwargs, failure, expected_exception
    ):
        """Verify a server wait longer than max_retry_delay raises at once."""
        # Given: An endpoint that asks the client to wait longer than the cap
        route = respx.route(method=method, url=f"{base_url}/items").mock(
            side_effect=lambda _request: failure()
        )

        # When/Then: The error is raised after one call
        with pytest.raises(expected_exception):
            _send(base_service, method, **kwargs)

        # Then: No wait and no retry happened
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.parametrize(
        ("failure", "expected_exception"),
        [
            pytest.param(_status(503), ServerError, id="503"),
            pytest.param(CONNECT_ERROR, APIConnectionError, id="connect-error"),
        ],
    )
    @respx.mock
    def test_retry_stops_when_budget_would_be_exceeded(
        self, make_service, base_url, mocker, mock_sleep, failure, expected_exception
    ):
        """Verify the last error is raised when the next wait would overrun the budget."""
        # Given: A clock where the first attempt takes 9.8 of the 10 second budget
        mocker.patch("vweb.api_client.services.base.time.monotonic", side_effect=[100.0, 109.8])

        # Given: An endpoint that always fails
        route = respx.get(f"{base_url}/test").mock(
            side_effect=lambda _request: _raise_or_return(failure)
        )

        # When/Then: The error is raised without a retry
        with pytest.raises(expected_exception):
            make_service(retry_budget=10.0)._get("/test")

        # Then: Only the first attempt was made
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    def test_vclient_defaults_suit_a_web_request(self, vclient):
        """Verify the default retry settings keep a call short enough for a web worker."""
        # Given/When: A client built with default retry settings
        config = vclient._config

        # Then: The defaults are a few short retries inside a 10 second budget
        assert config.max_retries == 2
        assert config.retry_delay == 0.5
        assert config.max_retry_delay == 2.0
        assert config.retry_budget == 10.0
