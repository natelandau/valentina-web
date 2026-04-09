"""Quickroll CRUD handler for user profile quickroll tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import session
from vclient import sync_users_service
from vclient.models import QuickrollCreate, QuickrollUpdate

from vweb.lib.blueprint_cache import get_all_traits

if TYPE_CHECKING:
    from vclient.models import Quickroll


@dataclass
class QuickrollDisplay:
    """Display-friendly quickroll with resolved trait names.

    The CRUD table template accesses fields via ``item[field]`` (Jinja2 ``getattr``),
    so this dataclass provides the attribute names that the ``Column`` definitions expect.
    """

    id: str
    name: str
    description: str
    trait_one_name: str
    trait_two_name: str


class QuickrollHandler:
    """CRUD operations for user quickrolls.

    Wrap vclient user quickroll API calls with sync interface.
    Usable standalone from any route or via the CRUD table framework.
    """

    def __init__(self, parent_id: str) -> None:
        self._parent_id = parent_id
        self._svc = sync_users_service(company_id=session["company_id"])

    def list_items(self) -> list[QuickrollDisplay]:
        """Fetch all quickrolls for the user, resolving trait IDs to display names."""
        quickrolls = self._svc.list_all_quickrolls(self._parent_id)
        return [self._to_display(qr) for qr in quickrolls]

    def get_item(self, item_id: str) -> Quickroll:
        """Fetch a single quickroll by ID."""
        return self._svc.get_quickroll(self._parent_id, item_id)

    def validate(self, form_data: dict[str, str]) -> list[str]:
        """Validate quickroll form data.

        Args:
            form_data: Form field values keyed by field name.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if not form_data.get("name", "").strip():
            errors.append("Name is required")

        trait_ids = QuickrollHandler._extract_trait_ids(form_data)
        if not trait_ids:
            errors.append("At least one trait is required")

        return errors

    def create_item(self, form_data: dict[str, str]) -> None:
        """Create a new quickroll from form data."""
        trait_ids = self._extract_trait_ids(form_data)
        description = form_data.get("description", "").strip() or None

        request = QuickrollCreate(
            name=form_data["name"].strip(),
            description=description,
            trait_ids=trait_ids,
        )
        self._svc.create_quickroll(self._parent_id, request=request)

    def update_item(self, item_id: str, form_data: dict[str, str]) -> None:
        """Update an existing quickroll from form data."""
        trait_ids = self._extract_trait_ids(form_data)
        description = form_data.get("description", "").strip() or None

        request = QuickrollUpdate(
            name=form_data["name"].strip(),
            description=description,
            trait_ids=trait_ids,
        )
        self._svc.update_quickroll(self._parent_id, item_id, request=request)

    def delete_item(self, item_id: str) -> None:
        """Delete a quickroll."""
        self._svc.delete_quickroll(self._parent_id, item_id)

    @staticmethod
    def _extract_trait_ids(form_data: dict[str, str]) -> list[str]:
        """Collect non-empty trait IDs from form data."""
        ids: list[str] = []
        for key in ("trait_one_id", "trait_two_id"):
            val = form_data.get(key, "").strip()
            if val:
                ids.append(val)
        return ids

    @staticmethod
    def _to_display(qr: Quickroll) -> QuickrollDisplay:
        """Convert a Quickroll model to a display dataclass with resolved trait names."""
        trait_ids = qr.trait_ids
        all_traits = get_all_traits()
        t1 = all_traits.get(trait_ids[0]) if len(trait_ids) > 0 else None
        t2 = all_traits.get(trait_ids[1]) if len(trait_ids) > 1 else None

        return QuickrollDisplay(
            id=qr.id,
            name=qr.name,
            description=qr.description or "",
            trait_one_name=t1.name if t1 else "-",
            trait_two_name=t2.name if t2 else "-",
        )
