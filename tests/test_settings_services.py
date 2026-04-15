"""Unit tests for settings.services user helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import UserFactory

if TYPE_CHECKING:
    from flask import Flask


class TestListPendingAndApproved:
    """list_pending_and_approved partitions users via two service calls."""

    def test_list_pending_and_approved_excludes_self(
        self,
        app: Flask,
        mocker,
    ) -> None:
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
        svc = MagicMock()
        svc.list_all_unapproved.return_value = pending
        svc.list_all.return_value = approved
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )

        # When partitioning with the self id excluded
        from vweb.routes.admin.services import list_pending_and_approved

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            result_pending, result_approved = list_pending_and_approved(self_id)

        # Then "self" is gone from both lists
        assert [u.id for u in result_pending] == ["pending-2"]
        assert [u.id for u in result_approved] == ["user-1", "user-2"]


class TestPendingUserCount:
    """pending_user_count returns the length of list_all_unapproved()."""

    def test_pending_user_count_returns_unapproved_total(
        self,
        app: Flask,
        mocker,
    ) -> None:
        """Verify the count matches list_all_unapproved length."""
        # Given three unapproved users
        svc = MagicMock()
        svc.list_all_unapproved.return_value = UserFactory.batch(3)
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )

        # When asking for the pending count
        from vweb.routes.admin.services import pending_user_count

        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            count = pending_user_count("admin-id")

        # Then the count is 3
        assert count == 3


class TestApprove:
    """approve() wraps users_svc.approve_user and clears the global cache."""

    def test_approve_calls_users_service_and_clears_cache(
        self,
        app: Flask,
        mocker,
    ) -> None:
        """Verify approve() forwards args and invalidates cache."""
        # Given a mocked users service
        svc = MagicMock()
        svc.approve_user.return_value = UserFactory.build(id="u1", role="PLAYER")
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )
        clear_cache = mocker.patch(
            "vweb.routes.admin.services.clear_global_context_cache",
        )

        # When approving
        from vweb.routes.admin.services import approve

        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "admin-id"
            result = approve("u1", "PLAYER", "admin-id")

        # Then users_svc.approve_user is called with the right args
        svc.approve_user.assert_called_once_with("u1", "PLAYER", "admin-id")
        clear_cache.assert_called_once()
        assert result.id == "u1"

    def test_approve_rejects_unapproved_role(self, app: Flask) -> None:
        """Verify approve() refuses to assign UNAPPROVED."""
        from vweb.routes.admin.services import approve

        # When approving with UNAPPROVED, then ValueError is raised
        with app.test_request_context(), pytest.raises(ValueError, match="UNAPPROVED"):
            approve("u1", "UNAPPROVED", "admin-id")


class TestChangeRole:
    """change_role() wraps users_svc.update."""

    def test_change_role_calls_update_and_clears_cache(
        self,
        app: Flask,
        mocker,
    ) -> None:
        """Verify change_role forwards args correctly."""
        # Given a mocked users service
        svc = MagicMock()
        svc.update.return_value = UserFactory.build(id="u1", role="STORYTELLER")
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )
        clear_cache = mocker.patch(
            "vweb.routes.admin.services.clear_global_context_cache",
        )

        # When changing role
        from vweb.routes.admin.services import change_role

        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "admin-id"
            result = change_role("u1", "STORYTELLER", "admin-id")

        # Then users_svc.update is called with keyword args and cache is cleared
        svc.update.assert_called_once_with("u1", role="STORYTELLER")
        clear_cache.assert_called_once()
        assert result.role == "STORYTELLER"

    def test_change_role_rejects_unapproved(self, app: Flask) -> None:
        """Verify UNAPPROVED is rejected as a target role."""
        from vweb.routes.admin.services import change_role

        # When changing role to UNAPPROVED, then ValueError is raised
        with app.test_request_context(), pytest.raises(ValueError, match="UNAPPROVED"):
            change_role("u1", "UNAPPROVED", "admin-id")


class TestDeny:
    """deny() wraps users_svc.deny_user."""

    def test_deny_calls_users_service(self, app: Flask, mocker) -> None:
        """Verify deny forwards args and clears cache."""
        # Given a mocked users service and cache clearer
        svc = MagicMock()
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )
        clear_cache = mocker.patch(
            "vweb.routes.admin.services.clear_global_context_cache",
        )

        from vweb.routes.admin.services import deny

        # When denying a user
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "admin-id"
            deny("u1", "admin-id")

        # Then deny_user is called and cache is cleared
        svc.deny_user.assert_called_once_with("u1")
        clear_cache.assert_called_once()


class TestMerge:
    """merge() wraps users_svc.merge."""

    def test_merge_forwards_args_and_clears_cache(
        self,
        app: Flask,
        mocker,
    ) -> None:
        """Verify merge() calls users_svc.merge with primary, secondary, requesting."""
        # Given a mocked users service
        svc = MagicMock()
        svc.merge.return_value = UserFactory.build(id="primary")
        mocker.patch(
            "vweb.routes.admin.services.sync_users_service",
            return_value=svc,
        )
        clear_cache = mocker.patch(
            "vweb.routes.admin.services.clear_global_context_cache",
        )

        from vweb.routes.admin.services import merge

        # When calling merge
        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "admin-id"
            result = merge("primary", "pending-1", "admin-id")

        # Then the service is called and cache cleared
        svc.merge.assert_called_once_with(
            primary_user_id="primary",
            secondary_user_id="pending-1",
        )
        clear_cache.assert_called_once()
        assert result.id == "primary"
