"""Tests for the /admin/users page and its action endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from vweb.api_client.models.users import AppleProfile, DiscordProfile
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


@pytest.fixture
def admin_context(mock_global_context: GlobalContext) -> GlobalContext:
    """Promote the test user to ADMIN."""
    mock_global_context.users[0].role = "ADMIN"
    return mock_global_context


class TestUsersPageAccessControl:
    """The blueprint admin guard covers /admin/users."""

    def test_non_admin_redirected(
        self,
        client: FlaskClient,
        mock_global_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify a non-admin GET to /admin/users is redirected."""
        # Given a player
        mock_global_context.users[0].role = "PLAYER"
        mocker.patch("vweb.lib.cache.global_context.load", return_value=mock_global_context)

        # When loading the page
        response = client.get("/admin/users")

        # Then the player is redirected away
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")


class TestUsersPageGet:
    """GET /admin/users renders the page with pending and approved sections."""

    def test_users_page_renders_pending_and_approved(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify pending and approved users render and the admin's own row is hidden."""
        # Given an admin and a mix of pending + approved users (one is the admin)
        admin_id = admin_context.users[0].id
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        fake_vclient.set_response(
            Routes.USERS_UNAPPROVED_LIST,
            items=[
                UserFactory.build(id="pending-1", name_first="Ada", name_last="Lovelace"),
            ],
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

        # Then the page contains the pending and approved (non-self) users
        assert response.status_code == 200
        assert "Ada" in body
        assert "Grace" in body
        assert "Self Admin" not in body
        assert 'id="pending-user-pending-1"' in body
        assert 'id="user-approved-1"' in body

    def test_users_page_uses_apple_fullname_and_provider_badges(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify a nameless apple user shows their apple fullname and provider badge."""
        # Given a pending apple user with no top-level names and a discord user
        admin_id = admin_context.users[0].id
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[_pending_apple_user()])
        fake_vclient.set_response(
            Routes.USERS_LIST,
            items=[
                UserFactory.build(id=admin_id),
                UserFactory.build(
                    id="approved-1",
                    name_first="Grace",
                    name_last="Hopper",
                    discord_profile=DiscordProfile(id="discord-1", username="grace"),
                ),
            ],
        )

        # When loading the users page
        response = client.get("/admin/users")
        body = response.get_data(as_text=True)

        # Then the apple fullname renders instead of 'None' and badges show providers
        assert response.status_code == 200
        assert "Ada Lovelace" in body
        assert "Deny Ada Lovelace? This cannot be undone." in body
        assert 'data-tip="Apple"' in body
        assert 'data-tip="Discord"' in body


class TestApproveUserEndpoint:
    """POST /admin/users/<id>/approve grants a role to a pending user."""

    def test_approve_calls_service_and_returns_swap_target(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify approve_user sends the chosen role to the API and returns 200."""
        # Given a pending user the API will approve
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(
            Routes.USERS_APPROVE, model=UserFactory.build(id="pending-1", role="PLAYER")
        )

        # When approving
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/pending-1/approve",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then the API approves pending-1 as a PLAYER
        fake_vclient.assert_called(
            Routes.USERS_APPROVE,
            params={"user_id": "pending-1"},
            json={"role": "PLAYER"},
            times=1,
        )
        assert response.status_code == 200

    def test_approve_self_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the admin cannot approve themselves."""
        # Given the admin's own id
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When approving self
        csrf = get_csrf(client)
        response = client.post(
            f"/admin/users/{self_id}/approve",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.USERS_APPROVE)

    def test_approve_unapproved_role_returns_400(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify approving with UNAPPROVED is rejected."""
        # Given an admin session
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        # When approving with UNAPPROVED role
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/pending-1/approve",
            data={"role": "UNAPPROVED", "csrf_token": csrf},
        )

        # Then 400 is returned and nothing reaches the API
        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.USERS_APPROVE)


class TestChangeRoleEndpoint:
    """POST /admin/users/<id>/role changes an approved user's role."""

    def test_change_role_returns_swapped_row(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify a successful role change sends the role and returns the updated row."""
        # Given the API returns the user as a STORYTELLER
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(
            Routes.USERS_UPDATE,
            model=UserFactory.build(
                id="approved-1",
                name_first="Grace",
                name_last="Hopper",
                role="STORYTELLER",
            ),
        )

        # When posting a role change
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/approved-1/role",
            data={"role": "STORYTELLER", "csrf_token": csrf},
        )

        # Then only the role is sent and the swapped row shows it selected
        fake_vclient.assert_called(
            Routes.USERS_UPDATE,
            params={"user_id": "approved-1"},
            json={"role": "STORYTELLER"},
            times=1,
        )
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
        fake_vclient,
    ) -> None:
        """Verify the admin cannot change their own role."""
        # Given the admin's own id
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When changing own role
        csrf = get_csrf(client)
        response = client.post(
            f"/admin/users/{self_id}/role",
            data={"role": "PLAYER", "csrf_token": csrf},
        )

        # Then 403 is returned and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.USERS_UPDATE)

    def test_change_role_unapproved_returns_400(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify UNAPPROVED is rejected with 400."""
        # Given an admin session
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        # When changing role to UNAPPROVED
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/approved-1/role",
            data={"role": "UNAPPROVED", "csrf_token": csrf},
        )

        # Then 400 is returned and nothing reaches the API
        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.USERS_UPDATE)


