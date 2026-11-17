"""Tests for CharacterInventoryHandler service."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import CharacterFactory, Routes
from vweb.routes.character_view.handlers_inventory import CharacterInventoryHandler


@pytest.fixture
def mock_character(mock_global_context):
    """Create a factory-built character in the global context."""
    char = CharacterFactory.build(id="char-123", campaign_id="camp-456")
    mock_global_context.characters = [char]
    return char


@pytest.fixture
def handler(app, fake_vclient, mock_character, mock_global_context):
    """Build a handler for char-123 inside a seeded request context."""
    from flask import g

    with app.test_request_context():
        g.global_context = mock_global_context
        seed_session()
        yield CharacterInventoryHandler("char-123")


class TestCharacterInventoryHandlerValidation:
    """Tests for CharacterInventoryHandler.validate()."""

    def test_empty_name_returns_error(self) -> None:
        """Verify validation rejects an empty name."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with an empty name
        errors = handler.validate({"name": "", "type": "WEAPON"})

        # Then a name error is returned
        assert errors["name"] == "Name is required"

    def test_empty_type_returns_error(self) -> None:
        """Verify validation rejects an empty type."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with an empty type
        errors = handler.validate({"name": "Sword", "type": ""})

        # Then a type error is returned
        assert errors["type"] == "Type is required"

    def test_whitespace_only_fields_return_errors(self) -> None:
        """Verify validation rejects whitespace-only fields."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with whitespace-only values
        errors = handler.validate({"name": "   ", "type": "  \t  "})

        # Then both errors are returned
        assert errors["name"] == "Name is required"
        assert errors["type"] == "Type is required"

    def test_valid_data_returns_no_errors(self) -> None:
        """Verify validation accepts valid form data."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating valid form data
        errors = handler.validate({"name": "Sword", "type": "WEAPON"})

        # Then no errors are returned
        assert errors == {}


class TestCharacterInventoryHandlerOperations:
    """Tests for CharacterInventoryHandler CRUD operations."""

    def test_list_items_calls_service(self, handler, fake_vclient) -> None:
        """Verify list_items fetches the parent character's inventory."""
        # When listing items
        handler.list_items()

        # Then the inventory list route is requested for the parent character
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_LIST,
            params={"company_id": "test-company-id", "character_id": "char-123"},
        )

    def test_create_item_strips_whitespace_and_omits_empty_description(
        self, handler, fake_vclient
    ) -> None:
        """Verify create_item strips name whitespace and omits empty description."""
        # When creating an item with padded name and empty description
        handler.create_item({"name": "  Sword  ", "type": "WEAPON", "description": ""})

        # Then the API receives a stripped name and no description
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_CREATE,
            params={"character_id": "char-123"},
            json={"name": "Sword", "type": "WEAPON"},
            times=1,
        )

    def test_create_item_includes_description_when_provided(self, handler, fake_vclient) -> None:
        """Verify create_item passes description when non-empty."""
        # When creating an item with a description
        handler.create_item({"name": "Sword", "type": "WEAPON", "description": "  Sharp blade  "})

        # Then the API receives the stripped description
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_CREATE,
            params={"character_id": "char-123"},
            json={"name": "Sword", "type": "WEAPON", "description": "Sharp blade"},
            times=1,
        )

    def test_update_item_sets_empty_description_to_none(self, handler, fake_vclient) -> None:
        """Verify update_item converts empty description to None."""
        # When updating with an empty description
        handler.update_item(
            "inv-1", {"name": "  Updated Sword  ", "type": "WEAPON", "description": "  "}
        )

        # Then the API receives a stripped name and no description
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_UPDATE,
            params={"character_id": "char-123", "item_id": "inv-1"},
            json={"name": "Updated Sword", "type": "WEAPON"},
            times=1,
        )

    def test_delete_item_calls_service(self, handler, fake_vclient) -> None:
        """Verify delete_item deletes the item on the parent character."""
        # When deleting an item
        handler.delete_item("inv-1")

        # Then the delete route is requested with both IDs
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_DELETE,
            params={"character_id": "char-123", "item_id": "inv-1"},
            times=1,
        )

    def test_get_item_calls_service(self, handler, fake_vclient) -> None:
        """Verify get_item fetches the item on the parent character."""
        # When getting a single item
        handler.get_item("inv-1")

        # Then the item route is requested with both IDs
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_GET,
            params={"character_id": "char-123", "item_id": "inv-1"},
            times=1,
        )

    def test_init_raises_for_unknown_character(self, app, mock_global_context) -> None:
        """Verify constructor raises ValueError for a character not in global context."""
        with app.test_request_context():
            # Given an empty characters list in global context
            from flask import g

            g.global_context = mock_global_context
            seed_session()
            mock_global_context.characters = []

            # When/Then constructing with an unknown character ID raises ValueError
            with pytest.raises(ValueError, match="Character not found"):
                CharacterInventoryHandler("nonexistent-id")
