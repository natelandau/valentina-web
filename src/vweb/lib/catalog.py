"""Application-wide JinjaX catalog singleton.

Owning the catalog here (instead of in ``vweb.app``) lets error handlers and
route modules import it at the top level without creating a circular import
through the application factory.
"""

from __future__ import annotations

from vweb.lib.jinja import register_jinjax_catalog

catalog = register_jinjax_catalog()
