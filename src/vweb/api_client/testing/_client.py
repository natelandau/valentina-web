"""Fake API client for testing downstream applications.

FakeVClient is a drop-in replacement for VClient that uses httpx2.MockTransport
instead of real HTTP. All real service classes work unmodified.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

import httpx2
from pydantic import BaseModel

from vweb.api_client.client import VClient
from vweb.api_client.testing._router import _FakeRouter
from vweb.api_client.testing._routes import LIST, NO_CONTENT, PAGINATED

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vweb.api_client.testing._routes import RouteSpec


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
        json: dict[str, Any] | list[dict[str, Any]],
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
        params: dict[str, str] | None = None,
    ) -> None:
        """Override a route to return specific response data.

        Automatically wraps data in the correct envelope based on the route's
        response style (paginated, single, or no-content).

        Args:
            route: A ``RouteSpec`` from the ``Routes`` class identifying the endpoint.
            items: List of items for paginated or list routes. Mutually exclusive with ``model``.
            model: A single model instance or dict for single-object routes.
                Mutually exclusive with ``items``.
            params: Optional path parameter values to match against. When set,
                the override only applies to requests whose URL path segments match
                all specified values. For example,
                ``params={"campaign_id": "abc"}`` only matches requests where
                ``{campaign_id}`` is ``"abc"``.

        Raises:
            TypeError: If ``model`` is passed to a paginated/list route or ``items`` is
                passed to a single-object route.
        """
        method, pattern, style = route.method, route.pattern, route.style

        if style == PAGINATED:
            if model is not None:
                msg = f"Route {pattern!r} is paginated; pass 'items' instead of 'model'"
                raise TypeError(msg)

            serialized: list[dict[str, Any]] = [self._serialize(item) for item in (items or [])]
            body: dict[str, Any] = {
                "items": serialized,
                "total": len(serialized),
                "limit": 100,
                "offset": 0,
            }
            self._router.add_route(method, pattern, json=body, status_code=200, params=params)

        elif style == LIST:
            if model is not None:
                msg = f"Route {pattern!r} returns a list; pass 'items' instead of 'model'"
                raise TypeError(msg)

            serialized_list: list[dict[str, Any]] = [
                self._serialize(item) for item in (items or [])
            ]
            self._router.add_route(
                method, pattern, json=serialized_list, status_code=200, params=params
            )

        elif style == NO_CONTENT:
            self._router.add_route(method, pattern, json={}, status_code=204, params=params)

        else:
            if items is not None:
                msg = f"Route {pattern!r} returns a single object; pass 'model' instead of 'items'"
                raise TypeError(msg)

            data: dict[str, Any] = self._serialize(model) if model is not None else {}
            self._router.add_route(method, pattern, json=data, status_code=200, params=params)

    def set_error(
        self,
        route: RouteSpec,
        *,
        status_code: int,
        detail: str | None = None,
        code: str | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Override a route to return an error response.

        Args:
            route: A ``RouteSpec`` from the ``Routes`` class identifying the endpoint.
            status_code: The HTTP status code to return.
            detail: Optional error detail message. Defaults to ``"Error {status_code}"``.
            code: Optional machine-readable error code, an RFC 9457 extension
                member exposed as ``APIError.code`` (e.g.
                ``"TOKEN_VERIFICATION_FAILED"``). Omitted from the body when not set.
            params: Optional path parameter values to match against. When set,
                the error override only applies to requests whose URL path segments
                match all specified values.
            headers: Optional response headers to return, e.g.
                ``{"Retry-After": "1"}`` to fake ``ConflictError.retry_after``.
        """
        method, pattern = route.method, route.pattern
        request_id = f"req_{secrets.token_urlsafe(16)}"
        body: dict[str, Any] = {
            "detail": detail or f"Error {status_code}",
            "request_id": request_id,
        }
        if code is not None:
            body["code"] = code
        self._router.add_route(
            method, pattern, json=body, status_code=status_code, params=params, headers=headers
        )
