"""Tests for Sign in with Apple client-secret generation and helpers."""

import time

import pytest
from authlib.integrations.flask_client import OAuth
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Flask
from joserfc import jwt
from joserfc.jwk import ECKey

from vweb.config import APISettings, AppleOAuthSettings, OAuthSettings, RedisSettings, Settings
from vweb.lib import oauth_setup
from vweb.lib.apple_oauth import build_apple_client_secret
from vweb.routes.auth.views import _apple_display_name


def _apple_settings(**overrides) -> AppleOAuthSettings:
    """Build AppleOAuthSettings with a throwaway P-256 key standing in for the .p8."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    defaults = {
        "services_id": "org.example.web",
        "team_id": "TEAM123456",
        "key_id": "KEY1234567",
        "private_key": pem,
    }
    defaults.update(overrides)
    return AppleOAuthSettings(**defaults)


class TestBuildAppleClientSecret:
    """Tests for minting Apple's signed client-secret JWT."""

    def test_signs_jwt_with_apple_required_claims(self) -> None:
        """Verify the client secret is an ES256 JWT carrying Apple's required claims."""
        # Given Apple credentials backed by a valid EC private key
        apple = _apple_settings()

        # When a client secret is minted
        before = int(time.time())
        token = build_apple_client_secret(apple)
        after = int(time.time())

        # Then it verifies against the key and carries the expected header and claims
        decoded = jwt.decode(token, ECKey.import_key(apple.private_key))
        assert decoded.header["alg"] == "ES256"
        assert decoded.header["kid"] == "KEY1234567"
        assert decoded.claims["iss"] == "TEAM123456"
        assert decoded.claims["sub"] == "org.example.web"
        assert decoded.claims["aud"] == "https://appleid.apple.com"
        assert before <= decoded.claims["iat"] <= after
        assert decoded.claims["exp"] > decoded.claims["iat"]

    def test_accepts_private_key_with_escaped_newlines(self) -> None:
        r"""Verify a PEM stored with literal \n escapes (env style) still signs."""
        # Given a key whose newlines were escaped, as .env/Railway storage does
        apple = _apple_settings()
        escaped = apple.model_copy(update={"private_key": apple.private_key.replace("\n", "\\n")})

        # When a client secret is minted from the escaped key
        token = build_apple_client_secret(escaped)

        # Then it is a well-formed three-segment JWT
        assert token.count(".") == 2

    def test_accepts_bare_base64_private_key_without_pem_armor(self) -> None:
        """Verify a key stored as a bare base64 body (no PEM armor) still signs."""
        # Given the key reduced to one continuous base64 line, the one-line env form
        apple = _apple_settings()
        bare = "".join(line for line in apple.private_key.splitlines() if "-----" not in line)
        settings = apple.model_copy(update={"private_key": bare})

        # When a client secret is minted from the bare body
        token = build_apple_client_secret(settings)

        # Then it verifies against the original key
        decoded = jwt.decode(token, ECKey.import_key(apple.private_key))
        assert decoded.header["alg"] == "ES256"
        assert decoded.claims["sub"] == "org.example.web"


class TestAppleOAuthSettings:
    """Tests for the AppleOAuthSettings.is_configured gate."""

    def test_is_configured_true_when_all_fields_set(self) -> None:
        """Verify is_configured is True when every credential is present."""
        assert _apple_settings().is_configured is True

    @pytest.mark.parametrize("missing", ["services_id", "team_id", "key_id", "private_key"])
    def test_is_configured_false_when_any_field_missing(self, missing: str) -> None:
        """Verify is_configured is False when any single credential is blank."""
        assert _apple_settings(**{missing: ""}).is_configured is False


class TestAppleDisplayName:
    """Tests for parsing Apple's first-login name payload."""

    def test_returns_full_name_from_user_payload(self) -> None:
        """Verify first and last names are joined into a display name."""
        raw = '{"name": {"firstName": "Ada", "lastName": "Lovelace"}}'
        assert _apple_display_name(raw) == "Ada Lovelace"

    def test_returns_partial_name_when_only_one_present(self) -> None:
        """Verify a single supplied name part is used on its own."""
        assert _apple_display_name('{"name": {"firstName": "Ada"}}') == "Ada"

    def test_ignores_non_string_name_parts(self) -> None:
        """Verify non-string name parts are dropped rather than crashing the parse."""
        assert _apple_display_name('{"name": {"firstName": "Ada", "lastName": 5}}') == "Ada"

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "not-json",
            "{}",
            '{"name": {}}',
            '{"email": "a@b.com"}',
            # Valid JSON that is not the object shape Apple sends — must not raise.
            '"a string"',
            "123",
            "[1, 2]",
            "null",
            '{"name": "not-an-object"}',
            '{"name": {"firstName": 5}}',
        ],
    )
    def test_returns_none_for_missing_or_invalid_payload(self, raw: str | None) -> None:
        """Verify absent, malformed, or wrongly-shaped payloads yield no display name."""
        assert _apple_display_name(raw) is None


class TestAppleProviderRegistration:
    """Tests for how Sign in with Apple is registered with Authlib."""

    def test_apple_registered_with_form_post_response_mode(self, mocker) -> None:
        """Verify Apple registration makes every authorize redirect request form_post."""
        # Given a fresh OAuth registry and settings with only Apple configured
        fresh = OAuth()
        mocker.patch.object(oauth_setup, "oauth", fresh)
        settings = Settings(
            _env_file=None,
            env="development",
            secret_key="test-secret-key",
            redis=RedisSettings(url=""),
            api=APISettings(base_url="http://localhost", api_key="k"),
            oauth=OAuthSettings(apple=_apple_settings()),
        )
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret-key"

        # When the providers are registered
        oauth_setup.register_oauth_providers(app, settings)

        # Then Apple carries form_post (so login and link both use it) and the scopes
        assert fresh.apple.authorize_params == {"response_mode": "form_post"}
        assert fresh.apple.client_kwargs["scope"] == "openid name email"
