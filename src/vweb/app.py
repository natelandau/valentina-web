"""Application factory and entry point."""

from __future__ import annotations

import atexit
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from flask import Flask, g, redirect, request, session, url_for
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from vclient import SyncVClient

import vweb
from vweb.config import Settings, get_settings
from vweb.constants import MAX_IMAGE_SIZE, STATIC_PATH, TEMPLATES_PATH
from vweb.extensions import cache, oauth
from vweb.lib.blueprint_cache import get_all_traits
from vweb.lib.errors import register_error_handlers
from vweb.lib.global_context import clear_global_context_cache, load_global_context
from vweb.lib.guards import (
    can_edit_character,
    can_edit_traits_free,
    can_grant_experience,
    can_manage_campaign,
    is_admin,
    is_self,
    is_storyteller,
)
from vweb.lib.jinja import register_jinjax_catalog, static_url
from vweb.lib.log_config import instantiate_logger
from vweb.lib.options_cache import get_options

if TYPE_CHECKING:
    from vclient.models import User
    from werkzeug.wrappers.response import Response

    from vweb.lib.global_context import GlobalContext

catalog = register_jinjax_catalog()


def _configure_jinja(app: Flask, s: Settings) -> None:
    """Set up Jinja2 globals and sync the JinjaX catalog environment.

    Args:
        app: The Flask application instance.
        s: The application settings.
    """
    app.jinja_env.add_extension("jinja2.ext.loopcontrols")
    jinja_globals = cast("dict[str, Any]", app.jinja_env.globals)
    jinja_globals["catalog"] = catalog
    jinja_globals["app_name"] = s.app_name
    jinja_globals["version"] = vweb.__version__
    jinja_globals["static_url"] = static_url
    jinja_globals["oauth_discord_enabled"] = bool(s.oauth.discord.client_id)
    jinja_globals["oauth_github_enabled"] = bool(s.oauth.github.client_id)
    jinja_globals["oauth_google_enabled"] = bool(s.oauth.google.client_id)

    def _get_global_context() -> GlobalContext | None:
        return g.get("global_context")

    jinja_globals["global_context"] = _get_global_context

    def _get_requesting_user() -> User | None:
        return g.get("requesting_user")

    jinja_globals["requesting_user"] = _get_requesting_user
    jinja_globals["get_all_traits"] = get_all_traits
    jinja_globals["get_options"] = get_options
    jinja_globals["MAX_IMAGE_SIZE"] = MAX_IMAGE_SIZE
    jinja_globals["is_admin"] = is_admin
    jinja_globals["is_storyteller"] = is_storyteller
    jinja_globals["is_self"] = is_self
    jinja_globals["can_manage_campaign"] = can_manage_campaign
    jinja_globals["can_grant_experience"] = can_grant_experience
    jinja_globals["can_edit_traits_free"] = can_edit_traits_free
    jinja_globals["can_edit_character"] = can_edit_character

    # Sync Flask's Jinja2 environment into the catalog's environment so
    # JinjaX components have access to url_for, config, and other app globals
    catalog.jinja_env.globals.update(app.jinja_env.globals)
    catalog.jinja_env.filters.update(app.jinja_env.filters)
    catalog.jinja_env.tests.update(app.jinja_env.tests)
    catalog.jinja_env.extensions.update(app.jinja_env.extensions)


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
    if not user_id:
        return None

    ctx = load_global_context()
    g.global_context = ctx

    requesting_user = next((u for u in ctx.users if u.id == user_id), None)
    if requesting_user is None:
        clear_global_context_cache()
        ctx = load_global_context()
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


def _register_before_request_hooks(app: Flask) -> None:
    """Register before-request hooks on the app.

    Args:
        app: The Flask application instance.
    """
    app.before_request(_hook_remove_trailing_slash)
    app.before_request(_hook_refresh_session)
    app.before_request(_hook_require_auth)
    app.before_request(_hook_inject_global_context)
    app.before_request(_hook_redirect_unapproved)


def _configure_cache_and_session(app: Flask, s: Settings) -> None:
    """Set up Flask-Caching and server-side sessions, using Redis when configured.

    Args:
        app: The Flask application instance.
        s: The application settings.
    """
    if s.redis.url:
        app.config["CACHE_TYPE"] = "RedisCache"
        app.config["CACHE_REDIS_URL"] = s.redis.url
        app.config["CACHE_DEFAULT_TIMEOUT"] = s.redis.default_timeout
        app.config["CACHE_KEY_PREFIX"] = s.redis.key_prefix

    else:
        app.config["CACHE_TYPE"] = "SimpleCache"
        app.config["CACHE_DEFAULT_TIMEOUT"] = s.redis.default_timeout
        app.config["CACHE_KEY_PREFIX"] = s.redis.key_prefix
    cache.init_app(app)

    if s.redis.url:
        import redis
        from flask_session import Session

        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis.from_url(s.redis.url)
        Session(app)


