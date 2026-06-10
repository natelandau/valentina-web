"""Company hub routes: the company-level home page."""

from __future__ import annotations

from flask import Blueprint, g
from flask.views import MethodView

from vweb.lib.catalog import catalog

bp = Blueprint("company_hub", __name__)


class HubView(MethodView):
    """Render the company hub: masthead, company tabs, campaign grid."""

    def get(self) -> str:
        """Render the hub entirely from the cached global context (no API calls)."""
        campaigns = sorted(
            g.global_context.campaigns,
            key=lambda campaign: campaign.date_modified,
            reverse=True,
        )
        return catalog.render("company_hub.HubPage", campaigns=campaigns)


bp.add_url_rule("/home", view_func=HubView.as_view("home"))
