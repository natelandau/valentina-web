"""Tests for character_view inventory CRUD table routes."""

from __future__ import annotations

import pytest

from tests.conftest import htmx_post
from vweb.api_client.testing import (
    InventoryItemFactory,
    Routes,
)

TABLE_URL = "/character/char-123/inventory/items"
FORM_URL = "/character/char-123/inventory/items/form"


@pytest.fixture
def inventory(fake_vclient):
    """Serve three inventory items from the API."""
    fake_vclient.set_response(
        Routes.CHARACTERS_INVENTORY_LIST,
        items=[
            InventoryItemFactory.build(id="inv-1", name="Sword", type="WEAPON"),
            InventoryItemFactory.build(id="inv-2", name="Apple", type="EQUIPMENT"),
            InventoryItemFactory.build(id="inv-3", name="Shield", type="CONSUMABLE"),
        ],
    )


class TestCharacterInventoryGet:
    """Tests for GET requests to character inventory CRUD."""

    @pytest.mark.parametrize(
        ("sort", "expected"),
        [
            ("", ["Apple", "Shield", "Sword"]),
            ("-name", ["Sword", "Shield", "Apple"]),
            ("description", ["Apple", "Shield", "Sword"]),
        ],
        ids=["default-first-sortable", "descending", "non-sortable-falls-back"],
    )
    def test_lists_items_in_sort_order(
        self, client, set_owner, inventory, sort: str, expected: list[str]
    ) -> None:
        """Verify the table lists the API's items in the requested sort order."""
        # Given the user's own character
        set_owner("test-user-id")

        # When requesting the table
        response = client.get(f"{TABLE_URL}?sort={sort}", headers={"HX-Request": "true"})

        # Then items appear in the expected order
        body = response.get_data(as_text=True)
        positions = [body.index(name) for name in expected]
        assert positions == sorted(positions)

    @pytest.mark.parametrize(
        ("owner_id", "editable", "controls_shown"),
        [
            ("test-user-id", "true", True),
            ("test-user-id", "false", False),
            ("other-user-id", "true", False),
        ],
        ids=["owner", "owner-read-only-view", "other-player"],
    )
    def test_edit_controls_follow_permission(
        self, client, set_owner, inventory, owner_id, editable, controls_shown
    ) -> None:
        """Verify edit controls show only for an editor, and the query flag never grants them."""
        # Given a character owned by the given user
        set_owner(owner_id)

        # When requesting the table
        response = client.get(f"{TABLE_URL}?editable={editable}", headers={"HX-Request": "true"})

        # Then the items show, with edit controls only when the user may edit
        body = response.get_data(as_text=True)
        assert "Sword" in body
        assert (FORM_URL in body) is controls_shown


class TestCharacterInventoryPost:
    """Tests for POST requests to character inventory CRUD."""

    def test_owner_creates_item(self, client, set_owner, fake_vclient) -> None:
        """Verify the owner's new item is sent to the API."""
        # Given the user's own character
        set_owner("test-user-id")

        # When creating an item
        response = htmx_post(client, TABLE_URL, {"name": "Sword", "type": "WEAPON"})

        # Then the item is created on the character
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_CREATE,
            params={"character_id": "char-123"},
            json={"name": "Sword", "type": "WEAPON"},
            times=1,
        )

    def test_other_player_cannot_create(self, client, set_owner, fake_vclient) -> None:
        """Verify a create POST on another player's character is 403."""
        # Given another player's character
        set_owner("other-user-id")

        # When attempting to create an item
        response = htmx_post(client, TABLE_URL, {"name": "Sword", "type": "WEAPON"})

        # Then the request is forbidden and no create occurs
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CHARACTERS_INVENTORY_CREATE)
