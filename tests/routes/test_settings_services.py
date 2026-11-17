"""Unit tests for settings.services user helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import Routes, UserFactory

if TYPE_CHECKING:
    from flask import Flask


class TestListPendingAndApproved:
    """list_pending_and_approved partitions users via two service calls."""

    def test_list_pending_and_approved_excludes_self(self, app: Flask, fake_vclient) -> None:
        """Verify the current admin is filtered from both lists."""
        # Given two unapproved users (one is "self") and three approved (one is "self")
        self_id = "self-id"
        pending = [
            UserFactory.build(id=self_id, role="UNAPPROVED"),
            UserFactory.build(id="pending-2", role="UNAPPROVED"),
        ]
        approved = [
            UserFactory.build(id=self_id, role="ADMIN"),
            UserFactory.build(id="user-1", role="PLAYER"),
            UserFactory.build(id="user-2", role="STORYTELLER"),
        ]
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=pending)
        fake_vclient.set_response(Routes.USERS_LIST, items=approved)

        # When partitioning with the self id excluded
        from vweb.routes.admin.services import list_pending_and_approved

        with app.test_request_context("/"):
            seed_session()
            result_pending, result_approved = list_pending_and_approved(self_id)

        # Then "self" is gone from both lists
        assert [u.id for u in result_pending] == ["pending-2"]
        assert [u.id for u in result_approved] == ["user-1", "user-2"]


class TestApprove:
    """approve() wraps users_svc.approve_user and clears the global cache."""

    def test_approve_calls_users_service_and_clears_cache(
        self,
        app: Flask,
        fake_vclient,
        mocker,
    ) -> None:
        """Verify approve() sends the role to the approve endpoint and invalidates cache."""
        # Given the API approves the user
        fake_vclient.set_response(
            Routes.USERS_APPROVE, model=UserFactory.build(id="u1", role="PLAYER")
        )
        clear_cache = mocker.patch(
            "vweb.lib.cache.global_context.clear",
        )

        # When approving
        from vweb.routes.admin.services import approve

        with app.test_request_context():
            seed_session(user_id="admin-id")
            result = approve("u1", "PLAYER")

        # Then the API approves u1 with the PLAYER role
        fake_vclient.assert_called(
            Routes.USERS_APPROVE,
            params={"user_id": "u1"},
            json={"role": "PLAYER"},
            times=1,
        )
        clear_cache.assert_called_once()
        assert result.id == "u1"

    def test_approve_rejects_unapproved_role(self, app: Flask) -> None:
        """Verify approve() refuses to assign UNAPPROVED."""
        from vweb.routes.admin.services import approve

        # When approving with UNAPPROVED, then ValueError is raised
        with app.test_request_context(), pytest.raises(ValueError, match="UNAPPROVED"):
            approve("u1", "UNAPPROVED")


class TestChangeRole:
    """change_role() wraps users_svc.update."""

    def test_change_role_calls_update_and_clears_cache(
        self,
        app: Flask,
        fake_vclient,
        mocker,
    ) -> None:
        """Verify change_role sends only the new role to the user update endpoint."""
        # Given the API returns the updated user
        fake_vclient.set_response(
            Routes.USERS_UPDATE, model=UserFactory.build(id="u1", role="STORYTELLER")
        )
        clear_cache = mocker.patch(
            "vweb.lib.cache.global_context.clear",
        )

        # When changing role
        from vweb.routes.admin.services import change_role

        with app.test_request_context():
            seed_session(user_id="admin-id")
            result = change_role("u1", "STORYTELLER")

        # Then the API updates only u1's role and the cache is cleared
        fake_vclient.assert_called(
            Routes.USERS_UPDATE,
            params={"user_id": "u1"},
            json={"role": "STORYTELLER"},
            times=1,
        )
        clear_cache.assert_called_once()
        assert result.role == "STORYTELLER"

    def test_change_role_rejects_unapproved(self, app: Flask) -> None:
        """Verify UNAPPROVED is rejected as a target role."""
        from vweb.routes.admin.services import change_role

        # When changing role to UNAPPROVED, then ValueError is raised
        with app.test_request_context(), pytest.raises(ValueError, match="UNAPPROVED"):
            change_role("u1", "UNAPPROVED")


class TestDeny:
    """deny() wraps users_svc.deny_user."""

    def test_deny_calls_users_service(self, app: Flask, fake_vclient, mocker) -> None:
        """Verify deny calls the deny endpoint for the user and clears cache."""
        # Given a cache clearer
        clear_cache = mocker.patch(
            "vweb.lib.cache.global_context.clear",
        )

        from vweb.routes.admin.services import deny

        # When denying a user
        with app.test_request_context():
            seed_session(user_id="admin-id")
            deny("u1")

        # Then the API denies u1 and the cache is cleared
        fake_vclient.assert_called(Routes.USERS_DENY, params={"user_id": "u1"}, times=1)
        clear_cache.assert_called_once()


class TestMerge:
    """merge() wraps users_svc.merge."""

    def test_merge_forwards_args_and_clears_cache(
        self,
        app: Flask,
        fake_vclient,
        mocker,
    ) -> None:
        """Verify merge() sends the primary and secondary users to the merge endpoint."""
        # Given the API returns the merged primary user
        fake_vclient.set_response(Routes.USERS_MERGE, model=UserFactory.build(id="primary"))
        clear_cache = mocker.patch(
            "vweb.lib.cache.global_context.clear",
        )

        from vweb.routes.admin.services import merge

        # When calling merge
        with app.test_request_context():
            seed_session(user_id="admin-id")
            result = merge("primary", "pending-1")

        # Then the API merges pending-1 into primary and the cache is cleared
        fake_vclient.assert_called(
            Routes.USERS_MERGE,
            json={"primary_user_id": "primary", "secondary_user_id": "pending-1"},
            times=1,
        )
        clear_cache.assert_called_once()
        assert result.id == "primary"
