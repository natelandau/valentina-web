"""OAuth provider registration for the vweb application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vweb.extensions import oauth

if TYPE_CHECKING:
    from flask import Flask

    from vweb.config import Settings


def register_oauth_providers(app: Flask, s: Settings) -> None:
    """Initialize Authlib and register each configured OAuth provider.

    Args:
        app: The Flask application instance.
        s: The application settings.
    """
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