class TestDenyUserEndpoint:
    """POST /admin/users/<id>/deny denies a pending user."""

    def test_deny_calls_service(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the deny endpoint denies the user through the API and returns 200."""
        # Given an admin session
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        # When denying a pending user
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/pending-1/deny",
            data={"csrf_token": csrf},
        )

        # Then the API denies pending-1 and the response is 200
        fake_vclient.assert_called(Routes.USERS_DENY, params={"user_id": "pending-1"}, times=1)
        assert response.status_code == 200

    def test_deny_self_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the admin cannot deny themselves."""
        # Given the admin's own id
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When denying self
        csrf = get_csrf(client)
        response = client.post(
            f"/admin/users/{self_id}/deny",
            data={"csrf_token": csrf},
        )

        # Then 403 is returned and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.USERS_DENY)


class TestMergeForm:
    """GET /admin/users/<id>/merge returns the merge modal."""

    def test_merge_form_returns_modal_with_picker(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the modal shows the pending user and a picker of candidates."""
        # Given a pending user and approved candidates
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(
            Routes.USERS_UNAPPROVED_LIST,
            items=[
                UserFactory.build(id="pending-1", name_first="Ada", name_last="Lovelace"),
            ],
        )
        fake_vclient.set_response(
            Routes.USERS_LIST,
            items=[
                UserFactory.build(id="approved-1", name_first="Grace", name_last="Hopper"),
            ],
        )

        # When requesting the merge form
        response = client.get("/admin/users/pending-1/merge")
        body = response.get_data(as_text=True)

        # Then the modal is rendered with the pending user and candidate picker
        assert response.status_code == 200
        assert "Ada" in body
        assert 'name="target_user_id"' in body
        assert "approved-1" in body

    def test_merge_form_handles_missing_names_and_shows_providers(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the modal never renders 'None' for nameless users and shows provider badges."""
        # Given a nameless pending apple user and a nameless approved candidate
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[_pending_apple_user()])
        fake_vclient.set_response(
            Routes.USERS_LIST,
            items=[
                UserFactory.build(
                    id="approved-1",
                    name_first=None,
                    name_last=None,
                    username="grace",
                ),
            ],
        )

        # When requesting the merge form
        response = client.get("/admin/users/pending-apple/merge")
        body = response.get_data(as_text=True)

        # Then names fall back gracefully and the pending user's provider is visible
        assert response.status_code == 200
        assert "Merge Ada Lovelace into existing user" in body
        assert "grace —" in body
        assert 'data-tip="Apple"' in body


class TestMergePost:
    """POST /admin/users/<id>/merge merges a pending user into a primary."""

    def test_merge_post_calls_service_and_redirects(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify the endpoint merges the pending user into the target and returns HX-Redirect."""
        # Given an admin session
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)

        # When posting with a target user
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/pending-1/merge",
            data={"csrf_token": csrf, "target_user_id": "approved-1"},
        )

        # Then the API merges pending-1 into approved-1 and HX-Redirect is returned
        fake_vclient.assert_called(
            Routes.USERS_MERGE,
            json={"primary_user_id": "approved-1", "secondary_user_id": "pending-1"},
            times=1,
        )
        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/admin/users"

    def test_merge_post_self_as_target_returns_403(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,
        fake_vclient,
    ) -> None:
        """Verify an admin cannot merge into their own account."""
        # Given the admin's own id as target
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        self_id = admin_context.users[0].id

        # When posting with self as target
        csrf = get_csrf(client)
        response = client.post(
            "/admin/users/pending-1/merge",
            data={"csrf_token": csrf, "target_user_id": self_id},
        )

        # Then a 403 is returned and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.USERS_MERGE)
