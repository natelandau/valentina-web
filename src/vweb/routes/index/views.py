"""Main application routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, g, redirect, session, url_for
from flask.views import MethodView

from vweb.lib.api import get_remembered_campaign
from vweb.lib.catalog import catalog

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response as WerkzeugResponse

bp = Blueprint("index", __name__)


class IndexView(MethodView):
    """Home page. Landing page for guests, entry redirect for authenticated users."""

    def get(self) -> str | WerkzeugResponse:
        """Route the visitor to the landing page, their campaign, or the company hub.

        Entry rules: a remembered campaign wins, a sole campaign is entered
        directly, and anything ambiguous (zero or many campaigns) lands on the
        company hub.
        """
        if "user_id" not in session:
            return catalog.render("auth.LandingPage")

        # The inject_global_context hook guarantees a context here: sessions
        # missing the company scope are cleared and redirected before any view.
        campaigns = g.global_context.campaigns

        remembered = get_remembered_campaign(campaigns)
        if remembered is not None:
            return redirect(url_for("campaign.campaign", campaign_id=remembered.id))

        if len(campaigns) == 1:
            return redirect(url_for("campaign.campaign", campaign_id=campaigns[0].id))

        return redirect(url_for("company_hub.home"))


bp.add_url_rule("/", view_func=IndexView.as_view("index"))
