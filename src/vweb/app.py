"""Application factory and entry point."""

from __future__ import annotations

import atexit
from datetime import timedelta
from typing import TYPE_CHECKING

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from vclient import SyncVClient
from werkzeug.middleware.proxy_fix import ProxyFix

if TYPE_CHECKING:
    from collections.abc import Iterable

    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment


from vweb.config import Settings, get_settings
from vweb.constants import STATIC_PATH, TEMPLATES_PATH
from vweb.extensions import cache
from vweb.lib.errors import register_error_handlers
from vweb.lib.hooks import register_before_request_hooks
from vweb.lib.jinja import configure_jinja, register_jinjax_catalog
from vweb.lib.log_config import instantiate_logger
from vweb.lib.oauth_setup import register_oauth_providers
from vweb.lib.security import configure_security

catalog = register_jinjax_catalog()


class _CloudflareIPMiddleware:
    """Prefer Cloudflare's CF-Connecting-IP header for the real client IP.

    Cloudflare sets this header to the true client address regardless of how many
    proxies sit between it and the application. When present it overwrites
    REMOTE_ADDR so that ``request.remote_addr`` returns the real IP. When absent
    the inner middleware (typically ProxyFix) determines the address instead.
    """

    def __init__(self, app: WSGIApplication) -> None:
        self._app = app

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        cf_ip = environ.get("HTTP_CF_CONNECTING_IP")
        if cf_ip:
            environ["REMOTE_ADDR"] = cf_ip
        return self._app(environ, start_response)


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


def create_app(settings_override: Settings | None = None) -> Flask:
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

    # Cloudflare → Railway → Flask: two reverse proxies terminate TLS.
    # ProxyFix with x_for=2 resolves the real client IP from X-Forwarded-For as a fallback;
    # _CloudflareIPMiddleware overrides REMOTE_ADDR with CF-Connecting-IP when present.
    app.wsgi_app = _CloudflareIPMiddleware(  # ty:ignore[invalid-assignment]
        ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1)
    )

    app.secret_key = s.secret_key
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SETTINGS"] = s
    CSRFProtect(app)
    _configure_cache_and_session(app, s)

    register_oauth_providers(app, s)
    configure_security(app, s)

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
    )

    def _cleanup() -> None:
        client = app.extensions.get("vclient")
        if client and not client.is_closed:
            client.close()

    atexit.register(_cleanup)

    configure_jinja(app, s, catalog)
    register_before_request_hooks(app)
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
