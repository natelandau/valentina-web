"""Tests for CharacterInventoryHandler service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.models import InventoryItemCreate, InventoryItemUpdate
from vclient.testing import CharacterFactory

from vweb.routes.character_view.handlers_inventory import CharacterInventoryHandler


@pytest.fixture
def mock_character(mock_global_context):
    """Create a factory-built character in the global context."""
    char = CharacterFactory.build(id="char-123", campaign_id="camp-456")
    mock_global_context.characters = [char]
    return char


@pytest.fixture
def mock_svc(mocker):
    """Mock the sync_characters_service for the handler module."""
    svc = MagicMock()
    mocker.patch(
        "vweb.routes.character_view.handlers_inventory.sync_characters_service", return_value=svc
    )
    return svc


class TestCharacterInventoryHandlerValidation:
    """Tests for CharacterInventoryHandler.validate()."""

    def test_empty_name_returns_error(self) -> None:
        """Verify validation rejects an empty name."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with an empty name
        errors = handler.validate({"name": "", "type": "WEAPON"})

        # Then a name error is returned
        assert "Name is required" in errors

    def test_empty_type_returns_error(self) -> None:
        """Verify validation rejects an empty type."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with an empty type
        errors = handler.validate({"name": "Sword", "type": ""})

        # Then a type error is returned
        assert "Type is required" in errors

    def test_whitespace_only_fields_return_errors(self) -> None:
        """Verify validation rejects whitespace-only fields."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating form data with whitespace-only values
        errors = handler.validate({"name": "   ", "type": "  \t  "})

        # Then both errors are returned
        assert "Name is required" in errors
        assert "Type is required" in errors

    def test_valid_data_returns_no_errors(self) -> None:
        """Verify validation accepts valid form data."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating valid form data
        errors = handler.validate({"name": "Sword", "type": "WEAPON"})

        # Then no errors are returned
        assert errors == []


class TestCharacterInventoryHandlerOperations:
    """Tests for CharacterInventoryHandler CRUD operations."""

    def test_list_items_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify list_items delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When listing items
            handler.list_items()

            # Then the service is called with the parent character ID
            mock_svc.list_all_inventory.assert_called_once_with("char-123")

    def test_create_item_strips_whitespace_and_omits_empty_description(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify create_item strips name whitespace and omits empty description."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When creating an item with padded name and empty description
            handler.create_item({"name": "  Sword  ", "type": "WEAPON", "description": ""})

            # Then the service receives a model with stripped name and no description
            mock_svc.create_inventory_item.assert_called_once_with(
                "char-123",
                request=InventoryItemCreate(name="Sword", type="WEAPON", description=None),
            )

    def test_create_item_includes_description_when_provided(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify create_item passes description when non-empty."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When creating an item with a description
            handler.create_item(
                {"name": "Sword", "type": "WEAPON", "description": "  Sharp blade  "}
            )

            # Then the service receives a model with the stripped description
            mock_svc.create_inventory_item.assert_called_once_with(
                "char-123",
                request=InventoryItemCreate(name="Sword", type="WEAPON", description="Sharp blade"),
            )

    def test_update_item_sets_empty_description_to_none(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify update_item converts empty description to None."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When updating with an empty description
            handler.update_item(
                "inv-1", {"name": "  Updated Sword  ", "type": "WEAPON", "description": "  "}
            )

            # Then the service receives a model with stripped name and None description
            mock_svc.update_inventory_item.assert_called_once_with(
                "char-123",
                "inv-1",
                request=InventoryItemUpdate(name="Updated Sword", type="WEAPON", description=None),
            )

    def test_delete_item_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify delete_item delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When deleting an item
            handler.delete_item("inv-1")

            # Then the service is called with the correct IDs
            mock_svc.delete_inventory_item.assert_called_once_with("char-123", "inv-1")

    def test_get_item_calls_service(
        self, app, mock_character, mock_global_context, mock_svc
    ) -> None:
        """Verify get_item delegates to the vclient service."""
        with app.test_request_context():
            # Given a handler with a mocked service
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            handler = CharacterInventoryHandler("char-123")

            # When getting a single item
            handler.get_item("inv-1")

            # Then the service is called with the correct IDs
            mock_svc.get_inventory_item.assert_called_once_with("char-123", "inv-1")

    def test_init_raises_for_unknown_character(self, app, mock_global_context, mock_svc) -> None:
        """Verify constructor raises ValueError for a character not in global context."""
        with app.test_request_context():
            # Given an empty characters list in global context
            from flask import g, session

            g.global_context = mock_global_context
            session["user_id"] = "test-user-id"
            mock_global_context.characters = []

            # When/Then constructing with an unknown character ID raises ValueError
            with pytest.raises(ValueError, match="Character not found"):
                CharacterInventoryHandler("nonexistent-id")
