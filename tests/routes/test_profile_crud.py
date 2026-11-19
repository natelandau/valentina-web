"""Tests for the profile quickrolls CRUD table routes.

What the handler sends for each form is covered in test_quickroll_handler.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from vweb.api_client.testing import QuickrollFactory, Routes, TraitFactory

if TYPE_CHECKING:
    from flask.testing import FlaskClient

OWN_TABLE = "/profile/test-user-id/quickrolls"
OTHER_TABLE = "/profile/other-user-id/quickrolls"


@pytest.fixture(autouse=True)
def _traits(mocker) -> None:
    """Serve the blueprint traits quickrolls reference."""
    mocker.patch(
        "vweb.lib.cache.blueprint.traits",
        return_value={"t1": TraitFactory.build(id="t1", name="Strength")},
    )


def _hx_headers(client: FlaskClient) -> dict[str, str]:
    """Build the headers HTMX sends for a mutation."""
    return {"HX-Request": "true", "X-CSRFToken": get_csrf(client)}


@pytest.mark.parametrize("table", [OWN_TABLE, OTHER_TABLE], ids=["own", "other-player"])
def test_anyone_can_list_quickrolls(client: FlaskClient, fake_vclient, table: str) -> None:
    """Verify a profile's quickrolls are readable by any member, with trait names resolved."""
    # Given a user with one quickroll
    fake_vclient.set_response(
        Routes.USERS_QUICKROLLS_LIST,
        items=[QuickrollFactory.build(id="qr-1", name="Attack", trait_ids=["t1"])],
    )

    # When listing the table
    response = client.get(table, headers={"HX-Request": "true"})

    # Then the profile owner's quickrolls are shown
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Attack" in body
    assert "Strength" in body
    owner_id = table.split("/")[2]
    fake_vclient.assert_called(Routes.USERS_QUICKROLLS_LIST, params={"user_id": owner_id})


def test_owner_can_create_quickroll(client: FlaskClient, fake_vclient) -> None:
    """Verify the owner's new quickroll is sent to the API."""
    response = client.post(
        OWN_TABLE, data={"name": "New Roll", "trait_one_id": "t1"}, headers=_hx_headers(client)
    )

    assert response.status_code == 200
    fake_vclient.assert_called(
        Routes.USERS_QUICKROLLS_CREATE,
        params={"user_id": "test-user-id"},
        json_subset={"name": "New Roll", "trait_ids": ["t1"]},
        times=1,
    )


def test_owner_can_delete_quickroll(client: FlaskClient, fake_vclient) -> None:
    """Verify the owner's delete reaches the API."""
    response = client.delete(f"{OWN_TABLE}/qr-1", headers=_hx_headers(client))

    assert response.status_code == 200
    fake_vclient.assert_called(
        Routes.USERS_QUICKROLLS_DELETE,
        params={"user_id": "test-user-id", "quickroll_id": "qr-1"},
        times=1,
    )


def test_invalid_quickroll_is_not_sent(client: FlaskClient, fake_vclient) -> None:
    """Verify a quickroll without a name or traits re-renders the form and is not created."""
    response = client.post(OWN_TABLE, data={"name": ""}, headers=_hx_headers(client))

    assert response.status_code == 200
    fake_vclient.assert_not_called(Routes.USERS_QUICKROLLS_CREATE)


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("POST", OTHER_TABLE, {"name": "Sneaky", "trait_one_id": "t1"}),
        ("POST", f"{OTHER_TABLE}/qr-1", {"name": "Sneaky", "trait_one_id": "t1"}),
        ("DELETE", f"{OTHER_TABLE}/qr-1", None),
        ("GET", f"{OTHER_TABLE}/form", None),
        ("GET", f"{OTHER_TABLE}/form/qr-1", None),
    ],
    ids=["create", "update", "delete", "add-form", "edit-form"],
)
def test_non_owner_cannot_change_quickrolls(
    client: FlaskClient, fake_vclient, method: str, path: str, data: dict | None
) -> None:
    """Verify only the profile owner may open quickroll forms or write quickrolls."""
    response = client.open(path, method=method, data=data, headers=_hx_headers(client))

    assert response.status_code == 403
    assert fake_vclient.requests == []
