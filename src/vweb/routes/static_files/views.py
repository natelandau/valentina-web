"""Root-level static file routes (robots.txt, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, current_app

if TYPE_CHECKING:
    from flask import Response

bp = Blueprint("static_files", __name__)


@bp.route("/robots.txt")
def robots_txt() -> Response:
    """Serve robots.txt from the static directory."""
    return current_app.send_static_file("robots.txt")
