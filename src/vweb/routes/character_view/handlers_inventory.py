"""Character inventory CRUD handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flask import g, session
from vclient import sync_characters_service
from vclient.models import InventoryItemCreate, InventoryItemUpdate

if TYPE_CHECKING:
    from vclient.models import InventoryItem
    from vclient.models.characters import CharacterInventoryType


class CharacterInventoryHandler:
    """CRUD operations for character inventory items.

    Wrap vclient character inventory API calls with sync interface.
    Usable standalone from any route or via the CRUD table framework.
    """

    def __init__(self, parent_id: str) -> None:
        self._parent_id = parent_id
        character = next((c for c in g.global_context.characters if c.id == parent_id), None)
        if character is None:
            msg = f"Character not found: {parent_id}"
            raise ValueError(msg)

        self._svc = sync_characters_service(
            user_id=session.get("user_id", ""),
            campaign_id=character.campaign_id,
            company_id=session["company_id"],
        )

    def list_items(self) -> list[InventoryItem]:
        """Fetch all inventory items for the character."""
        return self._svc.list_all_inventory(self._parent_id)

    def get_item(self, item_id: str) -> InventoryItem:
        """Fetch a single inventory item by ID."""
        return self._svc.get_inventory_item(self._parent_id, item_id)

    def validate(self, form_data: dict[str, str]) -> list[str]:
        """Validate inventory form data.

        Args:
            form_data: Form field values keyed by field name.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if not form_data.get("name", "").strip():
            errors.append("Name is required")
        if not form_data.get("type", "").strip():
            errors.append("Type is required")
        return errors

    def create_item(self, form_data: dict[str, str]) -> None:
        """Create a new inventory item from form data."""
        description = form_data.get("description", "").strip() or None
        item_request = InventoryItemCreate(
            name=form_data["name"].strip(),
            type=cast("CharacterInventoryType", form_data["type"]),
            description=description,
        )
        self._svc.create_inventory_item(self._parent_id, request=item_request)

    def update_item(self, item_id: str, form_data: dict[str, str]) -> None:
        """Update an existing inventory item from form data."""
        item_request = InventoryItemUpdate(
            name=form_data["name"].strip(),
            type=cast("CharacterInventoryType", form_data["type"]),
            description=form_data.get("description", "").strip() or None,
        )
        self._svc.update_inventory_item(self._parent_id, item_id, request=item_request)

    def delete_item(self, item_id: str) -> None:
        """Delete an inventory item."""
        self._svc.delete_inventory_item(self._parent_id, item_id)
