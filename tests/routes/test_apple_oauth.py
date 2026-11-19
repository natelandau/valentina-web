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
from vweb.routes.auth.apple_oauth import build_apple_client_secret
from vweb.routes.auth.services import extract_apple_display_name


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

    @pytest.mark.parametrize(
        "reshape",
        [
            lambda pem: pem.replace("\n", "\\n"),
            lambda pem: "".join(line for line in pem.splitlines() if "-----" not in line),
        ],
        ids=["escaped-newlines", "bare-base64-body"],
    )
    def test_accepts_private_key_in_env_friendly_forms(self, reshape) -> None:
        """Verify a key stored on one env line, escaped or without PEM armor, still signs."""
        # Given the key reshaped the way one-line env storage keeps it
        apple = _apple_settings()
        reshaped = apple.model_copy(update={"private_key": reshape(apple.private_key)})

        # When a client secret is minted from the reshaped key
        token = build_apple_client_secret(reshaped)

        # Then it verifies against the original key
        decoded = jwt.decode(token, ECKey.import_key(apple.private_key))
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

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"name": {"firstName": "Ada", "lastName": "Lovelace"}}', "Ada Lovelace"),
            ('{"name": {"firstName": "Ada"}}', "Ada"),
            ('{"name": {"firstName": "Ada", "lastName": 5}}', "Ada"),
        ],
        ids=["full-name", "first-name-only", "non-string-part-dropped"],
    )
    def test_builds_display_name_from_name_parts(self, raw: str, expected: str) -> None:
        """Verify the string name parts Apple sends are joined into a display name."""
        assert extract_apple_display_name(raw) == expected

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
        assert extract_apple_display_name(raw) is None


def test_apple_registered_for_form_post_and_client_secret_post(mocker) -> None:
    """Verify Apple registration uses form_post responses and sends the secret in the body.

    Apple rejects the default client_secret_basic with invalid_client, and returns the
    user's name only through a form_post callback.
    """
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

    # Then every authorize redirect requests form_post and the token exchange posts the secret
    assert fresh.apple.authorize_params == {"response_mode": "form_post"}
    assert fresh.apple.client_kwargs["scope"] == "openid name email"
    assert fresh.apple.client_kwargs["token_endpoint_auth_method"] == "client_secret_post"
