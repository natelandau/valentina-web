"""Tests for the /admin audit log page."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import AuditLogFactory, Routes

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

    from vweb.lib.cache.global_context import GlobalContext


@pytest.fixture
def admin_context(mock_global_context: GlobalContext) -> GlobalContext:
    """Promote the test user to ADMIN."""
    mock_global_context.users[0].role = "ADMIN"
    return mock_global_context


@pytest.fixture
def _mock_audit_api(mocker, admin_context: GlobalContext, fake_vclient) -> None:
    """Set up mocks for audit log page rendering."""
    mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

    fake_vclient.set_response(
        Routes.COMPANIES_AUDIT_LOGS_LIST,
        items=AuditLogFactory.batch(3),
    )

    users_svc = MagicMock()
    users_svc.list_all_unapproved.return_value = []
    mocker.patch(
        "vweb.routes.admin.services.sync_users_service",
        return_value=users_svc,
    )


class TestAuditLogRouteRegistered:
    """Smoke test: the /admin URL resolves to a registered view."""

    def test_admin_url_exists(self, app: Flask) -> None:
        """Verify the /admin endpoint is registered."""
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/admin" in rules

    def test_audit_log_table_url_removed(self, app: Flask) -> None:
        """Verify the legacy /admin/audit-log endpoint is no longer registered."""
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/admin/audit-log" not in rules


class TestAuditLogAccessControl:
    """Only ADMIN users can access the audit log."""

    def test_player_redirected(
        self, client: FlaskClient, mock_global_context: GlobalContext, mocker
    ) -> None:
        """Verify non-admin users are redirected away from /admin."""
        mock_global_context.users[0].role = "PLAYER"
        mocker.patch("vweb.lib.cache.global_context.load", return_value=mock_global_context)

        response = client.get("/admin")

        assert response.status_code == 302


@pytest.mark.usefixtures("_mock_audit_api")
class TestAuditLogPage:
    """GET /admin renders the full audit log page."""

    def test_renders_audit_log_page(self, client: FlaskClient) -> None:
        """Verify GET /admin embeds the shared audit log card with filters enabled."""
        # When loading the admin audit log page
        response = client.get("/admin")

        # Then it renders the shared card wrapper pointed at the fragment endpoint
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Audit Log" in body
        assert "/cards/audit-log" in body
        assert "show_filters=true" in body
        assert "page_size=25" in body
