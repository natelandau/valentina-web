"""Tests for shared test assertion helpers.

The suite uses these helpers everywhere they pass; these tests make sure each one
still fails when it should, so a broken helper cannot hide a broken page.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.helpers import (
    assert_has_element,
    assert_redirects_to,
    assert_shows_error,
    build_global_context,
)
from vweb.api_client.testing import UserFactory


def _response(status_code: int = 200, body: str = "", location: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.get_data.return_value = body
    resp.headers = {"Location": location} if location else {}
    return resp


@pytest.mark.parametrize(
    "check",
    [
        pytest.param(lambda: assert_shows_error(_response(body="<div>OK</div>")), id="error"),
        pytest.param(
            lambda: assert_redirects_to(_response(200, location="/dashboard"), "/dashboard"),
            id="redirect-status",
        ),
        pytest.param(
            lambda: assert_redirects_to(_response(302, location="/other"), "/dashboard"),
            id="redirect-location",
        ),
        pytest.param(
            lambda: assert_has_element(_response(body="<div></div>"), id="my-element"), id="id"
        ),
        pytest.param(
            lambda: assert_has_element(_response(body='<input name="email" />'), name="user"),
            id="name",
        ),
    ],
)
def test_assertion_helpers_fail_on_mismatch(check) -> None:
    """Verify each assertion helper raises when the response does not match."""
    with pytest.raises(AssertionError):
        check()


def test_build_global_context_rejects_role_mismatch() -> None:
    """Verify a custom user whose role disagrees with user_role is refused."""
    with pytest.raises(ValueError, match="conflicts"):
        build_global_context(user_role="PLAYER", user=UserFactory.build(role="STORYTELLER"))
