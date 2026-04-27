"""Tests for character_view inventory CRUD table routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    InventoryItemFactory,
)


@pytest.fixture
def _mock_character(mock_global_context) -> None:
    """Add a character to global context for CRUD tests."""
    char = CharacterFactory.build(
        id="char-123",
        campaign_id="camp-456",
        name="Test Character",
        user_player_id="test-user-id",
    )
    mock_global_context.characters = [char]
    campaign = CampaignFactory.build(id="camp-456")
    mock_global_context.campaigns = [campaign]


@pytest.fixture
def mock_inventory_handler(mocker, _mock_character):
    """Mock the CRUD handler for character inventory."""
    items = [
        InventoryItemFactory.build(id="inv-1", name="Sword", type="WEAPON", description="Sharp"),
        InventoryItemFactory.build(id="inv-2", name="Apple", type="EQUIPMENT", description="Tasty"),
        InventoryItemFactory.build(
            id="inv-3", name="Shield", type="CONSUMABLE", description="Sturdy"
        ),
    ]

    handler = MagicMock()
    handler.list_items.return_value = items
    handler.get_item.return_value = items[0]
    handler.create_item.return_value = None
    handler.update_item.return_value = None
    handler.delete_item.return_value = None
    handler.validate.return_value = []

    mocker.patch(
        "vweb.routes.character_view.views_inventory.CharacterInventoryTableView._build_handler",
        return_value=handler,
    )
    return handler


class TestCharacterInventoryGet:
    """Tests for GET requests to character inventory CRUD."""

    def test_get_table_returns_200(self, client, mock_inventory_handler) -> None:
        """Verify GET returns the inventory table HTML."""
        response = client.get(
            "/character/char-123/inventory/items",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Sword" in response.data

    def test_default_sort_is_first_sortable_field(self, client, mock_inventory_handler) -> None:
        """Verify table defaults to sorting by first sortable column ascending."""
        response = client.get(
            "/character/char-123/inventory/items",
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert body.index("Apple") < body.index("Shield") < body.index("Sword")

    def test_sort_descending(self, client, mock_inventory_handler) -> None:
        """Verify descending sort reverses item order."""
        response = client.get(
            "/character/char-123/inventory/items?sort=-name",
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert body.index("Sword") < body.index("Shield") < body.index("Apple")

    def test_nonsortable_field_falls_back(self, client, mock_inventory_handler) -> None:
        """Verify sorting by a non-sortable field falls back to default."""
        response = client.get(
            "/character/char-123/inventory/items?sort=description",
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert body.index("Apple") < body.index("Shield") < body.index("Sword")


class TestCharacterInventoryEditable:
    """Tests for inventory editable behavior."""

    def test_hides_buttons_when_not_editable(self, client, mock_inventory_handler) -> None:
        """Verify table with editable=false hides Add/Edit/Delete."""
        response = client.get(
            "/character/char-123/inventory/items?editable=false",
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert "Add Item" not in body
        assert "Edit" not in body
        assert "Delete" not in body

    def test_shows_buttons_when_editable(self, client, mock_inventory_handler) -> None:
        """Verify table with editable=true shows Add/Edit/Delete."""
        response = client.get(
            "/character/char-123/inventory/items?editable=true",
            headers={"HX-Request": "true"},
        )
        body = response.get_data(as_text=True)
        assert "Add Item" in body
        assert "Edit" in body
        assert "Delete" in body
