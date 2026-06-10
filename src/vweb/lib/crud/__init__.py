"""Generic CRUD table framework."""

from vweb.lib.crud.handler import CrudHandler
from vweb.lib.crud.routing import register_crud_table_routes
from vweb.lib.crud.view import Column, CrudTableView

__all__ = ["Column", "CrudHandler", "CrudTableView", "register_crud_table_routes"]
