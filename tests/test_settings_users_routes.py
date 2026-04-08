"""Tests for the /settings/users page and its action endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import UserFactory

from tests.conftest import get_csrf

if TYPE_CHECKING:
    from flask.testing import FlaskClient

    from vweb.lib.global_context import GlobalContext


@pytest.fixture
def admin_context(mock_global_context: GlobalContext) -> GlobalContext:
    """Promote the test user to ADMIN."""
    mock_global_context.users[0].role = "ADMIN"
    return mock_global_context


@pytest.fixture
def patch_users_service(mocker):
    """Return a callable that patches sync_users_service in services + views."""

    def _patch(svc: MagicMock) -> None:
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=svc,
        )

    return _patch


class TestUsersPageAccessControl:
    """The blueprint admin guard covers /settings/users."""

    def test_non_admin_redirected(
        self,
        client: FlaskClient,
        mock_global_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify a non-admin GET to /settings/users is redirected."""
        # Given a player
        mock_global_context.users[0].role = "PLAYER"
        mocker.patch("vweb.app.load_global_context", return_value=mock_global_context)

        # When loading the page
        response = client.get("/settings/users")

        # Then the player is redirected away
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")


class TestUsersPageGet:
    """GET /settings/users renders the page with pending and approved sections."""

    def test_users_page_renders_pending_and_approved(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        patch_users_service,
    ) -> None:
        """Verify pending and approved users render and the admin's own row is hidden."""
        # Given an admin and a mix of pending + approved users (one is the admin)
        admin_id = admin_context.users[0].id
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)

        svc = MagicMock()
        svc.list_all_unapproved.return_value = [
            UserFactory.build(id="pending-1", name_first="Ada", name_last="Lovelace"),
        ]
        svc.list_all.return_value = [
            UserFactory.build(id=admin_id, name_first="Self", name_last="Admin"),
            UserFactory.build(id="approved-1", name_first="Grace", name_last="Hopper"),
        ]
        patch_users_service(svc)

        # When loading the users page
        response = client.get("/settings/users")
        body = response.get_data(as_text=True)

        # Then the page contains the pending and approved (non-self) users
        assert response.status_code == 200
        assert "Ada" in body
        assert "Grace" in body
        assert "Self Admin" not in body
        assert 'id="pending-user-pending-1"' in body
        assert 'id="user-approved-1"' in body


