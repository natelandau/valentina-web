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

    @pytest.mark.parametrize(
        ("form_data", "error_fields"),
        [
            ({"name": "", "type": "WEAPON"}, {"name"}),
            ({"name": "Sword", "type": ""}, {"type"}),
            ({"name": "   ", "type": "  \t  "}, {"name", "type"}),
            ({"name": "Sword", "type": "WEAPON"}, set()),
        ],
        ids=["empty-name", "empty-type", "whitespace-only", "valid"],
    )
    def test_requires_name_and_type(self, form_data: dict, error_fields: set) -> None:
        """Verify blank or whitespace-only name and type are rejected per field."""
        # Given a handler instance with no service dependency
        handler = CharacterInventoryHandler.__new__(CharacterInventoryHandler)

        # When validating the form data
        errors = handler.validate(form_data)

        # Then exactly the blank fields carry errors
        assert set(errors) == error_fields


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

    @pytest.mark.parametrize(
        ("description", "expected_json"),
        [
            ("", {"name": "Sword", "type": "WEAPON"}),
            ("  Sharp blade  ", {"name": "Sword", "type": "WEAPON", "description": "Sharp blade"}),
        ],
        ids=["empty-description-omitted", "description-stripped"],
    )
    def test_create_item_sends_stripped_fields(
        self, handler, fake_vclient, description: str, expected_json: dict
    ) -> None:
        """Verify create_item strips whitespace and omits an empty description."""
        # When creating an item with a padded name
        handler.create_item({"name": "  Sword  ", "type": "WEAPON", "description": description})

        # Then the API receives stripped values and no empty description
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_CREATE,
            params={"character_id": "char-123"},
            json=expected_json,
            times=1,
        )

    def test_update_item_clears_empty_description(self, handler, fake_vclient) -> None:
        """Verify update_item clears the description when the field is blank."""
        # When updating with an empty description
        handler.update_item(
            "inv-1", {"name": "  Updated Sword  ", "type": "WEAPON", "description": "  "}
        )

        # Then the API receives a stripped name and a null description, which clears it
        fake_vclient.assert_called(
            Routes.CHARACTERS_INVENTORY_UPDATE,
            params={"character_id": "char-123", "item_id": "inv-1"},
            json={"name": "Updated Sword", "type": "WEAPON", "description": None},
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
