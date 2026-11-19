"""Tests for the /admin/users page and its action endpoints.

Non-admin access is covered by the admin blueprint table in test_settings_routes.py.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from vweb.api_client.models.users import AppleProfile
from vweb.api_client.testing import Routes, UserFactory

if TYPE_CHECKING:
    from flask.testing import FlaskClient

    from vweb.api_client.models.users import User
    from vweb.lib.cache.global_context import GlobalContext


def _pending_apple_user() -> User:
    """Build a nameless pending user whose only identity is an Apple profile."""
    return UserFactory.build(
        id="pending-apple",
        name_first=None,
        name_last=None,
        username="relay-user",
        apple_profile=AppleProfile(id="apple-1", fullname="Ada Lovelace"),
    )


pytestmark = pytest.mark.usefixtures("admin_context")


class TestUsersPageGet:
    """GET /admin/users renders the pending and approved users."""

    def test_lists_pending_and_approved_users_except_self(
        self, client: FlaskClient, admin_context: GlobalContext, fake_vclient
    ) -> None:
        """Verify pending and approved users render and the admin's own row is hidden."""
        # Given a mix of pending and approved users, one of them the admin
        admin_id = admin_context.users[0].id
        fake_vclient.set_response(
            Routes.USERS_UNAPPROVED_LIST,
            items=[UserFactory.build(id="pending-1", name_first="Ada", name_last="Lovelace")],
        )
        fake_vclient.set_response(
            Routes.USERS_LIST,
            items=[
                UserFactory.build(id=admin_id, name_first="Self", name_last="Admin"),
                UserFactory.build(id="approved-1", name_first="Grace", name_last="Hopper"),
            ],
        )

        # When loading the users page
        response = client.get("/admin/users")
        body = response.get_data(as_text=True)

        # Then the pending and approved (non-self) users are listed
        assert response.status_code == 200
        assert "Ada Lovelace" in body
        assert "Grace Hopper" in body
        assert "Self Admin" not in body
        assert 'id="pending-user-pending-1"' in body
        assert 'id="user-approved-1"' in body

    def test_nameless_apple_user_shows_apple_fullname(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a nameless pending Apple user is listed by their Apple full name."""
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[_pending_apple_user()])
        fake_vclient.set_response(Routes.USERS_LIST, items=[])

        body = client.get("/admin/users").get_data(as_text=True)

        assert "Ada Lovelace" in body


class TestSelfModificationBlocked:
    """An admin can never act on their own account."""

    @pytest.mark.parametrize(
        ("path_template", "data", "route"),
        [
            ("/admin/users/{me}/approve", {"role": "PLAYER"}, Routes.USERS_APPROVE),
            ("/admin/users/{me}/role", {"role": "PLAYER"}, Routes.USERS_UPDATE),
            ("/admin/users/{me}/deny", {}, Routes.USERS_DENY),
            ("/admin/users/{me}/merge", {"target_user_id": "approved-1"}, Routes.USERS_MERGE),
            ("/admin/users/pending-1/merge", {"target_user_id": "{me}"}, Routes.USERS_MERGE),
        ],
        ids=["approve", "change-role", "deny", "merge-self-as-source", "merge-into-self"],
    )
    def test_self_action_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        fake_vclient,
        path_template: str,
        data: dict[str, str],
        route: object,
    ) -> None:
        """Verify acting on the admin's own account returns 403 and nothing reaches the API."""
        self_id = admin_context.users[0].id
        form = {key: value.format(me=self_id) for key, value in data.items()}

        response = client.post(
            path_template.format(me=self_id),
            data={"csrf_token": get_csrf(client), **form},
        )

        assert response.status_code == 403
        fake_vclient.assert_not_called(route)


class TestRoleChanges:
    """Approve and change-role send the chosen role to the API."""

    def test_approve_sends_role(self, client: FlaskClient, fake_vclient) -> None:
        """Verify approve sends the chosen role to the API."""
        fake_vclient.set_response(Routes.USERS_APPROVE, model=UserFactory.build(id="pending-1"))

        response = client.post(
            "/admin/users/pending-1/approve",
            data={"role": "PLAYER", "csrf_token": get_csrf(client)},
        )

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.USERS_APPROVE,
            params={"user_id": "pending-1"},
            json={"role": "PLAYER"},
            times=1,
        )

    def test_change_role_returns_updated_row(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a role change sends only the role and returns the row with the new role selected."""
        fake_vclient.set_response(
            Routes.USERS_UPDATE,
            model=UserFactory.build(id="approved-1", role="STORYTELLER"),
        )

        response = client.post(
            "/admin/users/approved-1/role",
            data={"role": "STORYTELLER", "csrf_token": get_csrf(client)},
        )

        fake_vclient.assert_called(
            Routes.USERS_UPDATE,
            params={"user_id": "approved-1"},
            json={"role": "STORYTELLER"},
            times=1,
        )
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="user-approved-1"' in body
        selected = re.findall(r'<option value="(\w+)"\s+selected', body)
        assert selected == ["STORYTELLER"]

    @pytest.mark.parametrize(
        ("path", "route"),
        [
            ("/admin/users/pending-1/approve", Routes.USERS_APPROVE),
            ("/admin/users/approved-1/role", Routes.USERS_UPDATE),
        ],
        ids=["approve", "change-role"],
    )
    def test_unapproved_role_returns_400(
        self, client: FlaskClient, fake_vclient, path: str, route: object
    ) -> None:
        """Verify a user can never be set back to UNAPPROVED."""
        response = client.post(path, data={"role": "UNAPPROVED", "csrf_token": get_csrf(client)})

        assert response.status_code == 400
        fake_vclient.assert_not_called(route)


def test_deny_sends_request(client: FlaskClient, fake_vclient) -> None:
    """Verify the deny endpoint denies the user through the API."""
    response = client.post("/admin/users/pending-1/deny", data={"csrf_token": get_csrf(client)})

    assert response.status_code == 200
    fake_vclient.assert_called(Routes.USERS_DENY, params={"user_id": "pending-1"}, times=1)


class TestMergeForm:
    """GET /admin/users/<id>/merge returns the merge modal."""

    def test_modal_offers_approved_users_as_targets(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify the modal names the pending user and offers approved users to merge into."""
        # Given a nameless pending apple user and a nameless approved candidate
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[_pending_apple_user()])
        fake_vclient.set_response(
            Routes.USERS_LIST,
            items=[
                UserFactory.build(
                    id="approved-1", name_first=None, name_last=None, username="grace"
                )
            ],
        )

        # When requesting the merge form
        response = client.get("/admin/users/pending-apple/merge")
        body = response.get_data(as_text=True)

        # Then the modal names both users and offers the candidate as a target
        assert response.status_code == 200
        assert "Ada Lovelace" in body
        assert "grace" in body
        assert re.search(r'<option[^>]*value="approved-1"', body)

    def test_unknown_pending_user_returns_404(self, client: FlaskClient, fake_vclient) -> None:
        """Verify requesting the modal for a user who is not pending returns 404."""
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[])
        fake_vclient.set_response(Routes.USERS_LIST, items=[])

        response = client.get("/admin/users/not-pending/merge")

        assert response.status_code == 404


class TestMergePost:
    """POST /admin/users/<id>/merge merges a pending user into a primary."""

    def test_merges_and_redirects_to_users(self, client: FlaskClient, fake_vclient) -> None:
        """Verify the endpoint merges the pending user into the target and HX-redirects."""
        response = client.post(
            "/admin/users/pending-1/merge",
            data={"csrf_token": get_csrf(client), "target_user_id": "approved-1"},
        )

        fake_vclient.assert_called(
            Routes.USERS_MERGE,
            json={"primary_user_id": "approved-1", "secondary_user_id": "pending-1"},
            times=1,
        )
        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/admin/users"

    def test_missing_target_returns_400(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a merge without a target user returns 400 and nothing reaches the API."""
        response = client.post(
            "/admin/users/pending-1/merge",
            data={"csrf_token": get_csrf(client), "target_user_id": ""},
        )

        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.USERS_MERGE)