class TestApproveUserEndpoint:
    """POST /settings/users/<id>/approve grants a role to a pending user."""

    def test_approve_calls_service_and_returns_swap_target(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify approve_user calls the service and returns 200."""
        # Given a pending user
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        approve = mocker.patch(
            "vweb.routes.settings.views.settings_services.approve",
            return_value=UserFactory.build(id="pending-1", role="PLAYER"),
        )

        # When approving
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/pending-1/approve",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then the service was called
        approve.assert_called_once_with("pending-1", "PLAYER", admin_context.users[0].id)
        assert response.status_code == 200

    def test_approve_self_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify the admin cannot approve themselves."""
        # Given the admin's own id
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When approving self
        csrf = get_csrf(client)
        response = client.post(
            f"/settings/users/{self_id}/approve",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned
        assert response.status_code == 403

    def test_approve_unapproved_role_returns_400(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify approving with UNAPPROVED is rejected."""
        # Given an admin session
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)

        # When approving with UNAPPROVED role
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/pending-1/approve",
            data={"role": "UNAPPROVED", "csrf_token": csrf},
        )

        # Then 400 is returned
        assert response.status_code == 400


class TestChangeRoleEndpoint:
    """POST /settings/users/<id>/role changes an approved user's role."""

    def test_change_role_returns_swapped_row(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify a successful role change returns the updated ApprovedUserRow."""
        # Given a mocked change_role returning a STORYTELLER
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        mocker.patch(
            "vweb.routes.settings.views.settings_services.change_role",
            return_value=UserFactory.build(
                id="approved-1",
                name_first="Grace",
                name_last="Hopper",
                role="STORYTELLER",
            ),
        )

        # When posting a role change
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/approved-1/role",
            data={"role": "STORYTELLER", "csrf_token": csrf},
        )

        # Then the swapped row is returned with the new role selected
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="user-approved-1"' in body
        assert 'value="STORYTELLER"' in body
        assert "selected" in body

    def test_change_role_self_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify the admin cannot change their own role."""
        # Given the admin's own id
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When changing own role
        csrf = get_csrf(client)
        response = client.post(
            f"/settings/users/{self_id}/role",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned
        assert response.status_code == 403

    def test_change_role_unapproved_returns_400(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify UNAPPROVED is rejected with 400."""
        # Given an admin session
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)

        # When changing role to UNAPPROVED
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/approved-1/role",
            data={"role": "UNAPPROVED", "csrf_token": csrf},
        )

        # Then 400 is returned
        assert response.status_code == 400


class TestDenyUserEndpoint:
    """POST /settings/users/<id>/deny denies a pending user."""

    def test_deny_calls_service(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify deny endpoint calls deny_user and returns 200."""
        # Given an admin session and mocked deny service
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        deny = mocker.patch("vweb.routes.settings.views.settings_services.deny")

        # When denying a pending user
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/pending-1/deny",
            data={"csrf_token": csrf},
        )

        # Then the service is called and the response is 200
        deny.assert_called_once_with("pending-1", admin_context.users[0].id)
        assert response.status_code == 200

    def test_deny_self_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify the admin cannot deny themselves."""
        # Given the admin's own id
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When denying self
        csrf = get_csrf(client)
        response = client.post(
            f"/settings/users/{self_id}/deny",
            data={"csrf_token": csrf},
        )

        # Then 403 is returned
        assert response.status_code == 403


class TestMergeForm:
    """GET /settings/users/<id>/merge returns the merge modal."""

    def test_merge_form_returns_modal_with_picker(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        patch_users_service,
    ) -> None:
        """Verify the modal shows the pending user and a picker of candidates."""
        # Given a pending user and approved candidates
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        svc = MagicMock()
        svc.list_all_unapproved.return_value = [
            UserFactory.build(id="pending-1", name_first="Ada", name_last="Lovelace"),
        ]
        svc.list_all.return_value = [
            UserFactory.build(id="approved-1", name_first="Grace", name_last="Hopper"),
        ]
        patch_users_service(svc)

        # When requesting the merge form
        response = client.get("/settings/users/pending-1/merge")
        body = response.get_data(as_text=True)

        # Then the modal is rendered with the pending user and candidate picker
        assert response.status_code == 200
        assert "Ada" in body
        assert 'name="target_user_id"' in body
        assert "approved-1" in body


class TestMergePost:
    """POST /settings/users/<id>/merge merges a pending user into a primary."""

    def test_merge_post_calls_service_and_redirects(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify the endpoint calls merge() and returns HX-Redirect."""
        # Given an admin and a mocked merge service
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        merge = mocker.patch("vweb.routes.settings.views.settings_services.merge")

        # When posting with a target user
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/pending-1/merge",
            data={"csrf_token": csrf, "target_user_id": "approved-1"},
        )

        # Then merge is called with (target, pending, admin) and HX-Redirect is returned
        merge.assert_called_once_with(
            "approved-1",
            "pending-1",
            admin_context.users[0].id,
        )
        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/settings/users"

    def test_merge_post_self_as_target_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify an admin cannot merge into their own account."""
        # Given the admin's own id as target
        mocker.patch("vweb.app.load_global_context", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When posting with self as target
        csrf = get_csrf(client)
        response = client.post(
            "/settings/users/pending-1/merge",
            data={"csrf_token": csrf, "target_user_id": self_id},
        )

        # Then a 403 is returned
        assert response.status_code == 403
