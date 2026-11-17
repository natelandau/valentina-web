"""Tests for vweb.api_client.services.base."""

import httpx
import httpx2
import pytest
import respx

from vweb.api_client import VClient
from vweb.api_client.constants import API_KEY_HEADER, IDEMPOTENCY_KEY_HEADER, ON_BEHALF_OF_HEADER
from vweb.api_client.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    ValidationError,
)
from vweb.api_client.models.pagination import PaginatedResponse
from vweb.api_client.services.base import BaseService


class TestBaseServiceRequest:
    """Tests for BaseService._request method."""

    @respx.mock
    def test_successful_get_request(self, base_service, base_url):
        """Verify successful GET requests return response."""
        # Given: A mocked API endpoint that returns success
        route = respx.get(f"{base_url}/test-path").respond(200, json={"success": True})

        # When: Making a GET request
        response = base_service._get("/test-path")

        # Then: Response contains expected data
        assert route.called
        assert response.status_code == 200
        assert response.json() == {"success": True}

    @respx.mock
    def test_request_with_params(self, base_service, base_url):
        """Verify query parameters are passed correctly."""
        # Given: A mocked endpoint expecting specific params
        route = respx.get(f"{base_url}/test", params={"key": "value"}).respond(200, json={})

        # When: Making a GET request with params
        base_service._get("/test", params={"key": "value"})

        # Then: Request was made with correct params
        assert route.called

    @respx.mock
    def test_post_with_json_body(self, base_service, base_url):
        """Verify POST request sends JSON body correctly."""
        # Given: A mocked POST endpoint
        route = respx.post(f"{base_url}/items").respond(201, json={"id": 1})

        # When: Making a POST request with JSON body
        response = base_service._post("/items", json={"name": "test"})

        # Then: Request was made with correct body
        assert route.called
        assert response.status_code == 201
        request = route.calls.last.request
        assert b'"name"' in request.content


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
            (422, UnprocessableEntityError),
            (429, RateLimitError),
            (500, ServerError),
            (502, ServerError),
            (503, ServerError),
            (418, APIError),
        ],
    )
    @respx.mock
    def test_error_status_codes_raise_correct_exception(
        self, base_service, base_url, status_code, expected_exception, mocker
    ):
        """Verify error status codes raise appropriate exceptions."""
        # Given: Mock sleep to avoid delays on 429 retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning an error status
        respx.get(f"{base_url}/error").respond(status_code, json={"detail": "Error message"})

        # When/Then: Making a request raises the expected exception
        with pytest.raises(expected_exception) as exc_info:
            base_service._get("/error")

        assert exc_info.value.status_code == status_code
        assert "Error message" in exc_info.value.message

    @respx.mock
    def test_error_with_non_json_response(self, base_service, base_url, mocker):
        """Verify error handling when response is not JSON."""
        # Given: Mock time.sleep so the 5xx retries do not wait
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning plain text error
        respx.get(f"{base_url}/error").respond(500, text="Internal Server Error")

        # When/Then: Making a request raises ServerError with text message
        with pytest.raises(ServerError) as exc_info:
            base_service._get("/error")

        assert "Internal Server Error" in exc_info.value.message

    @respx.mock
    def test_error_with_json_list_body(self, base_service, base_url, mocker):
        """Verify a JSON array error body still raises the mapped exception."""
        # Given: Mock time.sleep so the 5xx retries do not wait
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint returning 500 with a JSON list body
        respx.get(f"{base_url}/error").respond(500, json=[{"msg": "bad gateway body"}])

        # When/Then: The mapped ServerError is raised, not AttributeError
        with pytest.raises(ServerError) as exc_info:
            base_service._get("/error")
        assert isinstance(exc_info.value.message, str)

    @respx.mock
    def test_error_with_list_detail(self, base_service, base_url):
        """Verify a list-typed detail field yields a str message."""
        # Given: A 422 with FastAPI-style list detail
        respx.get(f"{base_url}/error").respond(
            422, json={"detail": [{"loc": ["body", "token"], "msg": "field required"}]}
        )

        # When/Then: The message is a string, not the raw list
        with pytest.raises(UnprocessableEntityError) as exc_info:
            base_service._get("/error")
        assert isinstance(exc_info.value.message, str)

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

    @respx.mock
    def test_rate_limit_error_includes_retry_after(self, base_service, base_url, mocker):
        """Verify RateLimitError includes retry_after from Retry-After header."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning 429 with Retry-After header
        respx.get(f"{base_url}/limited").respond(
            429,
            json={
                "status": 429,
                "title": "Too Many Requests",
                "detail": "You are being rate limited.",
                "instance": "/api/v1/companies",
            },
            headers={"Retry-After": "60"},
        )

        # When/Then: Making a request raises RateLimitError with retry_after
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 60
        assert exc_info.value.title == "Too Many Requests"

    @respx.mock
    def test_rate_limit_error_without_retry_after_header(self, base_service, base_url, mocker):
        """Verify RateLimitError works without Retry-After header."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning 429 without Retry-After header
        respx.get(f"{base_url}/limited").respond(
            429,
            json={"detail": "Rate limit exceeded"},
        )

        # When/Then: Making a request raises RateLimitError with retry_after=None
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after is None

    @respx.mock
    def test_rate_limit_error_with_invalid_retry_after_header(self, base_service, base_url, mocker):
        """Verify RateLimitError handles invalid Retry-After header gracefully."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning 429 with non-numeric Retry-After
        respx.get(f"{base_url}/limited").respond(
            429,
            json={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "invalid"},
        )

        # When/Then: Making a request raises RateLimitError with retry_after=None
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after is None


class TestBaseServiceHTTPMethods:
    """Tests for BaseService HTTP method helpers."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "status"),
        [
            ("GET", 200),
            ("POST", 201),
            ("PUT", 200),
            ("PATCH", 200),
            ("DELETE", 204),
        ],
    )
    def test_http_methods(self, base_service, base_url, method, status):
        """Verify HTTP methods make correct requests."""
        # Given: A mocked endpoint for the HTTP method
        route = getattr(respx, method.lower())(f"{base_url}/path").respond(
            status, json={} if method != "DELETE" else None
        )

        # When: Calling the corresponding method
        service_method = getattr(base_service, f"_{method.lower()}")
        if method in ("POST", "PUT", "PATCH"):
            service_method("/path", json={"data": "value"})
        else:
            service_method("/path")

        # Then: Correct HTTP method was used
        assert route.called
        assert route.calls.last.request.method == method


