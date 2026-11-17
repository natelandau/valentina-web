"""Fake HTTP router that maps endpoint patterns to factory-generated responses."""

from __future__ import annotations

import datetime as dt
import functools
import re
import secrets
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

import httpx2
from polyfactory.factories.pydantic_factory import ModelFactory

from vweb.api_client.constants import REQUEST_ID_HEADER
from vweb.api_client.routes import (
    LIST,
    NO_CONTENT,
    PAGINATED,
    RAW_JSON,
    Routes,
    RouteSpec,
)
from vweb.api_client.testing import _factories
from vweb.api_client.testing._recording import RecordedRequest, encode_query, record

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

type JsonBody = dict[str, Any] | list[dict[str, Any]]

_FACTORY_MAP: dict[type, type[ModelFactory]] = {
    factory.__model__: factory
    for factory in vars(_factories).values()
    if isinstance(factory, type)
    and issubclass(factory, ModelFactory)
    and "__model__" in vars(factory)
}


def _endpoint_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert an Endpoints pattern like '/api/v1/companies/{company_id}' to a regex.

    Path parameters become named capture groups so their values can be extracted
    for per-parameter response matching.
    """
    regex = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", pattern)
    return re.compile(f"^{regex}$")


def _collect_route_specs() -> list[RouteSpec]:
    """Collect all RouteSpec values from the Routes class."""
    return [
        getattr(Routes, name)
        for name in dir(Routes)
        if isinstance(getattr(Routes, name), RouteSpec)
    ]


def _literal_length(pattern: str) -> int:
    """Count the characters of a pattern outside its path parameters."""
    return len(re.sub(r"\{[^}]+\}", "", pattern))


def _decode_params(captured: dict[str, str]) -> dict[str, str]:
    """Percent-decode path parameter values captured from an encoded path."""
    return {key: unquote(value) for key, value in captured.items()}


@dataclass(frozen=True, slots=True)
class _Reply:
    """One canned HTTP response."""

    status_code: int
    json: JsonBody | None
    headers: dict[str, str] | None = None

    def to_response(self) -> httpx2.Response:
        """Build the httpx response for this reply."""
        if self.json is None:
            return httpx2.Response(status_code=self.status_code, headers=self.headers)
        return httpx2.Response(status_code=self.status_code, json=self.json, headers=self.headers)


class _Override:
    """A user-registered response for one route, optionally narrowed by path or query values.

    Each match takes the next reply in order, and the last reply repeats.
    """

    def __init__(  # noqa: PLR0913
        self,
        method: str,
        pattern: str,
        replies: Sequence[_Reply],
        *,
        params: Mapping[str, str] | None,
        query: Mapping[str, Any] | None,
        order: int,
        known_route: bool,
    ) -> None:
        if not replies:
            msg = f"Override for {method} {pattern} needs at least one reply"
            raise ValueError(msg)
        self.method = method.upper()
        self.pattern = pattern
        # A known route is matched through the request's resolved route, so only an
        # ad-hoc pattern needs its own regex
        self.regex = None if known_route else _endpoint_to_regex(pattern)
        self.replies = list(replies)
        self.params = dict(params or {})
        self.query = encode_query(query or {})
        self.order = order
        self._next = 0

    @property
    def rank(self) -> tuple[int, int]:
        """Sort key: more matched values first, then the most recently registered."""
        return (len(self.params) + len(self.query), self.order)

    def matches(self, request: RecordedRequest) -> bool:
        """Return True when the request's method, route, path values, and query satisfy this override.

        An override for a known route only answers requests that resolved to that route,
        so ``/users/{user_id}`` never answers ``/users/unapproved``.
        """
        if self.method != request.method:
            return False
        if self.regex is None:
            return (
                request.route is not None
                and request.route.pattern == self.pattern
                and request.matches(params=self.params, query=self.query)
            )
        m = self.regex.match(request.path)
        if m is None:
            return False
        captured = _decode_params(m.groupdict())
        return all(
            captured.get(key) == value for key, value in self.params.items()
        ) and request.matches(query=self.query)

    def take_reply(self) -> _Reply:
        """Return the next reply, repeating the last one once the sequence is used up."""
        reply = self.replies[min(self._next, len(self.replies) - 1)]
        self._next += 1
        return reply


class _DefaultRoute:
    """The factory-generated response for one `RouteSpec`."""

    def __init__(self, spec: RouteSpec) -> None:
        self.spec = spec
        self.regex = _endpoint_to_regex(spec.pattern)

    def respond(self) -> httpx2.Response:
        """Generate a response with factory-built data in the route's envelope."""
        style = self.spec.style
        if style == NO_CONTENT:
            return httpx2.Response(status_code=204)

        if style == RAW_JSON:
            return httpx2.Response(status_code=200, json={})

        if self.spec.model_class is None:
            msg = f"model_class required for style {style}"
            raise RuntimeError(msg)
        instance_data = _FACTORY_MAP[self.spec.model_class].build().model_dump(mode="json")

        if style == LIST:
            return httpx2.Response(status_code=200, json=[instance_data])

        if style == PAGINATED:
            body = {"items": [instance_data], "total": 1, "limit": 10, "offset": 0}
            return httpx2.Response(status_code=200, json=body)

        return httpx2.Response(status_code=200, json=instance_data)


