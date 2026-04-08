"""Character inventory CRUD table view."""

from __future__ import annotations

from vweb.lib.crud_view import Column, CrudTableView
from vweb.routes.character_view.handlers_inventory import CharacterInventoryHandler


class CharacterInventoryTableView(CrudTableView):
    """Inline CRUD table for character inventory items."""

    handler_class = CharacterInventoryHandler
    table_name = "Inventory"
    item_name = "Item"
    table_id = "crud-inventory"
    columns = (
        Column("name", "Name"),
        Column("type", "Type"),
        Column("description", "Description", markdown=True, sortable=False),
    )
    form_component = "character_view.partials.crud_forms.InventoryForm"
