"""Fake API client for testing downstream applications.

FakeVClient is a drop-in replacement for VClient that uses httpx2.MockTransport
instead of real HTTP. All real service classes work unmodified.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx2
from pydantic import BaseModel

from vweb.api_client.client import VClient
from vweb.api_client.routes import LIST, NO_CONTENT, PAGINATED
from vweb.api_client.testing._router import JsonBody, _FakeRouter, _Reply

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from vweb.api_client.routes import RouteSpec
    from vweb.api_client.testing._recording import RecordedRequest

_UNSET: Any = object()


@dataclass(frozen=True, slots=True)
class FakeResponse:
    """A successful response step for ``FakeVClient.set_responses()``.

    Attributes:
        items: Items for a paginated or list route.
        model: The object for a single-object route.
    """

    items: Sequence[BaseModel | dict[str, Any]] | None = None
    model: BaseModel | dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FakeError:
    """An error response step for ``FakeVClient.set_responses()``.

    Attributes:
        status_code: The HTTP status code.
        detail: The error detail message. Defaults to ``"Error {status_code}"`` when None;
            an empty string sends an empty detail.
        code: Machine-readable error code exposed as ``APIError.code``.
        invalid_parameters: Field errors as ``{"field": ..., "message": ...}`` dicts,
            exposed as ``ValidationError.field_errors`` on a 400.
        headers: Response headers, e.g. ``{"Retry-After": "1"}``.
    """

    status_code: int
    detail: str | None = None
    code: str | None = None
    invalid_parameters: Sequence[Mapping[str, str]] | None = None
    headers: dict[str, str] | None = None


class FakeVClient(VClient):
    """A fake VClient for testing that uses mock HTTP transport.

    Drop-in replacement for VClient that returns auto-generated responses
    for all endpoints. Registers itself as the default client so factory
    functions like campaigns_service() work without configuration.

    Important:
        When ``set_as_default=True`` (the default), FakeVClient registers itself
        as the global default client. If your application also creates a real
        ``VClient`` with ``set_as_default=True``, the **last one created wins**.
        Ensure FakeVClient is created **after** any real VClient to avoid the
        fake being silently overridden. In pytest, this means the fake client
        fixture must depend on the application fixture that creates the real client.

    Example:
        ```python
        from vweb.api_client.testing import FakeVClient
        from vweb.api_client import campaigns_service

        with FakeVClient() as client:
            campaigns = campaigns_service("user123")
            result = campaigns.list_all()
        ```
    """

    def __init__(
        self,
        *,
        default_company_id: str = "fake-company",
        set_as_default: bool = True,
        **kwargs: Any,
    ) -> None:
        self._router = _FakeRouter()
        # One attempt per request, so a faked 5xx or 429 is answered and recorded once
        kwargs.setdefault("max_retries", 0)
        super().__init__(
            base_url="https://fake.valentina-api.test",
            api_key="fake-api-key",
            default_company_id=default_company_id,
            set_as_default=set_as_default,
            **kwargs,
        )

    def _create_http_client(self) -> httpx2.Client:
        """Create an HTTP client backed by the fake router."""
        return httpx2.Client(
            transport=httpx2.MockTransport(self._router.handle),
            base_url="https://fake.valentina-api.test",
        )

    @property
    def requests(self) -> list[RecordedRequest]:
        """Return every request the fake API received, oldest first."""
        return self._router.requests

    def clear_requests(self) -> None:
        """Forget recorded requests, e.g. those made while arranging a test."""
        self._router.clear_requests()

    def requests_for(
        self,
        route: RouteSpec,
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> list[RecordedRequest]:
        """Return the recorded requests to ``route``, oldest first.

        Args:
            route: A ``RouteSpec`` from ``Routes``.
            params: Path parameter values every returned request must carry.
            query: Query parameter values every returned request must carry.

        Returns:
            The matching requests.
        """
        return [
            request
            for request in self.requests
            if request.is_for(route) and request.matches(params=params, query=query)
        ]

    def assert_called(
        self,
        route: RouteSpec,
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        json: Any = _UNSET,
        json_subset: Mapping[str, Any] | None = None,
        times: int | None = None,
    ) -> list[RecordedRequest]:
        """Assert the fake API received requests to ``route`` that match every given filter.

        Use this to check what reached the wire: the route, the ids in the path, the
        query, and the body.

        Args:
            route: A ``RouteSpec`` from ``Routes``.
            params: Path parameter values the requests must carry.
            query: Query parameter values the requests must carry.
            json: The exact JSON body the requests must carry.
            json_subset: Keys and values the JSON body must contain. Nested dicts
                match as subsets too.
            times: The exact number of matching requests. When None, at least one.

        Returns:
            The matching requests, oldest first.

        Raises:
            AssertionError: If the matching requests do not meet the expectation.
        """
        matched = [
            request
            for request in self.requests_for(route, params=params, query=query)
            if (json is _UNSET or request.json == json)
            and (json_subset is None or _contains(request.json, json_subset))
        ]
        expected = "at least 1" if times is None else str(times)
        if (times is None and not matched) or (times is not None and len(matched) != times):
            msg = (
                f"Expected {expected} {route.method} {route.pattern} request(s) matching "
                f"params={params} query={query} json={_describe(json)} "
                f"json_subset={json_subset}, found {len(matched)}.\n"
                f"Requests to this route: {self._summarize(self.requests_for(route))}"
            )
            raise AssertionError(msg)
        return matched

    def assert_not_called(
        self,
        route: RouteSpec,
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> None:
        """Assert the fake API received no request to ``route`` matching the filters.

        Args:
            route: A ``RouteSpec`` from ``Routes``.
            params: Path parameter values that narrow the check.
            query: Query parameter values that narrow the check.

        Raises:
            AssertionError: If a matching request was recorded.
        """
        matched = self.requests_for(route, params=params, query=query)
        if matched:
            msg = (
                f"Expected no {route.method} {route.pattern} request matching "
                f"params={params} query={query}, found {len(matched)}: "
                f"{self._summarize(matched)}"
            )
            raise AssertionError(msg)

    @staticmethod
    def _summarize(requests: Sequence[RecordedRequest]) -> list[str]:
        """Describe requests briefly for an assertion message."""
        return [f"{r.method} {r.path} query={r.query} json={r.json}" for r in requests]

    @staticmethod
    def _serialize(obj: BaseModel | dict[str, Any]) -> dict[str, Any]:
        """Serialize a model instance or pass through a dict."""
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        return obj

    def add_route(
        self,
        method: str,
        pattern: str,
        *,
        json: JsonBody,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Add a custom route override.

        Low-level method for full control over the response. Prefer
        ``set_response()`` or ``set_error()`` for most use cases.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, PUT).
            pattern: Endpoint pattern from vweb.api_client.endpoints.Endpoints.
            json: The JSON response body to return.
            status_code: HTTP status code to return (default 200).
            headers: Optional response headers to return (e.g. ``Retry-After``).
        """
        self._router.add_route(method, pattern, json=json, status_code=status_code, headers=headers)

    def set_response(
        self,
        route: RouteSpec,
        *,
        items: Sequence[BaseModel | dict[str, Any]] | None = None,
        model: BaseModel | dict[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> None:
        """Override a route to return specific response data.

        Automatically wraps data in the correct envelope based on the route's
        response style (paginated, single, or no-content). When several overrides
        match a request, the one that pins the most ``params`` and ``query`` values
        wins, and a tie goes to the one registered last.

        Args:
            route: A ``RouteSpec`` from the ``Routes`` class identifying the endpoint.
            items: List of items for paginated or list routes. Mutually exclusive with ``model``.
            model: A single model instance or dict for single-object routes.
                Mutually exclusive with ``items``.
            params: Optional path parameter values to match against. For example,
                ``params={"campaign_id": "abc"}`` only matches requests where
                ``{campaign_id}`` is ``"abc"``.
            query: Optional query parameter values to match against. For example,
                ``query={"email": "a@b.c"}`` only matches requests with that query value.
        """
        self.set_responses(
            route, [FakeResponse(items=items, model=model)], params=params, query=query
        )

    def set_error(  # noqa: PLR0913
        self,
        route: RouteSpec,
        *,
        status_code: int,
        detail: str | None = None,
        code: str | None = None,
        invalid_parameters: Sequence[Mapping[str, str]] | None = None,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Override a route to return an error response.

        Args:
            route: A ``RouteSpec`` from the ``Routes`` class identifying the endpoint.
            status_code: The HTTP status code to return.
            detail: Optional error detail message. Defaults to ``"Error {status_code}"``
                when None; an empty string sends an empty detail.
            code: Optional machine-readable error code, an RFC 9457 extension
                member exposed as ``APIError.code`` (e.g.
                ``"TOKEN_VERIFICATION_FAILED"``). Omitted from the body when not set.
            invalid_parameters: Optional field errors as ``{"field": ..., "message": ...}``
                dicts. With ``status_code=400`` the client raises ``ValidationError``
                with these as ``field_errors``.
            params: Optional path parameter values to match against.
            query: Optional query parameter values to match against.
            headers: Optional response headers to return, e.g.
                ``{"Retry-After": "1"}`` to fake ``ConflictError.retry_after``.
        """
        error = FakeError(
            status_code=status_code,
            detail=detail,
            code=code,
            invalid_parameters=invalid_parameters,
            headers=headers,
        )
        self.set_responses(route, [error], params=params, query=query)

    def set_responses(
        self,
        route: RouteSpec,
        responses: Sequence[FakeResponse | FakeError],
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> None:
        """Override a route to return a different response on each call.

        Each matching request takes the next response, and the last one repeats.
        Use it for retry, fallback, and refetch flows, e.g. a 404 then a model.

        Args:
            route: A ``RouteSpec`` from the ``Routes`` class identifying the endpoint.
            responses: ``FakeResponse`` and ``FakeError`` steps, in call order.
            params: Optional path parameter values to match against.
            query: Optional query parameter values to match against.
        """
        replies = [
            self._error_reply(step)
            if isinstance(step, FakeError)
            else self._success_reply(route, step)
            for step in responses
        ]
        self._router.add_replies(route.method, route.pattern, replies, params=params, query=query)

    def _success_reply(self, route: RouteSpec, step: FakeResponse) -> _Reply:
        """Wrap response data in the envelope the route's style calls for.

        Raises:
            TypeError: If ``model`` is passed to a paginated/list route or ``items`` is
                passed to a single-object route.
        """
        pattern, style = route.pattern, route.style

        if style in {PAGINATED, LIST}:
            if step.model is not None:
                msg = f"Route {pattern!r} returns {style} data; pass 'items' instead of 'model'"
                raise TypeError(msg)
            serialized = [self._serialize(item) for item in (step.items or [])]
            if style == LIST:
                return _Reply(status_code=200, json=serialized)
            body = {"items": serialized, "total": len(serialized), "limit": 100, "offset": 0}
            return _Reply(status_code=200, json=body)

        if style == NO_CONTENT:
            return _Reply(status_code=204, json=None)

        if step.items is not None:
            msg = f"Route {pattern!r} returns a single object; pass 'model' instead of 'items'"
            raise TypeError(msg)
        data = self._serialize(step.model) if step.model is not None else {}
        return _Reply(status_code=200, json=data)

    @staticmethod
    def _error_reply(step: FakeError) -> _Reply:
        """Build an RFC 9457 problem body the client parses into an ``APIError``."""
        body: dict[str, Any] = {
            "detail": f"Error {step.status_code}" if step.detail is None else step.detail,
            "request_id": f"req_{secrets.token_urlsafe(16)}",
        }
        if step.code is not None:
            body["code"] = step.code
        if step.invalid_parameters is not None:
            body["invalid_parameters"] = [dict(param) for param in step.invalid_parameters]
        return _Reply(status_code=step.status_code, json=body, headers=step.headers)


def _contains(actual: Any, expected: Mapping[str, Any]) -> bool:
    """Return True when dict ``actual`` holds every key of ``expected`` with equal values."""
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if isinstance(value, dict) and isinstance(actual[key], dict):
            if not _contains(actual[key], value):
                return False
        elif actual[key] != value:
            return False
    return True


def _describe(json: Any) -> str:
    """Show an unset ``json`` filter as ``<any>`` in assertion messages."""
    return "<any>" if json is _UNSET else repr(json)
