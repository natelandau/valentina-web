"""Character creation route package."""

from flask import Blueprint

bp = Blueprint("character_create", __name__)

# Import view modules to trigger URL rule registration
from vweb.routes.character_create import (  # noqa: E402, F401
    autogen_views,
    manual_views,
    picker_views,
)
