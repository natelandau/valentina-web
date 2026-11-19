"""Tests for OAuth provider registration."""

from __future__ import annotations

import pytest
from authlib.integrations.flask_client import OAuth
from flask import Flask

from vweb.config import APISettings, OAuthProviderSettings, OAuthSettings, RedisSettings, Settings
from vweb.lib import oauth_setup

_PROVIDERS = ("discord", "github", "google")


@pytest.mark.parametrize("configured", _PROVIDERS)
def test_only_configured_providers_register(mocker, configured: str) -> None:
    """Verify a provider is offered only when its client id is set."""
    fresh = OAuth()
    mocker.patch.object(oauth_setup, "oauth", fresh)
    settings = Settings(
        _env_file=None,
        env="development",
        secret_key="test-secret-key",
        redis=RedisSettings(url=""),
        api=APISettings(base_url="http://localhost", api_key="k"),
        oauth=OAuthSettings.model_validate(
            {configured: OAuthProviderSettings(client_id="id", client_secret="secret")}
        ),
    )
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key"

    oauth_setup.register_oauth_providers(app, settings)

    for provider in (*_PROVIDERS, "apple"):
        assert (fresh.create_client(provider) is not None) is (provider == configured)
