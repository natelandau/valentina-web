"""Tests for CSRF protection."""

from __future__ import annotations


def test_csrf_token_in_page(client) -> None:
    """Verify the CSRF token is present in the rendered page body tag."""
    response = client.get("/", follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "X-CSRFToken" in body


def test_csrf_exempt_get(client) -> None:
    """Verify GET requests are not affected by CSRF protection."""
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
