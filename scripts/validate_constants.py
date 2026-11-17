"""Validate the API client constants against the live Valentina API.

Usage:
    uv run duty validate_constants company_id=<id>

Configuration comes from web's Settings: VWEB_API__BASE_URL and
VWEB_API__API_KEY, or the .env.secret file. The --api-url and --api-key
flags override them when the script runs directly.

Exit codes: 0 all constants match, 1 mismatch or unmapped API option,
2 configuration or API error.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from vweb.api_client import VClient
from vweb.api_client.exceptions import APIError
from vweb.api_client.validate_constants import print_report, validate
from vweb.config import SETTINGS_SOURCES
from vweb.lib.log_config import LOG_FORMAT


class _ApiConnection(BaseModel):
    """Hold the API URL and key, each optional so a CLI flag can supply the other."""

    base_url: str | None = None
    api_key: str | None = None


class _ApiOnlySettings(BaseSettings):
    """Load only the API block, using the same sources as `vweb.config.Settings`.

    Reading the full `Settings` would make unrelated production-only rules
    (secret key, Redis URL) block a constants check.
    """

    model_config = SettingsConfigDict(**SETTINGS_SOURCES, extra="ignore")

    api: _ApiConnection = Field(default_factory=_ApiConnection)


def main(api_url: str, api_key: str, company_id: str) -> int:
    """Run validation and return exit code.

    Args:
        api_url: Base URL for the Valentina API.
        api_key: API key for authentication.
        company_id: Company ID to use for the options endpoint.

    Returns:
        0 if all constants match, 1 if mismatches or unmapped options are found.
    """
    logger.enable("vweb.api_client")

    with VClient(api_key=api_key, base_url=api_url, set_as_default=False) as client:
        api_options = client.options(company_id=company_id).get_options()

    result = validate(api_options)
    print_report(result)

    return 0 if result.is_valid else 1


def cli() -> int:
    """Parse CLI arguments and run validation.

    Returns:
        Exit code: 0 if all constants match, 1 if a mismatch or unmapped option
        is found, 2 if a configuration or API error occurs.
    """
    parser = argparse.ArgumentParser(
        description="Validate the API client constants against the live API.",
    )
    parser.add_argument("--api-url", help="Base URL for the API (default: VWEB_API__BASE_URL)")
    parser.add_argument("--api-key", help="API key (default: VWEB_API__API_KEY)")
    parser.add_argument("--company-id", help="Company ID whose options are fetched")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="DEBUG", colorize=True, format=LOG_FORMAT)

    if not args.company_id:
        print("Error: --company-id is required.", file=sys.stderr)
        return 2

    api_url: str | None = args.api_url
    api_key: str | None = args.api_key
    if not (api_url and api_key):
        try:
            api_settings = _ApiOnlySettings().api
        except ValidationError as error:
            # Report field paths only; error text would include the input values, which hold the key
            fields = ", ".join(sorted({".".join(map(str, e["loc"])) for e in error.errors()}))
            print(f"Error: invalid API settings, check: {fields}", file=sys.stderr)
            return 2
        api_url = api_url or api_settings.base_url
        api_key = api_key or api_settings.api_key

    if not api_url or not api_key:
        print(
            "Error: the API URL and key are required (VWEB_API__BASE_URL, "
            "VWEB_API__API_KEY, or --api-url and --api-key).",
            file=sys.stderr,
        )
        return 2

    try:
        return main(api_url, api_key, args.company_id)
    except APIError as error:
        print(f"Error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(cli())
