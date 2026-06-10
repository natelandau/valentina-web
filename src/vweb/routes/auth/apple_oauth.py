"""Sign in with Apple client-secret generation.

Apple does not issue a static OAuth client secret like the other providers.
Instead, the server signs a short-lived ES256 JWT with the team's downloaded
``.p8`` key, and that JWT *is* the ``client_secret`` for the token exchange.
It must therefore be minted on demand rather than stored in settings.
"""

from __future__ import annotations

import textwrap
import time
from typing import TYPE_CHECKING

from joserfc import jwt
from joserfc.jwk import ECKey

if TYPE_CHECKING:
    from vweb.config import AppleOAuthSettings

# Apple requires the client-secret JWT's audience to be the Apple ID service.
_APPLE_AUDIENCE = "https://appleid.apple.com"

# Apple caps the secret's lifetime at six months; mint a short-lived one since it
# is generated immediately before each token exchange and never reused.
_CLIENT_SECRET_TTL_SECONDS = 300

# Standard PEM base64 body line width.
_PEM_LINE_WIDTH = 64


def _normalize_private_key(raw: str) -> str:
    r"""Return PEM-armored key material from either PEM or a bare base64 body.

    Accepts the ``.p8`` contents as full PEM (optionally with escaped ``\n``
    line breaks from env storage) or as a single continuous base64 body with the
    armor stripped, the most convenient form to store as a one-line env variable.

    Args:
        raw: The configured private key, in either accepted form.

    Returns:
        The key as a PKCS#8 PEM string the cryptography backend can parse.
    """
    # Anchor on the dashed armor: "-----" cannot occur in a base64 body, whereas
    # the bare word "BEGIN" can, which would misclassify a valid base64 key.
    if "-----BEGIN" in raw:
        # Already PEM; env storage may have escaped the line breaks.
        return raw.replace("\\n", "\n")
    # Bare base64 body: drop any whitespace and rewrap into PKCS#8 PEM armor.
    body = "\n".join(textwrap.wrap("".join(raw.split()), _PEM_LINE_WIDTH))
    return f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\n"


def build_apple_client_secret(apple: AppleOAuthSettings) -> str:
    """Mint a short-lived ES256 client-secret JWT for Apple's token endpoint.

    Apple verifies that the OAuth ``client_secret`` is a JWT signed with the
    team's Sign in with Apple key, so it has to be generated per exchange rather
    than configured as a static string.

    Args:
        apple: The Sign in with Apple credentials (team, key, services ID, key PEM).

    Returns:
        The signed JWT to use as the OAuth ``client_secret``.
    """
    issued_at = int(time.time())
    header = {"alg": "ES256", "kid": apple.key_id}
    payload = {
        "iss": apple.team_id,
        "iat": issued_at,
        "exp": issued_at + _CLIENT_SECRET_TTL_SECONDS,
        "aud": _APPLE_AUDIENCE,
        "sub": apple.services_id,
    }
    private_key = ECKey.import_key(_normalize_private_key(apple.private_key))
    return jwt.encode(header, payload, private_key)
