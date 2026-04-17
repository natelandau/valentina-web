"""Before-request hooks for the vweb application."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flask import abort, g, redirect, request, session, url_for
from loguru import logger

from vweb.lib.global_context import clear_global_context_cache, load_global_context

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.wrappers.response import Response

_PUBLIC_PATH_PREFIXES = ("/auth/", "/static", "/robots.txt")
_COMPANY_SELECTION_PATHS = ("/select-companies", "/select-company")

_SCANNER_DOT_EXEMPTIONS = frozenset({".well-known"})
_SCANNER_BLOCKED_PREFIXES = (
    "/wp-",
    "/wordpress",
    "/phpmyadmin",
    "/pma",
    "/adminer",
    "/cgi-bin",
    "/xmlrpc",
    "/laravel",
    "/react-app",
    "/vue-app",
    "/kube",
    "/var/",
    "/cpanel",
)
_SCANNER_BLOCKED_SUFFIXES = (
    ".php",
    ".asp",
    ".aspx",
    ".jsp",
    ".cgi",
    "config.json",
    ".yml",
    "mcp.json",
    "sitemap.xml",
)
_SCANNER_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.env\.?|phpinfo"),  # .env, .env.production, .env.local, .env.backup, etc.
]


def _block_probe() -> None:
    """Log a blocked scanner probe at debug level and abort with 404."""
    logger.debug(
        "Blocked scanner probe: {path} from {ip}", path=request.path, ip=request.remote_addr
    )
    abort(404)


def _hook_block_scanner_probes() -> Response | None:
    """Return 404 for paths commonly targeted by vulnerability scanners.

    Catch dotfile access, CMS admin paths, non-Python script extensions, and
    regex-matched patterns before any session or template work runs.
    """
    path = request.path.lower()

    for segment in path.split("/"):
        if segment.startswith(".") and segment not in _SCANNER_DOT_EXEMPTIONS:
            _block_probe()

    if path.startswith(_SCANNER_BLOCKED_PREFIXES):
        _block_probe()

    if path.endswith(_SCANNER_BLOCKED_SUFFIXES):
        _block_probe()

    for pattern in _SCANNER_BLOCKED_PATTERNS:
        if pattern.search(path):
            _block_probe()

    return None


def _hook_remove_trailing_slash() -> Response | None:
    """Redirect trailing-slash URLs to their canonical form."""
    rp: str = request.path
    if rp != "/" and rp.endswith("/"):
        return redirect(rp[:-1], 301)

    return None


def _hook_refresh_session() -> None:
    """Refresh permanent session expiry on each visit."""
    if request.path.startswith(_PUBLIC_PATH_PREFIXES):
        return

    session.modified = True


def _hook_require_auth() -> Response | None:
    """Redirect unauthenticated users to the landing page."""
    if (
        request.path == "/"
        or request.path.startswith(_PUBLIC_PATH_PREFIXES)
        or request.path in _COMPANY_SELECTION_PATHS
    ):
        return None

    if not session.get("user_id"):
        return redirect(url_for("index.index"))

    return None


def _hook_inject_global_context() -> Response | None:
    """Load cached global context and resolve the requesting user for template access."""
    if (
        request.path.startswith(_PUBLIC_PATH_PREFIXES)
        or request.path == "/pending-approval"
        or request.path in _COMPANY_SELECTION_PATHS
    ):
        return None

    user_id = session.get("user_id")
    company_id = session.get("company_id")
    if not user_id or not company_id:
        return None

    ctx = load_global_context(company_id, user_id)
    g.global_context = ctx

    requesting_user = next((u for u in ctx.users if u.id == user_id), None)
    if requesting_user is None:
        clear_global_context_cache(company_id, user_id)
        ctx = load_global_context(company_id, user_id)
        g.global_context = ctx
        requesting_user = next((u for u in ctx.users if u.id == user_id), None)

    if requesting_user is None:
        session.clear()
        return redirect(url_for("index.index"))

    g.requesting_user = requesting_user
    return None


def _hook_redirect_unapproved() -> Response | None:
    """Redirect unapproved users to the pending approval page."""
    requesting_user = g.get("requesting_user")
    if not requesting_user:
        return None

    if requesting_user.role == "UNAPPROVED" and request.path not in (
        "/pending-approval",
        "/",
    ):
        return redirect(url_for("auth.pending_approval"))

    return None


def register_before_request_hooks(app: Flask) -> None:
    """Register before-request hooks on the app.

    Args:
        app: The Flask application instance.
    """
    app.before_request(_hook_block_scanner_probes)
    app.before_request(_hook_remove_trailing_slash)
    app.before_request(_hook_refresh_session)
    app.before_request(_hook_require_auth)
    app.before_request(_hook_inject_global_context)
    app.before_request(_hook_redirect_unapproved)
