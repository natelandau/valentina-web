"""Application factory and entry point."""

from __future__ import annotations

import atexit
from datetime import timedelta
from typing import TYPE_CHECKING

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from vclient import SyncVClient

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


class _RealIPMiddleware:
    """Resolve the real client IP from reverse-proxy headers.

    Resolution order:
    1. ``CF-Connecting-IP`` — set by Cloudflare, most reliable when present.
    2. ``X-Forwarded-For`` — standard multi-proxy header. The client IP is
       extracted by skipping ``trusted_proxy_depth`` entries from the right.
    3. Raw ``REMOTE_ADDR`` — unchanged socket peer address as a final fallback.

    ``X-Forwarded-Proto`` and ``X-Forwarded-Host`` are also forwarded so Flask
    generates correct URLs behind TLS-terminating proxies.  These headers are
    trusted unconditionally (first value wins) — deploy behind at least one
    proxy that sets them, or strip them at the edge to prevent spoofing.

    Args:
        app: The inner WSGI application.
        trusted_proxy_depth: Number of trusted proxies between the client and
            this application.  Used only for ``X-Forwarded-For`` resolution.
    """

    def __init__(self, app: WSGIApplication, *, trusted_proxy_depth: int = 1) -> None:
        self._app = app
        self._depth = trusted_proxy_depth

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        real_ip = self._resolve_ip(environ)
        if real_ip:
            environ["REMOTE_ADDR"] = real_ip

        # Trust the first X-Forwarded-Proto/Host value so Flask generates
        # correct URLs and detects HTTPS behind reverse proxies.
        proto = environ.get("HTTP_X_FORWARDED_PROTO")
        if proto:
            environ["wsgi.url_scheme"] = proto.split(",")[0].strip()

        host = environ.get("HTTP_X_FORWARDED_HOST")
        if host:
            environ["HTTP_HOST"] = host.split(",")[0].strip()

        return self._app(environ, start_response)

    def _resolve_ip(self, environ: WSGIEnvironment) -> str | None:
        """Return the best-guess client IP, or None to keep the existing REMOTE_ADDR."""
        cf_ip = environ.get("HTTP_CF_CONNECTING_IP")
        if cf_ip:
            return cf_ip.strip()

        xff = environ.get("HTTP_X_FORWARDED_FOR")
        if xff:
            parts = xff.split(",")
            idx = len(parts) - 1 - self._depth
            if idx >= 0:
                return parts[idx].strip()

        return None


def _configure_cache_and_session(app: Flask, settings: Settings) -> None:
    """Set up Flask-Caching and server-side sessions, using Redis when configured.

    Args:
        app: The Flask application instance.
        settings: The application settings.
    """
    if settings.redis.url:
        app.config["CACHE_TYPE"] = "RedisCache"
        app.config["CACHE_REDIS_URL"] = settings.redis.url
        app.config["CACHE_DEFAULT_TIMEOUT"] = settings.redis.default_timeout
        app.config["CACHE_KEY_PREFIX"] = settings.redis.key_prefix

    else:
        app.config["CACHE_TYPE"] = "SimpleCache"
        app.config["CACHE_DEFAULT_TIMEOUT"] = settings.redis.default_timeout
        app.config["CACHE_KEY_PREFIX"] = settings.redis.key_prefix
    cache.init_app(app)

    if settings.redis.url:
        import redis
        from flask_session import Session

        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis.from_url(settings.redis.url)
        Session(app)


def create_app(settings_override: Settings | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        settings_override: Optional settings instance for testing; falls back to the
            lazy singleton when not provided.

    Returns:
        The configured application instance.
    """
    settings = settings_override or get_settings()

    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_PATH),
        static_folder=str(STATIC_PATH),
    )

    # Resolve the real client IP from reverse-proxy headers so that
    # request.remote_addr and gunicorn's %(h)s access log show the true address.
    app.wsgi_app = _RealIPMiddleware(  # ty:ignore[invalid-assignment]
        app.wsgi_app, trusted_proxy_depth=settings.trusted_proxy_depth
    )

    app.secret_key = settings.secret_key
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SETTINGS"] = settings
    CSRFProtect(app)
    _configure_cache_and_session(app, settings)

    register_oauth_providers(app, settings)
    configure_security(app, settings)

    if settings.env == "development":
        from flask_debugtoolbar import DebugToolbarExtension

        app.config["DEBUG"] = True
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
        if settings.debug_toolbar:
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
        base_url=settings.api.base_url,
        api_key=settings.api.api_key,
        timeout=settings.api.timeout,
        max_retries=settings.api.max_retries,
        retry_delay=settings.api.retry_delay,
        auto_retry_rate_limit=settings.api.auto_retry_rate_limit,
        auto_idempotency_keys=settings.api.auto_idempotency_keys,
    )

    def _cleanup() -> None:
        client = app.extensions.get("vclient")
        if client and not client.is_closed:
            client.close()

    atexit.register(_cleanup)

    configure_jinja(app, settings, catalog)
    register_before_request_hooks(app)
    register_error_handlers(app)

    return app


def main() -> None:
    """Entry point for the vweb CLI command."""
    settings = get_settings()
    instantiate_logger()
    app = create_app(settings_override=settings)

    if settings.env == "development":
        # Flask's built-in runner watches loaded Python modules for changes and
        # restarts automatically.
        app.run(host=settings.host, port=settings.port, debug=True, use_reloader=True)
    else:
        import subprocess
        import sys

        from loguru import logger

        logger.debug("Starting gunicorn with {} workers", settings.workers)

        cmd = [
            "gunicorn",
            "--bind",
            f"{settings.host}:{settings.port}",
            "--workers",
            str(settings.workers),
            "--access-logfile",
            settings.access_log,
        ]
        if settings.access_log_ip_header:
            ip_atom = f"%({{{settings.access_log_ip_header}}}i)s"
            cmd += [
                "--access-logformat",
                f'{ip_atom} %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"',
            ]
        cmd.append("vweb:create_app()")

        sys.exit(subprocess.call(cmd))  # noqa: S603
