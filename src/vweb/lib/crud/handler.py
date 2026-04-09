"""Protocol for CRUD table handlers."""

from __future__ import annotations

from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class CrudHandler(Protocol[T_co]):
    """Interface for CRUD table operation handlers.

    Each handler encapsulates API calls, validation, and form data parsing
    for a specific table type. Handlers are standalone — usable from any
    route, not just the CRUD table framework.

    Generic over the item type ``T_co`` so concrete handlers are verified
    against specific model types (e.g. ``CrudHandler[Note]``).
    """

    def list_items(self) -> list[T_co]:
        """Return all items for the resource."""
        ...

    def get_item(self, item_id: str) -> T_co:
        """Return a single item by ID."""
        ...

    def create_item(self, form_data: dict[str, str]) -> None:
        """Create a new item from validated form data."""
        ...

    def update_item(self, item_id: str, form_data: dict[str, str]) -> None:
        """Update an existing item from validated form data."""
        ...

    def delete_item(self, item_id: str) -> None:
        """Delete an item by ID."""
        ...

    def validate(self, form_data: dict[str, str]) -> list[str]:
        """Validate form data and return a list of error messages."""
        ...