class TestBaseServiceIdempotency:
    """Tests for BaseService idempotency key support."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "path", "status", "key"),
        [
            ("POST", "/items", 201, "post-key"),
            ("PUT", "/items/1", 200, "put-key"),
            ("PATCH", "/items/1", 200, "patch-key"),
        ],
    )
    def test_explicit_idempotency_key(
        self, base_service, base_url, api_key, method, path, status, key
    ):
        """Verify requests include explicit idempotency key and preserve other headers."""
        # Given: A mocked endpoint
        route = getattr(respx, method.lower())(f"{base_url}{path}").respond(status, json={})

        # When: Making a request with explicit idempotency key
        service_method = getattr(base_service, f"_{method.lower()}")
        service_method(path, json={}, idempotency_key=key)

        # Then: Request includes the idempotency key header and other headers
        assert route.called
        request = route.calls.last.request
        assert request.headers.get(IDEMPOTENCY_KEY_HEADER) == key
        assert request.headers.get(API_KEY_HEADER) == api_key

    @respx.mock
    def test_post_without_idempotency_key(self, base_service, base_url):
        """Verify POST request without idempotency key has no header."""
        # Given: A mocked POST endpoint
        route = respx.post(f"{base_url}/items").respond(201, json={})

        # When: Making a POST request without idempotency key
        base_service._post("/items", json={})

        # Then: Request does not include idempotency key header
        assert route.called
        request = route.calls.last.request
        assert IDEMPOTENCY_KEY_HEADER not in request.headers

    def test_generate_idempotency_key(self):
        """Verify generated idempotency keys are valid UUIDs and unique."""
        # When: Generating an idempotency key
        key = BaseService._generate_idempotency_key()

        # Then: Key is a valid UUID format (8-4-4-4-12 hex chars)
        assert len(key) == 36
        assert key.count("-") == 4

        # When: Generating 100 idempotency keys
        keys = {BaseService._generate_idempotency_key() for _ in range(100)}

        # Then: All keys are unique
        assert len(keys) == 100

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "path", "status"),
        [
            ("POST", "/items", 201),
            ("PUT", "/items/1", 200),
            ("PATCH", "/items/1", 200),
        ],
    )
    def test_auto_generates_idempotency_key_when_enabled(
        self, base_service_with_auto_idempotency, base_url, api_key, method, path, status
    ):
        """Verify requests auto-generate idempotency key and preserve other headers."""
        # Given: A mocked endpoint
        route = getattr(respx, method.lower())(f"{base_url}{path}").respond(status, json={})

        # When: Making a request without explicit idempotency key
        service_method = getattr(base_service_with_auto_idempotency, f"_{method.lower()}")
        service_method(path, json={})

        # Then: Request includes an auto-generated idempotency key header and other headers
        assert route.called
        request = route.calls.last.request
        key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        assert key is not None
        assert len(key) == 36
        assert key.count("-") == 4
        assert request.headers.get(API_KEY_HEADER) == api_key

    @respx.mock
    def test_explicit_key_takes_precedence_over_auto(
        self, base_service_with_auto_idempotency, base_url, api_key
    ):
        """Verify explicit idempotency key takes precedence and preserves other headers."""
        # Given: A mocked POST endpoint
        route = respx.post(f"{base_url}/items").respond(201, json={})

        # When: Making a POST request with explicit idempotency key
        base_service_with_auto_idempotency._post("/items", json={}, idempotency_key="explicit-key")

        # Then: Request uses the explicit key and preserves other headers
        assert route.called
        request = route.calls.last.request
        assert request.headers.get(IDEMPOTENCY_KEY_HEADER) == "explicit-key"
        assert request.headers.get(API_KEY_HEADER) == api_key


class TestBaseServicePagination:
    """Tests for BaseService pagination methods."""

    @respx.mock
    def test_get_paginated(self, base_service, base_url):
        """Verify _get_paginated returns PaginatedResponse."""
        # Given: A mocked paginated endpoint
        route = respx.get(f"{base_url}/items", params={"limit": "10", "offset": "0"}).respond(
            200,
            json={
                "items": [{"id": 1}, {"id": 2}],
                "limit": 10,
                "offset": 0,
                "total": 2,
            },
        )

        # When: Calling _get_paginated
        result = base_service._get_paginated("/items")

        # Then: Returns a PaginatedResponse with correct data
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 2
        assert result.total == 2

    @respx.mock
    def test_get_paginated_with_custom_limit_offset(self, base_service, base_url):
        """Verify _get_paginated accepts custom limit and offset."""
        # Given: A mocked paginated endpoint expecting custom params
        route = respx.get(f"{base_url}/items", params={"limit": "25", "offset": "50"}).respond(
            200,
            json={"items": [], "limit": 25, "offset": 50, "total": 100},
        )

        # When: Calling _get_paginated with custom limit and offset
        base_service._get_paginated("/items", limit=25, offset=50)

        # Then: Request was made with correct params
        assert route.called

    @respx.mock
    def test_get_paginated_clamps_limit(self, base_service, base_url):
        """Verify limit is clamped to valid range."""
        # Given: A mocked endpoint expecting max limit (100)
        route = respx.get(f"{base_url}/items", params={"limit": "100", "offset": "0"}).respond(
            200,
            json={"items": [], "limit": 100, "offset": 0, "total": 0},
        )

        # When: Calling _get_paginated with excessive limit
        base_service._get_paginated("/items", limit=999)

        # Then: Request was made with clamped limit
        assert route.called

    @respx.mock
    def test_get_paginated_respects_custom_max_limit(self, base_service, base_url):
        """Verify limit is clamped to a caller-supplied max_limit instead of the default."""
        # Given: An endpoint expecting the reference max limit (1000)
        route = respx.get(f"{base_url}/items", params={"limit": "1000", "offset": "0"}).respond(
            200,
            json={"items": [], "limit": 1000, "offset": 0, "total": 0},
        )

        # When: Calling _get_paginated with a raised max_limit and excessive limit
        base_service._get_paginated("/items", limit=5000, max_limit=1000)

        # Then: Request was made with the limit clamped to max_limit
        assert route.called

    @respx.mock
    def test_iter_all_pages(self, base_service, base_url):
        """Verify _iter_all_pages iterates through all pages."""
        # Given: Mocked endpoints for 3 pages of data
        respx.get(f"{base_url}/items", params={"limit": "2", "offset": "0"}).respond(
            200,
            json={
                "items": [{"id": 1}, {"id": 2}],
                "limit": 2,
                "offset": 0,
                "total": 5,
            },
        )
        respx.get(f"{base_url}/items", params={"limit": "2", "offset": "2"}).respond(
            200,
            json={
                "items": [{"id": 3}, {"id": 4}],
                "limit": 2,
                "offset": 2,
                "total": 5,
            },
        )
        respx.get(f"{base_url}/items", params={"limit": "2", "offset": "4"}).respond(
            200,
            json={
                "items": [{"id": 5}],
                "limit": 2,
                "offset": 4,
                "total": 5,
            },
        )

        # When: Iterating through all pages
        items = list(base_service._iter_all_pages("/items", limit=2))

        # Then: All items from all pages are returned
        assert len(items) == 5
        assert [item["id"] for item in items] == [1, 2, 3, 4, 5]


class TestBaseServiceRateLimitHeaderParsing:
    """Tests for BaseService rate limit header parsing."""

    def test_parse_rate_limit_header_t_value(self):
        """Verify parsing the 't' parameter from RateLimit header."""
        # Given: A RateLimit header with t value
        header = '"default";r=10;t=5'

        # When: Parsing the t parameter
        result = BaseService._parse_rate_limit_header_value(header, "t")

        # Then: The correct value is returned
        assert result == 5

    def test_parse_rate_limit_header_r_value(self):
        """Verify parsing the 'r' parameter from RateLimit header."""
        # Given: A RateLimit header with r value
        header = '"default";r=47;t=0'

        # When: Parsing the r parameter
        result = BaseService._parse_rate_limit_header_value(header, "r")

        # Then: The correct value is returned
        assert result == 47

    def test_parse_rate_limit_header_missing_parameter(self):
        """Verify parsing returns None for missing parameter."""
        # Given: A RateLimit header without the requested parameter
        header = '"default";r=10'

        # When: Parsing a missing parameter
        result = BaseService._parse_rate_limit_header_value(header, "t")

        # Then: None is returned
        assert result is None

    def test_parse_rate_limit_header_multiple_policies(self):
        """Verify parsing works with multiple comma-separated policies."""
        # Given: A RateLimit header with multiple policies
        header = '"burst";r=8;t=0, "sustained";r=95;t=0'

        # When: Parsing the r parameter (gets first policy's value)
        result = BaseService._parse_rate_limit_header_value(header, "r")

        # Then: The first policy's value is returned
        assert result == 8

    def test_parse_rate_limit_header_invalid_value(self):
        """Verify parsing handles non-numeric values gracefully."""
        # Given: A RateLimit header with invalid numeric value
        header = '"default";r=invalid;t=5'

        # When: Parsing the invalid parameter
        result = BaseService._parse_rate_limit_header_value(header, "r")

        # Then: None is returned
        assert result is None

    @respx.mock
    def test_rate_limit_error_includes_remaining_from_header(self, base_service, base_url, mocker):
        """Verify RateLimitError includes remaining tokens from RateLimit header."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint returning 429 with RateLimit header
        respx.get(f"{base_url}/limited").respond(
            429,
            json={"detail": "Rate limit exceeded"},
            headers={"RateLimit": '"default";r=0;t=5'},
        )

        # When/Then: Making a request raises RateLimitError with remaining
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.remaining == 0
        assert exc_info.value.retry_after == 5

    @respx.mock
    def test_rate_limit_prefers_rate_limit_header_over_retry_after(
        self, base_service, base_url, mocker
    ):
        """Verify RateLimit header 't' value is preferred over Retry-After."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint with both RateLimit and Retry-After headers
        respx.get(f"{base_url}/limited").respond(
            429,
            json={"detail": "Rate limit exceeded"},
            headers={
                "RateLimit": '"default";r=0;t=10',
                "Retry-After": "60",
            },
        )

        # When/Then: Making a request uses RateLimit header value
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        # RateLimit t=10 should be preferred over Retry-After: 60
        assert exc_info.value.retry_after == 10

    @respx.mock
    def test_rate_limit_falls_back_to_retry_after_header(self, base_service, base_url, mocker):
        """Verify Retry-After header is used when RateLimit header lacks 't' value."""
        # Given: Mock sleep to avoid actual delays during retries
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A mocked endpoint with only Retry-After header
        respx.get(f"{base_url}/limited").respond(
            429,
            json={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "30"},
        )

        # When/Then: Making a request uses Retry-After header value
        with pytest.raises(RateLimitError) as exc_info:
            base_service._get("/limited")

        assert exc_info.value.retry_after == 30


class TestBaseServiceRateLimitRetry:
    """Tests for BaseService rate limit auto-retry behavior."""

    @respx.mock
    def test_auto_retry_on_rate_limit_success(self, vclient, base_url, mocker):
        """Verify request is retried on 429 and succeeds after retry."""
        # Given: An endpoint that returns 429 once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(
                    429,
                    json={"detail": "Rate limited"},
                    headers={"RateLimit": '"default";r=0;t=0'},
                ),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # When: Making a request
        from vweb.api_client.services.base import BaseService

        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200
        assert response.json() == {"success": True}
        mock_sleep.assert_called_once()

    @respx.mock
    def test_auto_retry_max_retries_exceeded(self, vclient, base_url, mocker):
        """Verify RateLimitError is raised after max retries are exhausted."""
        # Given: An endpoint that always returns 429
        route = respx.get(f"{base_url}/test").respond(
            429,
            json={"detail": "Rate limited"},
            headers={"RateLimit": '"default";r=0;t=1'},
        )

        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # When/Then: Making a request raises RateLimitError after max retries
        from vweb.api_client.services.base import BaseService

        service = BaseService(vclient)
        with pytest.raises(RateLimitError):
            service._get("/test")

        # Then: Request was attempted max_retries + 1 times (initial + retries)
        assert route.call_count == vclient._config.max_retries + 1

    @respx.mock
    def test_auto_retry_disabled_via_config(self, base_url, api_key):
        """Verify no retry when auto_retry_rate_limit is disabled."""
        # Given: An endpoint that returns 429
        route = respx.get(f"{base_url}/test").respond(
            429,
            json={"detail": "Rate limited"},
            headers={"RateLimit": '"default";r=0;t=1'},
        )

        # When/Then: Making a request raises RateLimitError immediately
        from vweb.api_client import VClient
        from vweb.api_client.services.base import BaseService

        with VClient(base_url=base_url, api_key=api_key, auto_retry_rate_limit=False) as client:
            service = BaseService(client)
            with pytest.raises(RateLimitError):
                service._get("/test")

        # Then: Only one request was made (no retries)
        assert route.call_count == 1

    @respx.mock
    def test_auto_retry_respects_retry_after_from_header(self, vclient, base_url, mocker):
        """Verify retry delay uses the 't' value from RateLimit header."""
        # Given: An endpoint that returns 429 with t=1 then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(
                    429,
                    json={"detail": "Rate limited"},
                    headers={"RateLimit": '"default";r=0;t=1'},
                ),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # Given: Mock time.sleep to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # When: Making a request
        from vweb.api_client.services.base import BaseService

        service = BaseService(vclient)
        service._get("/test")

        # Then: Sleep waited the header's 1 second plus at most 25% jitter
        mock_sleep.assert_called_once()
        assert 1.0 <= mock_sleep.call_args[0][0] <= 1.25

    @respx.mock
    def test_auto_retry_does_not_double_retry_after(self, vclient, base_url, mocker):
        """Verify every retry waits the server's Retry-After plus jitter, without doubling."""
        # Given: An endpoint that returns 429 with Retry-After: 1 twice then succeeds
        rate_limited = httpx.Response(
            429, json={"detail": "Rate limited"}, headers={"Retry-After": "1"}
        )
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                rate_limited,
                rate_limited,
                httpx.Response(200, json={"success": True}),
            ]
        )
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # When: Making a request
        from vweb.api_client.services.base import BaseService

        BaseService(vclient)._get("/test")

        # Then: Each wait is 1s plus at most 25% jitter
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert all(1.0 <= delay <= 1.25 for delay in delays)

    @respx.mock
    def test_auto_retry_exponential_backoff(self, vclient, base_url, mocker):
        """Verify retry delay increases exponentially."""
        # Given: An endpoint that returns 429 twice then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(
                    429,
                    json={"detail": "Rate limited"},
                    headers={"RateLimit": '"default";r=0;t=0'},
                ),
                httpx.Response(
                    429,
                    json={"detail": "Rate limited"},
                    headers={"RateLimit": '"default";r=0;t=0'},
                ),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # Given: Mock time.sleep to capture the delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # When: Making a request
        from vweb.api_client.services.base import BaseService

        service = BaseService(vclient)
        service._get("/test")

        # Then: Sleep was called twice, doubling from the 0.5s default plus jitter
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert 0.5 <= delays[0] <= 0.625
        assert 1.0 <= delays[1] <= 1.25


