"""Valentina web client."""

__version__ = "0.16.1"

from vweb.app import create_app, main
from vweb.lib.catalog import catalog

__all__ = ["__version__", "catalog", "create_app", "main"]
