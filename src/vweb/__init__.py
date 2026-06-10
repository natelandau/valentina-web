"""Valentina web client."""

__version__ = "0.11.0"

from vweb.app import create_app, main
from vweb.lib.catalog import catalog

__all__ = ["__version__", "catalog", "create_app", "main"]
