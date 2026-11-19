"""Tests for CSRF protection."""

from __future__ import annotations

from tests.conftest import get_csrf


def test_csrf_token_in_page(client) -> None:
    """Verify pages hand HTMX a CSRF token to send with its requests."""
    assert get_csrf(client)
