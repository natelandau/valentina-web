"""Unit tests for the admin user-management service helpers.

What each helper sends to the API, and the UNAPPROVED role rejection, are covered by the
route tests in test_settings_users_routes.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import Routes, UserFactory
from vweb.routes.admin import services as admin_services

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def test_list_pending_and_approved_excludes_self(app: Flask, fake_vclient) -> None:
    """Verify the requesting admin is filtered from both lists."""
    # Given two unapproved users (one is "self") and three approved (one is "self")
    self_id = "self-id"
    fake_vclient.set_response(
        Routes.USERS_UNAPPROVED_LIST,
        items=[
            UserFactory.build(id=self_id, role="UNAPPROVED"),
            UserFactory.build(id="pending-2", role="UNAPPROVED"),
        ],
    )
    fake_vclient.set_response(
        Routes.USERS_LIST,
        items=[
            UserFactory.build(id=self_id, role="ADMIN"),
            UserFactory.build(id="user-1", role="PLAYER"),
            UserFactory.build(id="user-2", role="STORYTELLER"),
        ],
    )

    # When partitioning with the self id excluded
    with app.test_request_context("/"):
        seed_session()
        result_pending, result_approved = admin_services.list_pending_and_approved(self_id)

    # Then "self" is gone from both lists
    assert [u.id for u in result_pending] == ["pending-2"]
    assert [u.id for u in result_approved] == ["user-1", "user-2"]


@pytest.mark.parametrize(
    ("route", "action"),
    [
        (Routes.USERS_APPROVE, lambda: admin_services.approve("u1", "PLAYER")),
        (Routes.USERS_UPDATE, lambda: admin_services.change_role("u1", "STORYTELLER")),
        (Routes.USERS_DENY, lambda: admin_services.deny("u1")),
        (Routes.USERS_MERGE, lambda: admin_services.merge("primary", "u1")),
    ],
    ids=["approve", "change_role", "deny", "merge"],
)
def test_user_mutations_clear_global_context(
    app: Flask, fake_vclient, mocker, route: object, action: Callable[[], object]
) -> None:
    """Verify every user mutation invalidates the cached company users after the API write."""
    # Given the API accepts the write
    fake_vclient.set_response(route, model=UserFactory.build(id="u1"))
    clear_cache = mocker.patch("vweb.lib.cache.global_context.clear")

    # When performing the mutation
    with app.test_request_context():
        seed_session(user_id="admin-id")
        action()

    # Then the write reached the API and the cached context was cleared
    fake_vclient.assert_called(route, times=1)
    clear_cache.assert_called_once()
