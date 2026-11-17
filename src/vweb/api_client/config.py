"""Configuration for the API client."""

from dataclasses import dataclass

from vweb.api_client.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_RETRY_DELAY,
    DEFAULT_RETRY_BUDGET,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
)


@dataclass
class _APIConfig:
    """Internal configuration settings for the API client.

    Attributes:
        base_url: Base URL for the API.
        api_key: API key for authentication.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts for failed requests.
        retry_delay: Base delay between retries in seconds.
        max_retry_delay: Longest single wait between retries in seconds.
        retry_budget: Total seconds one call may spend across all attempts and waits.
        auto_retry_rate_limit: Automatically retry requests that hit rate limits (429).
        auto_idempotency_keys: Automatically generate idempotency keys for POST/PUT/PATCH.
        default_company_id: Default company ID to use when not explicitly provided.
    """

    base_url: str
    api_key: str
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY
    retry_budget: float = DEFAULT_RETRY_BUDGET
    auto_retry_rate_limit: bool = True
    auto_idempotency_keys: bool = False
    default_company_id: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize configuration."""
        # Remove trailing slash from base_url
        self.base_url = self.base_url.rstrip("/")