class TestBaseServiceTransientRetry:
    """Tests for BaseService transient 5xx error retry behavior."""

    @respx.mock
    def test_get_retries_on_500(self, vclient, base_url, mocker):
        """Verify GET request is retried on 500 and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_get_retries_on_502(self, vclient, base_url, mocker):
        """Verify GET request is retried on 502 and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 502 once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(502, json={"detail": "Bad Gateway"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_get_retries_on_503(self, vclient, base_url, mocker):
        """Verify GET request is retried on 503 and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 503 once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(503, json={"detail": "Service Unavailable"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_get_retries_on_504(self, vclient, base_url, mocker):
        """Verify GET request is retried on 504 and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 504 once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(504, json={"detail": "Gateway Timeout"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_5xx_max_retries_exhausted_raises_server_error(self, vclient, base_url, mocker):
        """Verify ServerError is raised after max retries are exhausted on 500."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that always returns 500
        route = respx.get(f"{base_url}/test").respond(500, json={"detail": "Server error"})

        # When/Then: Making a request raises ServerError after max retries
        service = BaseService(vclient)
        with pytest.raises(ServerError):
            service._get("/test")

        # Then: Request was attempted max_retries + 1 times (initial + retries)
        assert route.call_count == vclient._config.max_retries + 1

    @respx.mock
    def test_5xx_not_retried_for_non_retryable_status(self, vclient, base_url, mocker):
        """Verify 501 is not retried because it is not in DEFAULT_RETRY_STATUSES."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 501
        route = respx.get(f"{base_url}/test").respond(501, json={"detail": "Not Implemented"})

        # When/Then: Making a request raises ServerError immediately
        service = BaseService(vclient)
        with pytest.raises(ServerError):
            service._get("/test")

        # Then: Only one request was made (no retries)
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_post_without_idempotency_key_not_retried_on_500(self, vclient, base_url, mocker):
        """Verify POST without idempotency key is not retried on 500."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500
        route = respx.post(f"{base_url}/items").respond(500, json={"detail": "Server error"})

        # When/Then: Making a POST request without idempotency key raises ServerError
        service = BaseService(vclient)
        with pytest.raises(ServerError):
            service._post("/items", json={"name": "test"})

        # Then: Only one request was made (no retries)
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_post_with_idempotency_key_retried_on_500(self, vclient, base_url, mocker):
        """Verify POST with explicit idempotency key is retried on 500."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 once then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request with explicit idempotency key
        service = BaseService(vclient)
        response = service._post("/items", json={"name": "test"}, idempotency_key="test-key")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 201

    @respx.mock
    def test_post_with_auto_idempotency_retried_on_500(
        self, vclient_with_auto_idempotency, base_url, mocker
    ):
        """Verify POST with auto-idempotency is retried on 500."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 once then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request with auto-idempotency enabled
        service = BaseService(vclient_with_auto_idempotency)
        response = service._post("/items", json={"name": "test"})

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 201

    @respx.mock
    def test_put_retried_on_500(self, vclient, base_url, mocker):
        """Verify PUT request is retried on 500 because PUT is idempotent."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 once then succeeds
        route = respx.put(f"{base_url}/items/1").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(200, json={"id": 1}),
            ]
        )

        # When: Making a PUT request
        service = BaseService(vclient)
        response = service._put("/items/1", json={"name": "test"})

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_delete_retried_on_500(self, vclient, base_url, mocker):
        """Verify DELETE request is retried on 500 because DELETE is idempotent."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 once then succeeds
        route = respx.delete(f"{base_url}/items/1").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(204),
            ]
        )

        # When: Making a DELETE request
        service = BaseService(vclient)
        response = service._delete("/items/1")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 204

    @respx.mock
    def test_patch_without_idempotency_key_not_retried_on_500(self, vclient, base_url, mocker):
        """Verify PATCH without idempotency key is not retried on 500."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500
        route = respx.patch(f"{base_url}/items/1").respond(500, json={"detail": "Server error"})

        # When/Then: Making a PATCH request without idempotency key raises ServerError
        service = BaseService(vclient)
        with pytest.raises(ServerError):
            service._patch("/items/1", json={"name": "test"})

        # Then: Only one request was made (no retries)
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_5xx_not_retried_when_auto_retry_disabled(self, base_url, api_key, mocker):
        """Verify 500 is not retried when auto_retry_rate_limit is disabled."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500
        route = respx.get(f"{base_url}/test").respond(500, json={"detail": "Server error"})

        # When/Then: Making a request with retry disabled raises ServerError immediately
        with VClient(base_url=base_url, api_key=api_key, auto_retry_rate_limit=False) as client:
            service = BaseService(client)
            with pytest.raises(ServerError):
                service._get("/test")

        # Then: Only one request was made (no retries)
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_5xx_uses_exponential_backoff(self, vclient, base_url, mocker):
        """Verify 5xx retries use exponential backoff with increasing delays."""
        # Given: Mock time.sleep to capture the delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 500 twice then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(500, json={"detail": "Server error"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a request
        service = BaseService(vclient)
        service._get("/test")

        # Then: Sleep was called twice, doubling from the 0.5s default plus jitter
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert 0.5 <= delays[0] <= 0.625
        assert 1.0 <= delays[1] <= 1.25


IN_PROGRESS = {
    "status": 409,
    "title": "Conflict",
    "detail": "A request with this idempotency key is still in progress.",
    "code": "IDEMPOTENCY_IN_PROGRESS",
}


class TestBaseServiceIdempotencyInProgressRetry:
    """Tests for retrying the 409 the API returns while an idempotent request is in progress."""

    @respx.mock
    def test_in_progress_409_is_retried_then_succeeds(
        self, base_service_with_auto_idempotency, base_url, mocker
    ):
        """Verify an in-progress 409 is retried with the same key and waits per Retry-After."""
        # Given: Mock time.sleep to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress once, then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx.Response(
                    409,
                    json=IN_PROGRESS,
                    headers={"Retry-After": "1", "RateLimit": '"default";r=5;t=30'},
                ),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request
        response = base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The retry succeeded with the same idempotency key
        assert response.json() == {"id": 1}
        assert route.call_count == 2
        keys = [call.request.headers[IDEMPOTENCY_KEY_HEADER] for call in route.calls]
        assert keys[0] == keys[1]

        # Then: The wait came from Retry-After, not the RateLimit t= value
        mock_sleep.assert_called_once()
        delay = mock_sleep.call_args[0][0]
        assert 1.0 <= delay <= 1.25

    @respx.mock
    def test_in_progress_409_without_retry_after_uses_backoff(
        self, base_service_with_auto_idempotency, vclient_with_auto_idempotency, base_url, mocker
    ):
        """Verify an in-progress 409 without Retry-After is retried with backoff."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress without Retry-After, then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx.Response(409, json=IN_PROGRESS, headers={"RateLimit": '"default";r=5;t=30'}),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request
        base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The request was retried once after a first-attempt backoff, not the RateLimit t=
        assert route.call_count == 2
        mock_sleep.assert_called_once()
        retry_delay = vclient_with_auto_idempotency._config.retry_delay
        assert retry_delay <= mock_sleep.call_args[0][0] <= retry_delay * 1.25

    @respx.mock
    def test_in_progress_409_with_invalid_retry_after_uses_backoff(
        self, base_service_with_auto_idempotency, vclient_with_auto_idempotency, base_url, mocker
    ):
        """Verify a non-integer Retry-After on an in-progress 409 falls back to backoff."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress with a non-integer Retry-After
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx.Response(
                    409,
                    json=IN_PROGRESS,
                    headers={"Retry-After": "soon", "RateLimit": '"default";r=5;t=30'},
                ),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request
        base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The request was retried once after a first-attempt backoff, not the RateLimit t=
        assert route.call_count == 2
        mock_sleep.assert_called_once()
        retry_delay = vclient_with_auto_idempotency._config.retry_delay
        assert retry_delay <= mock_sleep.call_args[0][0] <= retry_delay * 1.25

    @respx.mock
    def test_in_progress_409_exhausts_retries(
        self, base_service_with_auto_idempotency, vclient_with_auto_idempotency, base_url, mocker
    ):
        """Verify a persistent in-progress 409 raises ConflictError after all retries."""
        # Given: Mock time.sleep to capture the delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that always reports in progress
        route = respx.post(f"{base_url}/items").mock(
            return_value=httpx.Response(409, json=IN_PROGRESS, headers={"Retry-After": "1"})
        )

        # When: Making a POST request
        with pytest.raises(ConflictError) as exc_info:
            base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: The error identifies the in-progress conflict and its wait
        assert exc_info.value.is_idempotency_in_progress
        assert exc_info.value.retry_after == 1

        # Then: Every attempt was used
        config = vclient_with_auto_idempotency._config
        assert route.call_count == config.max_retries + 1

        # Then: Each wait was the 1 second Retry-After plus at most 25% jitter
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == config.max_retries
        assert all(1.0 <= delay <= 1.25 for delay in delays)

    @respx.mock
    def test_other_409_is_not_retried(self, base_service_with_auto_idempotency, base_url, mocker):
        """Verify a 409 without the in-progress code is raised immediately."""
        # Given: Mock time.sleep to detect any retry
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports a reused idempotency key
        route = respx.post(f"{base_url}/items").mock(
            return_value=httpx.Response(
                409, json={"detail": "Idempotency key reused with a different request body"}
            )
        )

        # When: Making a POST request
        with pytest.raises(ConflictError) as exc_info:
            base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: No retry was made
        assert not exc_info.value.is_idempotency_in_progress
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_in_progress_409_without_idempotency_key_is_not_retried(
        self, base_service, base_url, mocker
    ):
        """Verify an in-progress 409 is not retried when the request carried no key."""
        # Given: Mock time.sleep to detect any retry
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress
        route = respx.post(f"{base_url}/items").mock(
            return_value=httpx.Response(409, json=IN_PROGRESS, headers={"Retry-After": "1"})
        )

        # When: Making a POST request without an idempotency key
        with pytest.raises(ConflictError):
            base_service._post("/items", json={"name": "x"})

        # Then: No retry was made
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_in_progress_409_is_retried_for_keyed_put(self, base_service, base_url, mocker):
        """Verify an in-progress 409 is retried for a PUT that carries an explicit key."""
        # Given: Mock time.sleep to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress once, then succeeds
        route = respx.put(f"{base_url}/items/1").mock(
            side_effect=[
                httpx.Response(409, json=IN_PROGRESS, headers={"Retry-After": "1"}),
                httpx.Response(200, json={"id": 1}),
            ]
        )

        # When: Making a PUT request with an explicit idempotency key
        response = base_service._put("/items/1", json={"name": "x"}, idempotency_key="k-1")

        # Then: The retry succeeded with the same key
        assert response.json() == {"id": 1}
        assert route.call_count == 2
        assert [c.request.headers[IDEMPOTENCY_KEY_HEADER] for c in route.calls] == ["k-1", "k-1"]

        # Then: The wait was the 1 second Retry-After plus at most 25% jitter
        mock_sleep.assert_called_once()
        assert 1.0 <= mock_sleep.call_args[0][0] <= 1.25

    @respx.mock
    def test_in_progress_409_is_not_retried_for_unkeyed_delete(
        self, base_service, base_url, mocker
    ):
        """Verify an in-progress 409 is not retried for a DELETE, which carries no key."""
        # Given: Mock time.sleep to detect any retry
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress
        route = respx.delete(f"{base_url}/items/1").mock(
            return_value=httpx.Response(409, json=IN_PROGRESS, headers={"Retry-After": "1"})
        )

        # When/Then: The conflict surfaces after a single call
        with pytest.raises(ConflictError):
            base_service._delete("/items/1")
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_in_progress_409_not_retried_when_auto_retry_disabled(self, base_url, api_key, mocker):
        """Verify an in-progress 409 is not retried when auto retry is disabled."""
        # Given: Mock time.sleep to detect any retry
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress
        route = respx.post(f"{base_url}/items").mock(
            return_value=httpx.Response(409, json=IN_PROGRESS, headers={"Retry-After": "1"})
        )

        # When: Making a POST request with retries disabled
        with VClient(
            base_url=base_url,
            api_key=api_key,
            auto_retry_rate_limit=False,
            auto_idempotency_keys=True,
        ) as client:
            service = BaseService(client)
            with pytest.raises(ConflictError):
                service._post("/items", json={"name": "x"})

        # Then: Only one request was made
        assert route.call_count == 1
        mock_sleep.assert_not_called()


class TestBaseServiceNetworkErrorRetry:
    """Tests for BaseService network error retry behavior."""

    @respx.mock
    def test_get_retries_on_connect_error(self, vclient, base_url, mocker):
        """Verify GET request is retried on ConnectError and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx2.ConnectError("Connection refused"),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_get_retries_on_timeout(self, vclient, base_url, mocker):
        """Verify GET request is retried on ReadTimeout and succeeds after retry."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ReadTimeout once then succeeds
        route = respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx2.ReadTimeout("Read timed out"),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET request
        service = BaseService(vclient)
        response = service._get("/test")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 200

    @respx.mock
    def test_connect_error_max_retries_exhausted(self, vclient, base_url, mocker):
        """Verify ConnectError is raised after max retries are exhausted."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that always raises ConnectError
        respx.get(f"{base_url}/test").mock(side_effect=httpx2.ConnectError("Connection refused"))

        # When/Then: Making a request raises ConnectError after max retries
        service = BaseService(vclient)
        with pytest.raises(httpx2.ConnectError):
            service._get("/test")

    @respx.mock
    def test_timeout_max_retries_exhausted(self, vclient, base_url, mocker):
        """Verify TimeoutException is raised after max retries are exhausted."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that always raises ReadTimeout
        respx.get(f"{base_url}/test").mock(side_effect=httpx2.ReadTimeout("Read timed out"))

        # When/Then: Making a request raises TimeoutException after max retries
        service = BaseService(vclient)
        with pytest.raises(httpx2.TimeoutException):
            service._get("/test")

    @respx.mock
    def test_post_without_idempotency_key_not_retried_on_connect_error(
        self, vclient, base_url, mocker
    ):
        """Verify POST without idempotency key is not retried on ConnectError."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError
        respx.post(f"{base_url}/items").mock(side_effect=httpx2.ConnectError("Connection refused"))

        # When/Then: Making a POST request without idempotency key raises immediately
        service = BaseService(vclient)
        with pytest.raises(httpx2.ConnectError):
            service._post("/items", json={"name": "test"})

        # Then: No retries were attempted
        mock_sleep.assert_not_called()

    @respx.mock
    def test_post_with_idempotency_key_retried_on_connect_error(self, vclient, base_url, mocker):
        """Verify POST with idempotency key is retried on ConnectError."""
        # Given: Mock time.sleep to avoid actual delays
        mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError once then succeeds
        route = respx.post(f"{base_url}/items").mock(
            side_effect=[
                httpx2.ConnectError("Connection refused"),
                httpx.Response(201, json={"id": 1}),
            ]
        )

        # When: Making a POST request with explicit idempotency key
        service = BaseService(vclient)
        response = service._post("/items", json={"name": "test"}, idempotency_key="test-key")

        # Then: Request was retried and succeeded
        assert route.call_count == 2
        assert response.status_code == 201

    @respx.mock
    def test_network_error_not_retried_when_auto_retry_disabled(self, base_url, api_key, mocker):
        """Verify network errors are not retried when auto_retry_rate_limit is disabled."""
        # Given: Mock time.sleep to avoid actual delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError
        respx.get(f"{base_url}/test").mock(side_effect=httpx2.ConnectError("Connection refused"))

        # When/Then: Making a request with retry disabled raises immediately
        with VClient(base_url=base_url, api_key=api_key, auto_retry_rate_limit=False) as client:
            service = BaseService(client)
            with pytest.raises(httpx2.ConnectError):
                service._get("/test")

        # Then: No retries were attempted
        mock_sleep.assert_not_called()

    @respx.mock
    def test_network_error_uses_exponential_backoff(self, vclient, base_url, mocker):
        """Verify network error retries use exponential backoff with increasing delays."""
        # Given: Mock time.sleep to capture the delays
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that raises ConnectError twice then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx2.ConnectError("Connection refused"),
                httpx2.ConnectError("Connection refused"),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a request
        service = BaseService(vclient)
        service._get("/test")

        # Then: Sleep was called twice, doubling from the 0.5s default plus jitter
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert 0.5 <= delays[0] <= 0.625
        assert 1.0 <= delays[1] <= 1.25


class ConcreteServiceWithOnBehalfOf(BaseService):
    """Concrete implementation with on_behalf_of for testing."""

    def __init__(self, client: VClient, on_behalf_of: str | None = None) -> None:
        super().__init__(client)
        self._on_behalf_of = on_behalf_of


class TestOnBehalfOfHeader:
    """Tests for On-Behalf-Of header injection."""

    @respx.mock
    def test_on_behalf_of_header_sent(self, vclient, base_url):
        """Verify On-Behalf-Of header is sent when set."""
        # Given: A service with on_behalf_of set
        service = ConcreteServiceWithOnBehalfOf(vclient, on_behalf_of="user-uuid-123")
        route = respx.get(f"{base_url}/test").respond(200, json={})

        # When: Making a GET request
        service._get("/test")

        # Then: The On-Behalf-Of header is present in the request
        assert route.called
        request = route.calls[0].request
        assert request.headers[ON_BEHALF_OF_HEADER] == "user-uuid-123"

    @respx.mock
    def test_on_behalf_of_header_not_sent_when_none(self, vclient, base_url):
        """Verify On-Behalf-Of header is not sent when not set."""
        # Given: A service with on_behalf_of unset
        service = ConcreteServiceWithOnBehalfOf(vclient, on_behalf_of=None)
        route = respx.get(f"{base_url}/test").respond(200, json={})

        # When: Making a GET request
        service._get("/test")

        # Then: The On-Behalf-Of header is absent from the request
        assert route.called
        request = route.calls[0].request
        assert ON_BEHALF_OF_HEADER not in request.headers

    @respx.mock
    def test_on_behalf_of_coexists_with_idempotency_key(self, vclient, base_url):
        """Verify On-Behalf-Of header coexists with idempotency key header."""
        # Given: A service with on_behalf_of set and an explicit idempotency key
        service = ConcreteServiceWithOnBehalfOf(vclient, on_behalf_of="user-uuid-123")
        route = respx.post(f"{base_url}/test").respond(200, json={})

        # When: Making a POST request with an explicit idempotency key
        service._post("/test", json={}, idempotency_key="idem-key-456")

        # Then: Both headers are present in the request
        assert route.called
        request = route.calls[0].request
        assert request.headers[ON_BEHALF_OF_HEADER] == "user-uuid-123"
        assert request.headers["Idempotency-Key"] == "idem-key-456"


class TestGetCustomHeaders:
    """Tests for BaseService._get custom header forwarding."""

    @respx.mock
    def test_get_forwards_custom_headers(self, base_service, base_url):
        """Verify _get forwards caller-supplied headers such as Accept."""
        # Given: A mocked endpoint
        route = respx.get(f"{base_url}/custom").respond(200, json={})

        # When: Issuing a GET with a custom Accept header
        base_service._get("/custom", headers={"Accept": "application/zip"})

        # Then: The request carried the custom Accept header
        assert route.called
        assert route.calls.last.request.headers["accept"] == "application/zip"


class TestBaseServiceRetryLimits:
    """Tests for the per-wait cap and total time budget on retries."""

    @respx.mock
    def test_backoff_is_capped_at_max_retry_delay(self, base_url, api_key, mocker):
        """Verify a backoff longer than max_retry_delay waits only max_retry_delay."""
        # Given: Mock time.sleep to capture the delay
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that returns 503 once then succeeds
        respx.get(f"{base_url}/test").mock(
            side_effect=[
                httpx.Response(503, json={"detail": "Unavailable"}),
                httpx.Response(200, json={"success": True}),
            ]
        )

        # When: Making a GET with a base delay longer than the cap
        with VClient(
            base_url=base_url, api_key=api_key, retry_delay=5.0, max_retry_delay=1.5
        ) as client:
            BaseService(client)._get("/test")

        # Then: The wait was exactly the cap, jitter included
        mock_sleep.assert_called_once_with(1.5)

    @respx.mock
    def test_retry_after_above_cap_raises_without_waiting(self, vclient, base_url, mocker):
        """Verify a server Retry-After longer than max_retry_delay raises at once."""
        # Given: Mock time.sleep to detect any wait
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that asks the client to wait 30 seconds
        route = respx.get(f"{base_url}/test").respond(
            429, json={"detail": "Rate limited"}, headers={"Retry-After": "30"}
        )

        # When/Then: The rate limit error is raised after one call
        with pytest.raises(RateLimitError) as exc_info:
            BaseService(vclient)._get("/test")

        # Then: No wait and no retry happened
        assert exc_info.value.retry_after == 30
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_in_progress_409_retry_after_above_cap_raises(
        self, base_service_with_auto_idempotency, base_url, mocker
    ):
        """Verify an in-progress 409 asking for a long wait raises without retrying."""
        # Given: Mock time.sleep to detect any wait
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: An endpoint that reports in progress and asks for a 10 second wait
        route = respx.post(f"{base_url}/items").respond(
            409, json=IN_PROGRESS, headers={"Retry-After": "10"}
        )

        # When/Then: The conflict is raised after one call
        with pytest.raises(ConflictError):
            base_service_with_auto_idempotency._post("/items", json={"name": "x"})

        # Then: No wait and no retry happened
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_retry_stops_when_budget_would_be_exceeded(self, base_url, api_key, mocker):
        """Verify the last error is raised when the next wait would overrun the budget."""
        # Given: Mock time.sleep to detect any wait
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A clock where the first attempt takes 9.8 of the 10 second budget
        mocker.patch("vweb.api_client.services.base.time.monotonic", side_effect=[100.0, 109.8])

        # Given: An endpoint that always returns 503
        route = respx.get(f"{base_url}/test").respond(503, json={"detail": "Unavailable"})

        # When/Then: The server error is raised without a retry
        with (
            VClient(base_url=base_url, api_key=api_key, retry_budget=10.0) as client,
            pytest.raises(ServerError),
        ):
            BaseService(client)._get("/test")

        # Then: Only the first attempt was made
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    @respx.mock
    def test_network_error_retry_stops_at_budget(self, base_url, api_key, mocker):
        """Verify a network error is raised when the next wait would overrun the budget."""
        # Given: Mock time.sleep to detect any wait
        mock_sleep = mocker.patch("vweb.api_client.services.base.time.sleep")

        # Given: A clock where the first attempt uses the whole budget
        mocker.patch("vweb.api_client.services.base.time.monotonic", side_effect=[0.0, 10.0])

        # Given: An endpoint that refuses connections
        route = respx.get(f"{base_url}/test").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )

        # When/Then: The network error surfaces after one call
        with (
            VClient(base_url=base_url, api_key=api_key, retry_budget=10.0) as client,
            pytest.raises(httpx2.ConnectError),
        ):
            BaseService(client)._get("/test")

        # Then: No retry was made
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
