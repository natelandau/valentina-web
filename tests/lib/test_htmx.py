"""Tests for HTMX response helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import flash

from vweb.lib.htmx import htmx_flash_only

if TYPE_CHECKING:
    from flask import Flask


def test_htmx_flash_only_returns_flash_and_no_swap(app: Flask) -> None:
    """Verify the response carries only the OOB flash container and tells htmx not to swap."""
    with app.test_request_context():
        # Given a flashed message
        flash("Saved nothing", "error")

        # When building the flash-only response
        response = htmx_flash_only()

    # Then the flash is swapped out of band and the target is left alone
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert 'id="flash-messages"' in body
    assert "Saved nothing" in body
