"""Tests for the /admin audit log page and HTMX table endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import AuditLogFactory, Routes

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

    from vweb.lib.global_context import GlobalContext


@pytest.fixture
def admin_context(mock_global_context: GlobalContext) -> GlobalContext:
    """Promote the test user to ADMIN."""
    mock_global_context.users[0].role = "ADMIN"
    return mock_global_context


@pytest.fixture
def _mock_audit_api(mocker, admin_context: GlobalContext, fake_vclient) -> None:
    """Set up mocks for audit log page rendering."""
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)

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

    def test_audit_log_table_url_exists(self, app: Flask) -> None:
        """Verify the /admin/audit-log endpoint is registered."""
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/admin/audit-log" in rules


class TestAuditLogAccessControl:
    """Only ADMIN users can access the audit log."""

    def test_player_redirected(
        self, client: FlaskClient, mock_global_context: GlobalContext, mocker
    ) -> None:
        """Verify non-admin users are redirected away from /admin."""
        mock_global_context.users[0].role = "PLAYER"
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=mock_global_context)

        response = client.get("/admin")

        assert response.status_code == 302


@pytest.mark.usefixtures("_mock_audit_api")
class TestAuditLogPage:
    """GET /admin renders the full audit log page."""

    def test_renders_audit_log_page(self, client: FlaskClient) -> None:
        """Verify GET /admin returns 200 with audit log content."""
        response = client.get("/admin")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Audit Log" in body
        assert "audit-log-content" in body


@pytest.mark.usefixtures("_mock_audit_api")
class TestAuditLogTable:
    """GET /admin/audit-log returns HTMX table rows."""

    def test_returns_table_rows(self, client: FlaskClient) -> None:
        """Verify GET /admin/audit-log returns table row HTML."""
        response = client.get("/admin/audit-log", headers={"HX-Request": "true"})

        assert response.status_code == 200

    @pytest.fixture
    def mock_empty_page(self, mocker) -> MagicMock:
        """Patch get_audit_log_page to return an empty page."""
        mock_svc_fn = mocker.patch(
            "vweb.routes.admin.views.audit_log_services.get_audit_log_page",
        )
        mock_page = MagicMock()
        mock_page.items = []
        mock_page.total = 0
        mock_page.has_more = False
        mock_svc_fn.return_value = mock_page
        return mock_svc_fn

    def test_passes_filters_as_query_params(
        self, client: FlaskClient, mock_empty_page: MagicMock
    ) -> None:
        """Verify filter query params are forwarded to the service."""
        client.get(
            "/admin/audit-log?entity_type=CHARACTER&operation=UPDATE&acting_user_id=u1",
            headers={"HX-Request": "true"},
        )

        mock_empty_page.assert_called_once_with(
            limit=20,
            offset=0,
            entity_type="CHARACTER",
            operation="UPDATE",
            acting_user_id="u1",
            date_from="",
            date_to="",
        )

    def test_pagination_offset(self, client: FlaskClient, mock_empty_page: MagicMock) -> None:
        """Verify offset query param is forwarded for pagination."""
        client.get(
            "/admin/audit-log?offset=40",
            headers={"HX-Request": "true"},
        )

        mock_empty_page.assert_called_once_with(
            limit=20,
            offset=40,
            entity_type="",
            operation="",
            acting_user_id="",
            date_from="",
            date_to="",
        )
