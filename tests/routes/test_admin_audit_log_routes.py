"""Tests for the /admin audit log page.

Non-admin access is covered by the admin blueprint table in test_settings_routes.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from flask.testing import FlaskClient


pytestmark = pytest.mark.usefixtures("admin_context")


def test_page_lazy_loads_filterable_audit_log_card(client: FlaskClient) -> None:
    """Verify the page wires the shared audit log card with filters and a full page size."""
    # When loading the admin audit log page
    response = client.get("/admin")

    # Then the card loads from the fragment endpoint with filters enabled
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/cards/audit-log" in body
    assert "show_filters=true" in body
    assert "page_size=25" in body


def test_date_picker_script_is_not_escaped(client: FlaskClient) -> None:
    """Verify the date picker's script tag renders as HTML so the filters' calendar loads."""
    body = client.get("/admin").get_data(as_text=True)

    assert '<script type="module" src="https://cdn.jsdelivr.net/npm/cally' in body
