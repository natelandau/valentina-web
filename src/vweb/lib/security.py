"""Content Security Policy and Talisman configuration.

When adding new CDN sources, update the CSP dict here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_talisman import Talisman

if TYPE_CHECKING:
    from flask import Flask

    from vweb.config import Settings


def configure_security(app: Flask, s: Settings) -> None:
    """Apply Flask-Talisman with the app's content security policy.

    Args:
        app: The Flask application instance.
        s: The application settings.
    """
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
