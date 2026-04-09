"""Before-request hooks for the vweb application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g, redirect, request, session, url_for

from vweb.lib.global_context import clear_global_context_cache, load_global_context

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.wrappers.response import Response

_PUBLIC_PATH_PREFIXES = ("/auth/", "/static")


def _hook_remove_trailing_slash() -> Response | None:
    """Redirect trailing-slash URLs to their canonical form."""
    rp: str = request.path
    if rp != "/" and rp.endswith("/"):
        return redirect(rp[:-1], 301)

    return None


def _hook_refresh_session() -> None:
    """Refresh permanent session expiry on each visit."""
    if request.path.startswith("/static"):
        return

    session.modified = True


def _hook_require_auth() -> Response | None:
    """Redirect unauthenticated users to the landing page."""
    if request.path == "/" or request.path.startswith(_PUBLIC_PATH_PREFIXES):
        return None

    if not session.get("user_id"):
        return redirect(url_for("index.index"))

    return None


def _hook_inject_global_context() -> Response | None:
    """Load cached global context and resolve the requesting user for template access."""
    if request.path.startswith(_PUBLIC_PATH_PREFIXES) or request.path == "/pending-approval":
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
    app.before_request(_hook_remove_trailing_slash)
    app.before_request(_hook_refresh_session)
    app.before_request(_hook_require_auth)
    app.before_request(_hook_inject_global_context)
    app.before_request(_hook_redirect_unapproved)
