"""Base service class for API services."""

import mimetypes
import random
import time
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

import httpx2
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_RETRY_STATUSES,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_600_UPPER_BOUND,
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENT_HTTP_METHODS,
    MAX_PAGE_LIMIT,
    ON_BEHALF_OF_HEADER,
    RATE_LIMIT_HEADER,
    REQUEST_ID_HEADER,
)
from vweb.api_client.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    RequestValidationError,
    ServerError,
    UnprocessableEntityError,
    ValidationError,
)
from vweb.api_client.models.pagination import PaginatedResponse
from vweb.api_client.models.shared import RollStatistics

T = TypeVar("T", bound=BaseModel)

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class _RetryPlan(NamedTuple):
    """How to log and wait before retrying an error response."""

    message: str
    retry_after: int | None
    log_fields: dict[str, Any]


class BaseService:
    """Base class for all API services.

    Provides common functionality for making HTTP requests and handling responses.
    """

    def __init__(self, client: "VClient", *, on_behalf_of: str | None = None, **scope: str) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            on_behalf_of: User ID to impersonate via the On-Behalf-Of header, or None.
            **scope: Path IDs (such as ``company_id``) filled into every endpoint template.
        """
        self._client = client
        self._on_behalf_of = on_behalf_of
        self._scope = scope

    @property
    def _company_id(self) -> str | None:
        """The company this service is scoped to, or None for unscoped services."""
        return self._scope.get("company_id")

    def _format_endpoint(self, endpoint: str, **kwargs: str) -> str:
        """Fill an endpoint template with the service's scope IDs plus any extra params.

        Args:
            endpoint: The endpoint template from ``Endpoints``.
            **kwargs: Path parameters beyond the service's scope.

        Returns:
            The formatted endpoint path.
        """
        return endpoint.format(**self._scope, **kwargs)

    @property
    def _http(self) -> httpx2.Client:
        """Get the HTTP client from the parent VClient."""
        return self._client._http  # noqa: SLF001

    @staticmethod
    def _generate_idempotency_key() -> str:
        """Generate a new UUID v4 idempotency key.

        Returns:
            A unique idempotency key string.
        """
        return str(uuid.uuid4())

    def _validate_request(self, request_class: type[T], **kwargs: Any) -> T:
        """Validate and create a request model, converting Pydantic errors.

        Args:
            request_class: The Pydantic model class to instantiate.
            **kwargs: Fields to pass to the model constructor.

        Returns:
            The validated request model instance.

        Raises:
            RequestValidationError: If validation fails.
        """
        try:
            return request_class(**kwargs)
        except PydanticValidationError as e:
            raise RequestValidationError(e) from e

    def _calculate_backoff_delay(
        self, attempt: int, retry_after: int | None, *, started_at: float
    ) -> float | None:
        """Calculate the delay before the next retry attempt, or decide not to retry.

        Wait the server's ``retry_after`` when it gives one, since the server knows
        when capacity returns. Otherwise use exponential backoff:
        ``retry_delay * 2 ** attempt``. Either way, add up to 25% random jitter so
        clients that were limited together do not retry together, and cap the result
        at ``max_retry_delay``.

        A caller holds a web worker while it waits, so a call never waits longer than
        it can use: a server ``retry_after`` above ``max_retry_delay``, or a wait that
        would overrun ``retry_budget``, ends the retries.

        Args:
            attempt: The current attempt number (0-indexed).
            retry_after: Seconds the server asked the client to wait, or None.
            started_at: ``time.monotonic()`` reading taken when the call began.

        Returns:
            Number of seconds to wait before retrying, or None to stop retrying.
        """
        config = self._client._config  # noqa: SLF001
        if retry_after is not None and retry_after > 0:
            if retry_after > config.max_retry_delay:
                return None
            delay = float(retry_after)
        else:
            delay = config.retry_delay * (2**attempt)

        delay = min(delay + random.uniform(0, delay * 0.25), config.max_retry_delay)

        if time.monotonic() - started_at + delay > config.retry_budget:
            return None
        return delay

    @staticmethod
    def _is_retryable_method(method: str, headers: dict[str, str] | None) -> bool:
        """Check if a request method is safe to retry.

        Idempotent methods (GET, PUT, DELETE) are always safe. Non-idempotent
        methods (POST, PATCH) are only safe if an idempotency key is present.

        Args:
            method: The HTTP method (uppercase).
            headers: The request headers, or None.

        Returns:
            True if the request is safe to retry.
        """
        if method in IDEMPOTENT_HTTP_METHODS:
            return True

        return BaseService._has_idempotency_key(headers)

    @staticmethod
    def _has_idempotency_key(headers: dict[str, str] | None) -> bool:
        """Check if the request headers carry an idempotency key.

        Args:
            headers: The request headers, or None.

        Returns:
            True if the idempotency key header is present.
        """
        return IDEMPOTENCY_KEY_HEADER in (headers or {})

    @classmethod
    def _plan_error_retry(
        cls,
        error: RateLimitError | ServerError | ConflictError,
        method: str,
        headers: dict[str, str] | None,
    ) -> _RetryPlan | None:
        """Decide whether an error response is safe to retry, and how to log and wait.

        Rate limits always retry. Server errors retry only for a status in
        `DEFAULT_RETRY_STATUSES` on a request that is safe to resend. A 409 retries only when the
        API reports that a request with the same idempotency key is still in progress and
        this request carried that key: every other 409 means the request itself
        conflicts, so resending it cannot succeed.

        Args:
            error: The error raised for the response.
            method: The HTTP method (uppercase).
            headers: The request headers, or None.

        Returns:
            The retry plan, or None if the error must be raised without a retry.
        """
        if isinstance(error, RateLimitError):
            return _RetryPlan(
                message="Retry after rate limit", retry_after=error.retry_after, log_fields={}
            )

        if isinstance(error, ServerError):
            if error.status_code in DEFAULT_RETRY_STATUSES and cls._is_retryable_method(
                method, headers
            ):
                return _RetryPlan(
                    message="Retry after server error",
                    retry_after=None,
                    log_fields={"status": error.status_code},
                )
            return None

        if error.is_idempotency_in_progress and cls._has_idempotency_key(headers):
            return _RetryPlan(
                message="Retry after idempotency conflict",
                retry_after=error.retry_after,
                log_fields={"status": error.status_code},
            )
        return None

    def _wait_before_retry(
        self,
        request_logger: Any,
        message: str,
        *,
        attempt: int,
        max_attempts: int,
        retry_after: int | None,
        started_at: float,
        **log_fields: Any,
    ) -> bool:
        """Log a retry at WARNING and sleep for the backoff delay before the next attempt.

        Args:
            request_logger: A bound loguru logger to emit the log record on.
            message: The log message that names the retry cause.
            attempt: The current attempt number (0-indexed).
            max_attempts: The total number of attempts allowed.
            retry_after: Seconds the server asked the client to wait, or None to use backoff.
            started_at: ``time.monotonic()`` reading taken when the call began.
            **log_fields: Extra structured fields to bind on the log record.

        Returns:
            True after waiting, or False when the call must stop retrying instead.
        """
        if attempt >= max_attempts - 1:
            return False

        delay = self._calculate_backoff_delay(attempt, retry_after, started_at=started_at)
        if delay is None:
            request_logger.bind(**log_fields, attempt=attempt + 1, retry_after=retry_after).warning(
                "Stop retrying to stay within the retry time limits"
            )
            return False

        request_logger.bind(
            **log_fields,
            attempt=attempt + 1,
            max_attempts=max_attempts,
            delay=delay,
        ).warning(message)
        time.sleep(delay)
        return True

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: Any | None = None,
    ) -> httpx2.Response:
        """Make an HTTP request with automatic retry on transient errors.

        Retries on rate limits (429), server errors (5xx in DEFAULT_RETRY_STATUSES),
        and network errors (ConnectError, TimeoutException), within the
        ``max_retry_delay`` and ``retry_budget`` limits described on
        `_calculate_backoff_delay`. Non-idempotent methods (POST, PATCH) only
        retry on 5xx/network errors when an idempotency key header is present. Rate limit retries (429) always
        apply regardless of method. A 409 is retried only when the API reports
        that a request with the same idempotency key is still in progress
        (code IDEMPOTENCY_IN_PROGRESS) and this request carried that key.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            path: API endpoint path (will be appended to base_url).
            params: Query parameters.
            json: JSON body data.
            data: Form data.
            headers: Additional headers to include in the request.
            files: Files to upload (passed through to httpx2).

        Returns:
            The HTTP response.

        Raises:
            RateLimitError: When rate limit is exceeded and max retries are exhausted.
            ServerError: When server error occurs and max retries are exhausted.
            ConflictError: For a 409 response, or when an idempotent request is
                still in progress after max retries are exhausted.
            APIConnectionError: When no response arrives, such as a refused connection or
                a timeout, and retries are exhausted or not allowed.
            APIError: For other API error responses.
        """
        headers = self._merge_on_behalf_of_header(headers)

        config = self._client._config  # noqa: SLF001
        max_attempts = config.max_retries + 1 if config.auto_retry_rate_limit else 1
        # Bind params so paginated requests are distinguishable in logs; without
        # limit/offset, identical paths look like duplicate (thundering-herd) calls.
        request_logger = logger.bind(method=method, url=path, params=params)

        # TRACE so the in-flight request is visible only when diagnosing hangs; the
        # "Request complete" DEBUG line below is the superset record for normal use.
        request_logger.trace("Send request")

        last_error: RateLimitError | ServerError | ConflictError | None = None
        attempts_made = 0
        started_at = time.monotonic()

        for attempt in range(max_attempts):
            attempts_made = attempt + 1
            try:
                response = self._http.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json,
                    data=data,
                    headers=headers,
                    files=files,
                )
            except httpx2.HTTPError as exc:
                retryable = isinstance(
                    exc, (httpx2.ConnectError, httpx2.TimeoutException)
                ) and self._is_retryable_method(method, headers)
                if retryable and self._wait_before_retry(
                    request_logger,
                    "Retry after network error",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_after=None,
                    started_at=started_at,
                    error_type=type(exc).__name__,
                ):
                    continue
                request_logger.bind(attempts=attempts_made, error_type=type(exc).__name__).error(
                    "Fail to reach the API"
                )
                msg = f"Could not reach the API: {str(exc) or type(exc).__name__}"
                raise APIConnectionError(msg) from exc

            try:
                self._raise_for_status(response, method, path, params=params)
                self._log_success_response(response, request_logger)
                return response  # noqa: TRY300
            except (RateLimitError, ServerError, ConflictError) as e:
                retry_plan = self._plan_error_retry(error=e, method=method, headers=headers)
                if retry_plan is None:
                    raise

                last_error = e

                if not self._wait_before_retry(
                    request_logger,
                    retry_plan.message,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_after=retry_plan.retry_after,
                    started_at=started_at,
                    **retry_plan.log_fields,
                ):
                    break

        if last_error is not None:
            if max_attempts > 1:
                request_logger.bind(attempts=attempts_made).error("Exhaust retries")
            else:
                request_logger.warning("Fail with automatic retries off")
            raise last_error

        msg = "Unexpected state: no response or error"
        raise RuntimeError(msg)

    @staticmethod
    def _log_success_response(response: httpx2.Response, request_logger: Any) -> None:
        """Log a successful HTTP response with elapsed time and optional request_id.

        Args:
            response: The successful HTTP response to log.
            request_logger: A bound loguru logger to emit the log record on.
        """
        elapsed_ms = response.elapsed.total_seconds() * 1000
        success_bind: dict[str, Any] = {
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
        }
        header_request_id = response.headers.get(REQUEST_ID_HEADER)
        if header_request_id:
            success_bind["request_id"] = header_request_id
        request_logger.bind(**success_bind).debug("Request complete")

    @staticmethod
    def _inject_request_id_fallback(
        response_data: dict[str, Any], response: httpx2.Response
    ) -> None:
        """Inject request_id from X-Request-Id header when the response body omits it.

        Args:
            response_data: The parsed response JSON body (mutated in place).
            response: The HTTP response to read the header from.
        """
        if "request_id" not in response_data:
            header_id = response.headers.get(REQUEST_ID_HEADER)
            if header_id:
                response_data["request_id"] = header_id

    def _raise_for_status(  # noqa: C901
        self,
        response: httpx2.Response,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Raise appropriate exception for error responses.

        Args:
            response: The HTTP response to check.
            method: The HTTP method of the request.
            url: The URL path of the request.
            params: The query parameters of the request, logged to disambiguate
                paginated calls that share the same path.

        Raises:
            AuthenticationError: For 401 responses.
            AuthorizationError: For 403 responses.
            NotFoundError: For 404 responses.
            ValidationError: For 400 responses.
            ConflictError: For 409 responses.
            PayloadTooLargeError: For 413 responses.
            UnprocessableEntityError: For 422 responses.
            RateLimitError: For 429 responses.
            ServerError: For 5xx responses.
            APIError: For other error responses.
        """
        if response.is_success:
            return

        status_code = response.status_code
        try:
            response_data = response.json()
        except ValueError:
            response_data = {}
        # Non-RFC 9457 bodies (proxies, framework validators) may be a JSON
        # list or scalar, or carry a non-string detail; normalize so .get()
        # works and message is always a str
        if not isinstance(response_data, dict):
            response_data = {}
        detail = response_data.get("detail")
        message = detail if isinstance(detail, str) else (response.text or f"HTTP {status_code}")

        self._inject_request_id_fallback(response_data, response)

        error_logger = logger.bind(
            method=method,
            url=url,
            params=params,
            status=status_code,
            request_id=response_data.get("request_id"),
        )

        if status_code == 429:  # noqa: PLR2004
            retry_after = self._parse_retry_after(response)
            remaining = self._parse_remaining_tokens(response)
            raise RateLimitError(
                message, status_code, response_data, retry_after=retry_after, remaining=remaining
            )

        if status_code == 401:  # noqa: PLR2004
            error_logger.error("Fail authentication")
            raise AuthenticationError(message, status_code, response_data)

        if status_code == 403:  # noqa: PLR2004
            error_logger.error("Deny authorization")
            raise AuthorizationError(message, status_code, response_data)

        if status_code == 404:  # noqa: PLR2004
            error_logger.debug("Return 404")
            raise NotFoundError(message, status_code, response_data)

        if status_code == 400:  # noqa: PLR2004
            error_logger.warning("Reject with validation error")
            raise ValidationError(message, status_code, response_data)

        if status_code == 409:  # noqa: PLR2004
            conflict = ConflictError(
                message,
                status_code,
                response_data,
                retry_after=self._parse_retry_after_header(response),
            )
            # An in-progress conflict is either retried, which logs its own warning, or
            # reported once _request gives up, so a second warning here is noise
            log_conflict = (
                error_logger.debug if conflict.is_idempotency_in_progress else error_logger.warning
            )
            log_conflict("Return 409 conflict")
            raise conflict

        if status_code == 413:  # noqa: PLR2004
            error_logger.warning("Reject request body as too large")
            raise PayloadTooLargeError(message, status_code, response_data)

        if status_code == 422:  # noqa: PLR2004
            error_logger.warning("Reject with unprocessable entity error")
            raise UnprocessableEntityError(message, status_code, response_data)

        if HTTP_500_INTERNAL_SERVER_ERROR <= status_code < HTTP_600_UPPER_BOUND:
            raise ServerError(message, status_code, response_data)

        raise APIError(message, status_code, response_data)

    @staticmethod
    def _parse_rate_limit_header_value(header_value: str, parameter: str) -> int | None:
        """Parse a parameter value from a RateLimit header.

        The RateLimit header format is: "policy_name";r=REMAINING;t=RETRY_SECONDS
        Multiple policies are comma-separated.

        Args:
            header_value: The full RateLimit header value.
            parameter: The parameter to extract (e.g., "r" for remaining, "t" for retry).

        Returns:
            The parsed integer value, or None if not found or invalid.
        """
        search_pattern = f";{parameter}="
        if search_pattern not in header_value:
            return None

        try:
            # Extract value after ";parameter=" up to next ";" or end/comma
            value_start = header_value.split(search_pattern)[1]
            # Handle multiple policies (comma-separated) and multiple params (semicolon)
            value_str = value_start.split(";")[0].split(",")[0].strip()
            return int(value_str)
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _parse_retry_after_header(response: httpx2.Response) -> int | None:
        """Parse the standard Retry-After header as whole seconds.

        Read only Retry-After, because the RateLimit header's "t" parameter describes
        the rate limit bucket, not when an in-progress request will finish.

        Args:
            response: The HTTP response to read the header from.

        Returns:
            Number of seconds to wait, or None if the header is missing or not an integer.
        """
        value = response.headers.get("Retry-After")
        if value is None:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_retry_after(response: httpx2.Response) -> int | None:
        """Parse the retry time from response headers.

        First checks the RateLimit header for the "t" parameter (seconds until next token),
        then falls back to the standard Retry-After header.

        Args:
            response: The HTTP response containing rate limit headers.

        Returns:
            Number of seconds to wait, or None if no retry info is available.
        """
        # Try RateLimit header first (";t=" parameter)
        rate_limit_header = response.headers.get(RATE_LIMIT_HEADER)
        if rate_limit_header:
            retry_time = BaseService._parse_rate_limit_header_value(rate_limit_header, "t")
            if retry_time is not None:
                return retry_time

        return BaseService._parse_retry_after_header(response)

    @staticmethod
    def _parse_remaining_tokens(response: httpx2.Response) -> int | None:
        """Parse the remaining tokens from the RateLimit header.

        Args:
            response: The HTTP response containing the RateLimit header.

        Returns:
            Number of remaining tokens, or None if not available.
        """
        rate_limit_header = response.headers.get(RATE_LIMIT_HEADER)
        if not rate_limit_header:
            return None

        return BaseService._parse_rate_limit_header_value(rate_limit_header, "r")

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx2.Response:
        """Make a GET request.

        Args:
            path: API endpoint path.
            params: Query parameters.
            headers: Additional headers (e.g. an Accept override for binary downloads).

        Returns:
            The HTTP response.
        """
        return self._request("GET", path, params=params, headers=headers)

    def _merge_on_behalf_of_header(
        self,
        headers: dict[str, str] | None,
    ) -> dict[str, str] | None:
        """Merge the On-Behalf-Of header into headers when _on_behalf_of is set.

        Prepends the On-Behalf-Of header so caller-supplied headers always win
        on any key collision (though in practice the keys are distinct).

        Args:
            headers: Existing request headers, or None.

        Returns:
            A new headers dict with the On-Behalf-Of header included, or the
            original value unchanged if _on_behalf_of is not set.
        """
        if self._on_behalf_of is None:
            return headers
        return {ON_BEHALF_OF_HEADER: self._on_behalf_of, **(headers or {})}

    def _build_idempotency_headers(
        self,
        idempotency_key: str | None,
        *,
        auto_generate: bool = False,
    ) -> dict[str, str] | None:
        """Build the idempotency-key header, generating a key when asked and configured.

        Args:
            idempotency_key: Explicit idempotency key, always sent when given.
            auto_generate: Generate a key when none is given and ``auto_idempotency_keys``
                is on. A key makes POST and PATCH safe to retry after network and server
                errors.

        Returns:
            Headers dict with the idempotency key, or None if there is no key.
        """
        if (
            idempotency_key is None and auto_generate and self._client._config.auto_idempotency_keys  # noqa: SLF001
        ):
            idempotency_key = self._generate_idempotency_key()
        if idempotency_key is None:
            return None
        return {IDEMPOTENCY_KEY_HEADER: idempotency_key}

    @staticmethod
    def _build_params(**kwargs: Any) -> dict[str, Any] | None:
        """Build query params dict, filtering out None values.

        Args:
            **kwargs: Key-value pairs for query parameters.

        Returns:
            Dict with non-None values, or None if all values are None.
        """
        params = {k: v for k, v in kwargs.items() if v is not None}
        return params or None

    def _get_statistics(self, path: str, *, num_top_traits: int) -> RollStatistics:
        """Fetch aggregated dice roll statistics from a statistics endpoint.

        Args:
            path: The formatted statistics endpoint path.
            num_top_traits: Number of top traits to include.

        Returns:
            The parsed RollStatistics.
        """
        response = self._get(path, params={"num_top_traits": num_top_traits})
        return RollStatistics.model_validate(response.json())

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any] | list[Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        auto_idempotency_key: bool = True,
    ) -> httpx2.Response:
        """Make a POST request.

        Args:
            path: API endpoint path.
            json: JSON body data.
            data: Form data.
            params: Query parameters.
            idempotency_key: Optional idempotency key for safe retries.
            auto_idempotency_key: When False, no key is generated even if
                ``auto_idempotency_keys`` is on, which disables retries after network
                and server errors. Rate limit (429) retries still apply. An explicit
                ``idempotency_key`` is still sent.

        Returns:
            The HTTP response.
        """
        return self._request(
            "POST",
            path,
            json=json,
            data=data,
            params=params,
            headers=self._build_idempotency_headers(
                idempotency_key, auto_generate=auto_idempotency_key
            ),
        )

    def _put(
        self,
        path: str,
        *,
        json: dict[str, Any] | list[Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> httpx2.Response:
        """Make a PUT request.

        Args:
            path: API endpoint path.
            json: JSON body data.
            data: Form data.
            params: Query parameters.
            idempotency_key: Optional idempotency key for safe retries.

        Returns:
            The HTTP response.
        """
        return self._request(
            "PUT",
            path,
            json=json,
            data=data,
            params=params,
            headers=self._build_idempotency_headers(idempotency_key, auto_generate=True),
        )

    def _patch(
        self,
        path: str,
        *,
        json: dict[str, Any] | list[Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> httpx2.Response:
        """Make a PATCH request.

        Args:
            path: API endpoint path.
            json: JSON body data.
            data: Form data.
            params: Query parameters.
            idempotency_key: Optional idempotency key for safe retries.

        Returns:
            The HTTP response.
        """
        return self._request(
            "PATCH",
            path,
            json=json,
            data=data,
            params=params,
            headers=self._build_idempotency_headers(idempotency_key, auto_generate=True),
        )

    def _delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        """Make a DELETE request.

        Args:
            path: API endpoint path.
            params: Query parameters.

        Returns:
            The HTTP response.
        """
        return self._request("DELETE", path, params=params)

    @staticmethod
    def _multipart_file(file: tuple[str, bytes, str | None]) -> dict[str, tuple[str, bytes, str]]:
        """Build the multipart ``files`` mapping, guessing a missing content type.

        Args:
            file: Tuple of (filename, content, content_type).

        Returns:
            The ``files`` mapping with the upload under the ``data`` field.
        """
        filename, content, content_type = file
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return {"data": (filename, content, content_type)}

    def _post_file(
        self,
        path: str,
        *,
        file: tuple[str, bytes, str | None],
        idempotency_key: str | None = None,
    ) -> httpx2.Response:
        """Make a POST request with a file upload (multipart/form-data).

        Args:
            path: API endpoint path.
            file: Tuple of (filename, content, content_type) for the file to upload. A
                None content_type is guessed from the filename.
            idempotency_key: Optional idempotency key for safe retries.

        Returns:
            The HTTP response.

        Raises:
            ServerError: When server error occurs and max retries are exhausted.
            ConflictError: For a 409 response, or when an idempotent request is
                still in progress after max retries are exhausted.
            RateLimitError: When rate limit is exceeded and max retries are exhausted.
            APIError: For other API error responses.
        """
        return self._request(
            "POST",
            path,
            files=self._multipart_file(file),
            headers=self._build_idempotency_headers(idempotency_key),
        )

    def _put_file(
        self,
        path: str,
        *,
        file: tuple[str, bytes, str | None],
        idempotency_key: str | None = None,
    ) -> httpx2.Response:
        """Make a PUT request with a file upload (multipart/form-data).

        Mirrors ``_post_file``: an idempotency key is sent only when supplied.

        Args:
            path: API endpoint path.
            file: Tuple of (filename, content, content_type) for the file to upload. A
                None content_type is guessed from the filename.
            idempotency_key: Optional idempotency key for safe retries.

        Returns:
            The HTTP response.

        Raises:
            ServerError: When server error occurs and max retries are exhausted.
            ConflictError: For a 409 response, or when an idempotent request is
                still in progress after max retries are exhausted.
            RateLimitError: When rate limit is exceeded and max retries are exhausted.
            APIError: For other API error responses.
        """
        return self._request(
            "PUT",
            path,
            files=self._multipart_file(file),
            headers=self._build_idempotency_headers(idempotency_key),
        )

    # -------------------------------------------------------------------------
    # Pagination Methods
    # -------------------------------------------------------------------------

    def _get_paginated(
        self,
        path: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        params: dict[str, Any] | None = None,
        max_limit: int = MAX_PAGE_LIMIT,
    ) -> PaginatedResponse[dict[str, Any]]:
        """Make a paginated GET request.

        Args:
            path: API endpoint path.
            limit: Maximum number of items to return (default 10).
            offset: Number of items to skip from the beginning (default 0).
            params: Additional query parameters.
            max_limit: Upper bound the limit is clamped to (default 100). Reference/catalog
                endpoints pass a higher bound (MAX_REFERENCE_PAGE_LIMIT).

        Returns:
            A PaginatedResponse containing the items and pagination metadata.
        """
        request_params = {
            "limit": min(max(limit, 0), max_limit),  # Clamp to valid range
            "offset": max(offset, 0),
            **(params or {}),
        }

        response = self._get(path, params=request_params)
        return PaginatedResponse.from_dict(response.json())

    def _get_paginated_as(
        self,
        path: str,
        model_class: type[T],
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        params: dict[str, Any] | None = None,
        max_limit: int = MAX_PAGE_LIMIT,
    ) -> PaginatedResponse[T]:
        """Make a paginated GET request and parse items into the given model class.

        Args:
            path: API endpoint path.
            model_class: Pydantic model class to validate each item into.
            limit: Maximum number of items to return (default 10).
            offset: Number of items to skip from the beginning (default 0).
            params: Additional query parameters.
            max_limit: Upper bound the limit is clamped to (default 100). Reference/catalog
                endpoints pass a higher bound (MAX_REFERENCE_PAGE_LIMIT).

        Returns:
            A PaginatedResponse containing validated model instances.
        """
        response = self._get_paginated(
            path, limit=limit, offset=offset, params=params, max_limit=max_limit
        )
        return PaginatedResponse(
            items=[model_class.model_validate(item) for item in response.items],
            limit=response.limit,
            offset=response.offset,
            total=response.total,
        )

    def _iter_all_pages(
        self,
        path: str,
        *,
        limit: int = MAX_PAGE_LIMIT,
        params: dict[str, Any] | None = None,
        max_limit: int = MAX_PAGE_LIMIT,
    ) -> Iterator[dict[str, Any]]:
        """Iterate through all pages of a paginated endpoint.

        Yields individual items from each page, automatically fetching
        subsequent pages until all items have been retrieved.

        Args:
            path: API endpoint path.
            limit: Items per page (default 100 for efficiency).
            params: Additional query parameters.
            max_limit: Upper bound the per-page limit is clamped to (default 100).
                Reference/catalog endpoints pass a higher bound (MAX_REFERENCE_PAGE_LIMIT).

        Yields:
            Individual items from the paginated response.

        Example:
            ```python
            for user in self._iter_all_pages("/users"):
                print(user["name"])
            ```
        """
        offset = 0

        while True:
            page = self._get_paginated(
                path,
                limit=limit,
                offset=offset,
                params=params,
                max_limit=max_limit,
            )

            yield from page.items

            if not page.has_more:
                break

            offset = page.next_offset

    def _iter_all_pages_as(
        self,
        path: str,
        model_class: type[T],
        *,
        limit: int = MAX_PAGE_LIMIT,
        params: dict[str, Any] | None = None,
        max_limit: int = MAX_PAGE_LIMIT,
    ) -> Iterator[T]:
        """Iterate through all pages of a paginated endpoint, parsing items into a model.

        Args:
            path: API endpoint path.
            model_class: Pydantic model class to validate each item into.
            limit: Items per page (default 100 for efficiency).
            params: Additional query parameters.
            max_limit: Upper bound the per-page limit is clamped to (default 100).

        Yields:
            Validated model instances, one per item.
        """
        for item in self._iter_all_pages(path, limit=limit, params=params, max_limit=max_limit):
            yield model_class.model_validate(item)
