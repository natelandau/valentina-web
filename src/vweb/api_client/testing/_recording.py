"""Requests that `FakeVClient` received, recorded for wire-level assertions."""

from __future__ import annotations

import json as jsonlib
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import HTTP
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

import httpx2

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vweb.api_client.routes import RouteSpec


@dataclass(frozen=True, slots=True)
class RecordedFile:
    """One file part of a multipart request.

    Attributes:
        filename: The filename the client sent, or None.
        content_type: The part's content type, or None.
        content: The file's bytes.
    """

    filename: str | None
    content_type: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    """One HTTP request as the fake API received it.

    Attributes:
        method: The HTTP method, uppercase.
        path: The URL path as sent, percent-encoded, without the query string.
        route: The ``RouteSpec`` the path resolved to, or None when no route matched.
        params: Path parameter values captured from the route pattern.
        query: Query parameters. A repeated key keeps its last value.
        json: The decoded JSON body, or None when the body is not JSON.
        form: Non-file fields of a form or multipart body.
        files: File parts of a multipart body, keyed by field name.
        headers: Request headers with lowercase names.
    """

    method: str
    path: str
    route: RouteSpec | None
    params: dict[str, str]
    query: dict[str, str]
    json: Any
    form: dict[str, str] = field(default_factory=dict)
    files: dict[str, RecordedFile] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def is_for(self, route: RouteSpec) -> bool:
        """Return True when this request resolved to ``route``.

        Routes are compared by method and pattern, so two specs that name the same
        endpoint match the same requests.

        Args:
            route: The route to compare against.
        """
        return (
            self.route is not None
            and self.route.method == route.method
            and self.route.pattern == route.pattern
        )

    def matches(
        self,
        *,
        params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return True when the request carries every given path and query value.

        Args:
            params: Path parameter values that must all match.
            query: Query parameter values that must all match. Values are encoded the
                way the client encodes them, so ``True`` matches ``"true"``.
        """
        if params and any(self.params.get(key) != value for key, value in params.items()):
            return False
        return not query or all(
            self.query.get(key) == value for key, value in encode_query(query).items()
        )


def encode_query(query: Mapping[str, Any]) -> dict[str, str]:
    """Encode query values to the strings that appear on the wire.

    Args:
        query: Query values as a test or the client passes them.

    Returns:
        The values as httpx encodes them in a URL.

    Raises:
        TypeError: If a value encodes to more than one query item, because a recorded
            request keeps only the last value of a repeated key.
    """
    items = httpx2.QueryParams(dict(query)).multi_items()
    encoded = dict(items)
    if len(encoded) != len(items):
        msg = f"Query filters take one value per key, got {dict(query)!r}"
        raise TypeError(msg)
    return encoded


def record(
    request: httpx2.Request, *, path: str, route: RouteSpec | None, params: dict[str, str]
) -> RecordedRequest:
    """Build a `RecordedRequest` from an outgoing httpx request.

    Args:
        request: The request the client sent.
        path: The percent-encoded URL path without the query string.
        route: The route the request resolved to, or None.
        params: Path parameter values captured from the route pattern.

    Returns:
        The recorded request.
    """
    content = request.read()
    content_type = request.headers.get("content-type", "")
    body_json: Any = None
    form: dict[str, str] = {}
    files: dict[str, RecordedFile] = {}

    if content and "json" in content_type:
        body_json = jsonlib.loads(content)
    elif content and content_type.startswith("multipart/form-data"):
        form, files = _parse_multipart(content, content_type)
    elif content and content_type.startswith("application/x-www-form-urlencoded"):
        form = dict(parse_qsl(content.decode()))

    return RecordedRequest(
        method=request.method.upper(),
        path=path,
        route=route,
        params=params,
        query=dict(request.url.params.multi_items()),
        json=body_json,
        form=form,
        files=files,
        headers={name.lower(): value for name, value in request.headers.items()},
    )


def _parse_multipart(
    content: bytes, content_type: str
) -> tuple[dict[str, str], dict[str, RecordedFile]]:
    """Split a multipart body into form fields and file parts."""
    message = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + content
    )
    form: dict[str, str] = {}
    files: dict[str, RecordedFile] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str):
            continue
        payload = part.get_payload(decode=True)
        data = payload if isinstance(payload, bytes) else b""
        filename = part.get_filename()
        if filename is None:
            form[name] = data.decode()
        else:
            files[name] = RecordedFile(
                filename=filename,
                content_type=part.get_content_type(),
                content=data,
            )
    return form, files