def create_app(settings_override: Settings | None = None) -> Flask:  # noqa: PLR0915
    """Create and configure the Flask application.

    Args:
        settings_override: Optional settings instance for testing; falls back to the
            lazy singleton when not provided.

    Returns:
        The configured application instance.
    """
    s = settings_override or get_settings()

    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_PATH),
        static_folder=str(STATIC_PATH),
    )

    app.secret_key = s.secret_key
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SETTINGS"] = s
    CSRFProtect(app)
    _configure_cache_and_session(app, s)

    oauth.init_app(app)
    if s.oauth.discord.client_id:
        oauth.register(
            name="discord",
            client_id=s.oauth.discord.client_id,
            client_secret=s.oauth.discord.client_secret,
            access_token_url="https://discord.com/api/oauth2/token",  # noqa: S106
            authorize_url="https://discord.com/oauth2/authorize",
            api_base_url="https://discord.com/api/v10/",
            client_kwargs={"scope": "identify email"},
        )

    if s.oauth.github.client_id:
        oauth.register(
            name="github",
            client_id=s.oauth.github.client_id,
            client_secret=s.oauth.github.client_secret,
            access_token_url="https://github.com/login/oauth/access_token",  # noqa: S106
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "user:email read:user"},
        )

    if s.oauth.google.client_id:
        oauth.register(
            name="google",
            client_id=s.oauth.google.client_id,
            client_secret=s.oauth.google.client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    script_src = [
        "'self'",
        "'unsafe-eval'",
        "unpkg.com",
        "kit.fontawesome.com",
        "ka-f.fontawesome.com",
    ]
    if s.env == "development":
        script_src.append("'unsafe-inline'")

    csp = {
        "default-src": "'self'",
        "script-src": script_src,
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "ka-f.fontawesome.com",
            "fonts.googleapis.com",
        ],
        "font-src": [
            "'self'",
            "ka-f.fontawesome.com",
            "fonts.gstatic.com",
        ],
        "img-src": [
            "'self'",
            "data:",
            "cdn.discordapp.com",
            "cdn.valentina-noir.com",
            "avatars.githubusercontent.com",
            "lh3.googleusercontent.com",
            "img.daisyui.com",
            "cdn.midjourney.com",
        ],
        "connect-src": [
            "'self'",
            "ka-f.fontawesome.com",
        ],
    }
    Talisman(
        app,
        force_https=s.env == "production",
        session_cookie_secure=s.env == "production",
        session_cookie_http_only=True,
        content_security_policy=csp,
    )

    if s.env == "development":
        from flask_debugtoolbar import DebugToolbarExtension

        app.config["DEBUG"] = True
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
        if s.debug_toolbar:
            DebugToolbarExtension(app)

    from vweb.routes.auth.views import bp as auth_bp
    from vweb.routes.book.views import bp as book_view_bp
    from vweb.routes.campaign.views import bp as campaign_bp
    from vweb.routes.chapter.views import bp as chapter_view_bp
    from vweb.routes.character_create import bp as character_create_bp
    from vweb.routes.character_trait_edit.views import bp as character_trait_edit_bp
    from vweb.routes.character_view.views import bp as character_view_bp
    from vweb.routes.diceroll.views import bp as diceroll_bp
    from vweb.routes.dictionary.views import bp as dictionary_bp
    from vweb.routes.index.views import bp as index_bp
    from vweb.routes.profile.views import bp as profile_bp
    from vweb.routes.settings.views import bp as settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(index_bp)
    app.register_blueprint(campaign_bp)
    app.register_blueprint(character_view_bp)
    app.register_blueprint(character_trait_edit_bp)
    app.register_blueprint(book_view_bp)
    app.register_blueprint(chapter_view_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(diceroll_bp)
    app.register_blueprint(dictionary_bp)
    app.register_blueprint(character_create_bp)
    app.register_blueprint(settings_bp)

    app.extensions["vclient"] = SyncVClient(
        base_url=s.api.base_url,
        api_key=s.api.api_key,
        timeout=s.api.timeout,
        max_retries=s.api.max_retries,
        retry_delay=s.api.retry_delay,
        auto_retry_rate_limit=s.api.auto_retry_rate_limit,
        auto_idempotency_keys=s.api.auto_idempotency_keys,
        default_company_id=s.api.default_company_id,
    )

    def _cleanup() -> None:
        client = app.extensions.get("vclient")
        if client and not client.is_closed:
            client.close()

    atexit.register(_cleanup)

    _configure_jinja(app, s)
    _register_before_request_hooks(app)
    register_error_handlers(app)

    return app


def main() -> None:
    """Entry point for the vweb CLI command."""
    s = get_settings()
    instantiate_logger()
    app = create_app(settings_override=s)

    if s.env == "development":
        # Flask's built-in runner watches loaded Python modules for changes and
        # restarts automatically.
        app.run(host=s.host, port=s.port, debug=True, use_reloader=True)
    else:
        import subprocess
        import sys

        from loguru import logger

        logger.debug("Starting gunicorn with {} workers", s.workers)
        sys.exit(
            subprocess.call(  # noqa: S603
                [  # noqa: S607
                    "gunicorn",
                    "--bind",
                    f"{s.host}:{s.port}",
                    "--workers",
                    str(s.workers),
                    "--access-logfile",
                    s.access_log,
                    "vweb:create_app()",
                ],
            )
        )
