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

    if s.oauth.apple.is_configured:
        oauth.register(
            name="apple",
            client_id=s.oauth.apple.services_id,
            # Apple has no static secret. The callback mints a fresh short-lived
            # JWT before each token exchange, so leave it empty here — minting at
            # registration would only couple app startup to key validity (a bad
            # key would crash every worker on boot, not just disable Apple).
            client_secret="",
            server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
            # "openid" makes Authlib add a nonce and parse the id_token into
            # token["userinfo"]; "name email" requests the user's profile fields.
            # Apple only accepts the client_secret in the POST body; Authlib's
            # default (client_secret_basic) sends it as a Basic auth header, which
            # Apple rejects at the token exchange with invalid_client.
            client_kwargs={
                "scope": "openid name email",
                "token_endpoint_auth_method": "client_secret_post",
            },
            # Apple returns the result as a form POST whenever name/email is
            # requested. Set it here so every authorize redirect (login and link)
            # gets it, rather than special-casing each call site.
            authorize_params={"response_mode": "form_post"},
        )