@functools.cache
def _default_routes() -> tuple[_DefaultRoute, ...]:
    """Build the stateless default routes once, most literal pattern first.

    Ordering by literal length lets ``.../users/unapproved`` win over ``.../users/{user_id}``.
    """
    return tuple(
        sorted(
            (_DefaultRoute(spec) for spec in _collect_route_specs()),
            key=lambda route: _literal_length(route.spec.pattern),
            reverse=True,
        )
    )


class _FakeRouter:
    """Route HTTP requests to factory-generated responses and record every request.

    Provide default responses for all Valentina API endpoints using model factories,
    while allowing user overrides for specific routes. The client fetches pages and
    datasets on a thread pool, so all shared state sits behind one lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: list[_Override] = []
        self._requests: list[RecordedRequest] = []
        self._defaults = _default_routes()
        self._known_routes = frozenset(
            (route.spec.method, route.spec.pattern) for route in self._defaults
        )

    @property
    def requests(self) -> list[RecordedRequest]:
        """Return a snapshot of the recorded requests, oldest first."""
        with self._lock:
            return list(self._requests)

    def clear_requests(self) -> None:
        """Forget every recorded request."""
        with self._lock:
            self._requests.clear()

    def add_replies(
        self,
        method: str,
        pattern: str,
        replies: Sequence[_Reply],
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> None:
        """Register an override that answers matching requests with ``replies`` in order.

        Args:
            method: HTTP method (GET, POST, etc.).
            pattern: Endpoint pattern string from the Endpoints class.
            replies: Responses to return in order. The last one repeats.
            params: Path parameter values a request must carry.
            query: Query parameter values a request must carry.
        """
        with self._lock:
            self._overrides.append(
                _Override(
                    method,
                    pattern,
                    replies,
                    params=params,
                    query=query,
                    order=len(self._overrides),
                    known_route=(method.upper(), pattern) in self._known_routes,
                )
            )

    def add_route(
        self,
        method: str,
        pattern: str,
        *,
        json: JsonBody | None,
        status_code: int = 200,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Register a single-response override that takes precedence over defaults.

        Args:
            method: HTTP method (GET, POST, etc.).
            pattern: Endpoint pattern string from Endpoints class.
            json: Response body to return, or None for an empty body.
            status_code: HTTP status code to return.
            params: Optional path parameter values to match against.
            headers: Optional response headers to return.
        """
        self.add_replies(
            method,
            pattern,
            [_Reply(status_code=status_code, json=json, headers=headers)],
            params=params,
        )

    def _resolve(self, method: str, path: str) -> tuple[_DefaultRoute | None, dict[str, str]]:
        """Find the route a request targets and its path parameter values."""
        for route in self._defaults:
            if route.spec.method != method:
                continue
            m = route.regex.match(path)
            if m is not None:
                return route, _decode_params(m.groupdict())
        return None, {}

    def _select_override(self, request: RecordedRequest) -> _Override | None:
        """Pick the most specific override that matches a request."""
        candidates = [override for override in self._overrides if override.matches(request)]
        if not candidates:
            return None
        return max(candidates, key=lambda override: override.rank)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Record a request and return the matching override, default, or a 404.

        Among overrides that match, the one that pins the most path and query values
        wins, and a tie goes to the one registered last.

        Args:
            request: The incoming httpx2.Request to match.

        Returns:
            An httpx2.Response from the matched route, or a 404 if unmatched.
        """
        method = request.method.upper()
        # Match the encoded path so an id holding an encoded "/" stays one segment
        path = request.url.raw_path.decode("ascii").split("?", 1)[0]
        default, params = self._resolve(method, path)
        spec = default.spec if default is not None else None
        recorded = record(request, path=path, route=spec, params=params)

        with self._lock:
            self._requests.append(recorded)
            override = self._select_override(recorded)
            reply = override.take_reply() if override is not None else None

        if reply is not None:
            return self._finalize(reply.to_response())

        if default is not None:
            return self._finalize(default.respond())

        return self._finalize(
            httpx2.Response(
                status_code=404,
                json={"detail": f"No route matched: {method} {path}"},
            )
        )

    @staticmethod
    def _with_elapsed(response: httpx2.Response) -> None:
        """Set the elapsed time on a response so BaseService._request can log it."""
        response.elapsed = dt.timedelta(milliseconds=1)

    @staticmethod
    def _with_request_id(response: httpx2.Response) -> None:
        """Inject an X-Request-Id header into the response.

        Reuse an existing request_id from the response body when present so that
        the header and error body stay in sync (e.g. for set_error overrides).
        """
        try:
            body = response.json()
            existing = body.get("request_id") if isinstance(body, dict) else None
        except Exception:  # noqa: BLE001
            existing = None

        request_id = existing or f"req_{secrets.token_urlsafe(16)}"
        response.headers[REQUEST_ID_HEADER] = request_id

    def _finalize(self, response: httpx2.Response) -> httpx2.Response:
        """Apply elapsed time and request ID header to a response."""
        self._with_elapsed(response)
        self._with_request_id(response)
        return response
