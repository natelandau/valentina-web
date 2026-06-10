"""HTMX response helpers for the vweb application."""

from __future__ import annotations

from flask import Response
from markupsafe import Markup

from vweb.lib.catalog import catalog


def hx_redirect(url: str) -> Response:
    """Return an empty 200 response with an ``HX-Redirect`` header.

    Args:
        url: The URL to redirect to.

    Returns:
        A Flask Response that tells HTMX to perform a client-side redirect.
    """
    return Response("", status=200, headers={"HX-Redirect": url})


def htmx_response(*parts: str) -> Markup:
    """Concatenate HTML fragments into a single HTMX response without escaping.

    Safely join rendered HTML strings (from ``render_template`` and
    ``catalog.render``) that may be a mix of plain ``str`` and ``Markup``.
    Without this, ``Markup.__radd__`` escapes any plain-string neighbors.

    Args:
        *parts: Rendered HTML strings to concatenate.

    Returns:
        Markup: The combined HTML, safe for return from a route.
    """
    return Markup("".join(parts))  # noqa: S704


def htmx_response_with_flash(content: str) -> Markup:
    """Return an HTMX response that OOB-swaps the flash container.

    Any HTMX endpoint that calls ``flash()`` must include the flash container
    in the response or the toast silently drops. Use this helper in place of
    the manual ``catalog.render("shared.layout.FlashMessage", oob=True)`` +
    ``htmx_response(...)`` pairing.
    """
    flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
    return htmx_response(content, flash_html)
