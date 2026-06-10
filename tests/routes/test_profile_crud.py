"""Tests for profile quickrolls CRUD table routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.conftest import get_csrf


@pytest.fixture
def mock_quickroll_handler(mocker):
    """Mock the CRUD handler for quickrolls."""
    from vweb.routes.profile.handlers import QuickrollDisplay

    items = [
        QuickrollDisplay(
            id="qr-1",
            name="Attack",
            description="Basic attack",
            trait_one_name="Strength",
            trait_two_name="Brawl",
        ),
    ]

    handler = MagicMock()
    handler.list_items.return_value = items
    handler.get_item.return_value = MagicMock(
        id="qr-1", name="Attack", description="Basic attack", trait_ids=["t1", "t2"]
    )
    handler.create_item.return_value = None
    handler.update_item.return_value = None
    handler.delete_item.return_value = None
    handler.validate.return_value = []

    mocker.patch(
        "vweb.routes.profile.views_quickrolls.QuickrollsTableView._build_handler",
        return_value=handler,
    )
    return handler


class TestQuickrollsCrud:
    """Tests for quickrolls CRUD operations."""

    def test_get_table_returns_200(self, client, mock_quickroll_handler) -> None:
        """Verify GET returns the quickrolls table."""
        response = client.get(
            "/profile/test-user-id/quickrolls",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Attack" in response.data

    def test_create_returns_refetch(self, client, mock_quickroll_handler) -> None:
        """Verify POST creates item and returns refetch snippet."""
        response = client.post(
            "/profile/test-user-id/quickrolls",
            data={"name": "New Roll", "trait_one_id": "t1"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_quickroll_handler.create_item.assert_called_once()

    def test_delete_returns_refetch(self, client, mock_quickroll_handler) -> None:
        """Verify DELETE removes item and returns refetch snippet."""
        response = client.delete(
            "/profile/test-user-id/quickrolls/qr-1",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )
        assert response.status_code == 200
        mock_quickroll_handler.delete_item.assert_called_once()

    def test_non_owner_post_returns_403(self, client, mock_quickroll_handler) -> None:
        """Verify a non-owner cannot create a quickroll on someone else's profile."""
        # Given a request targeting a different user's quickroll table
        # When POSTing to create
        response = client.post(
            "/profile/other-user-id/quickrolls",
            data={"name": "Sneaky", "trait_one_id": "t1"},
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then the server rejects with 403 and the handler is never called
        assert response.status_code == 403
        mock_quickroll_handler.create_item.assert_not_called()

    def test_non_owner_delete_returns_403(self, client, mock_quickroll_handler) -> None:
        """Verify a non-owner cannot delete a quickroll from someone else's profile."""
        # Given a DELETE targeting a different user's quickroll
        # When issuing the delete
        response = client.delete(
            "/profile/other-user-id/quickrolls/qr-1",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then the server rejects and the handler is never called
        assert response.status_code == 403
        mock_quickroll_handler.delete_item.assert_not_called()

    def test_non_owner_form_get_returns_403(self, client, mock_quickroll_handler) -> None:
        """Verify a non-owner cannot open the add/edit form on someone else's profile."""
        # Given a GET on the add form for another user
        response = client.get(
            "/profile/other-user-id/quickrolls/form",
            headers={"HX-Request": "true"},
        )

        # Then the form is blocked
        assert response.status_code == 403
