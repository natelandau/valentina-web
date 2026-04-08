"""Base notes handler with shared CRUD logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vclient.models import Note


class BaseNotesHandler:
    """Shared note CRUD operations for all note handler types.

    Subclasses must set ``_parent_id`` and ``_svc`` in their ``__init__``.
    The service object must expose ``list_all_notes``, ``get_note``,
    ``create_note``, ``update_note``, and ``delete_note`` methods.
    """

    _parent_id: str
    _svc: Any

    def list_items(self) -> list[Note]:
        """Fetch all notes for the parent resource."""
        return self._svc.list_all_notes(self._parent_id)

    def get_item(self, item_id: str) -> Note:
        """Fetch a single note by ID."""
        return self._svc.get_note(self._parent_id, item_id)

    def validate(self, form_data: dict[str, str]) -> list[str]:
        """Validate note form data.

        Args:
            form_data: Form field values keyed by field name.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if not form_data.get("title", "").strip():
            errors.append("Title is required")
        if not form_data.get("content", "").strip():
            errors.append("Content is required")
        return errors

    def create_item(self, form_data: dict[str, str]) -> None:
        """Create a new note from form data."""
        self._svc.create_note(
            self._parent_id,
            title=form_data["title"].strip(),
            content=form_data["content"].strip(),
        )

    def update_item(self, item_id: str, form_data: dict[str, str]) -> None:
        """Update an existing note from form data."""
        self._svc.update_note(
            self._parent_id,
            item_id,
            title=form_data["title"].strip(),
            content=form_data["content"].strip(),
        )

    def delete_item(self, item_id: str) -> None:
        """Delete a note."""
        self._svc.delete_note(self._parent_id, item_id)
