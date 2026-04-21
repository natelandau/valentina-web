"""Main application routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, redirect, session, url_for
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import get_active_campaign

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response as WerkzeugResponse

bp = Blueprint("index", __name__)


class IndexView(MethodView):
    """Home page. Landing page for guests, redirect for authenticated users."""

    def get(self) -> str | WerkzeugResponse:
        """Render landing page or redirect to the active campaign."""
        if "user_id" not in session:
            return catalog.render("auth.LandingPage")

        selected = get_active_campaign()
        if selected is None:
            return catalog.render("index.NoCampaign")

        return redirect(url_for("campaign.campaign", campaign_id=selected.id))


bp.add_url_rule("/", view_func=IndexView.as_view("index"))
