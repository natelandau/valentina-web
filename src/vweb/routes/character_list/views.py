"""Campaign-scoped character list page.

The page renders the CampaignChrome plus the shared lazy ``CharacterListCard``
(scoped to the whole campaign), which owns its own server-side player/class/type
filtering via the ``/cards/character-list`` fragment endpoint.
"""

from __future__ import annotations

from flask import Blueprint, session
from flask.views import MethodView

from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.catalog import catalog

bp = Blueprint("character_list", __name__)


class CharacterListView(MethodView):
    """Full page: CampaignChrome + the lazy character list card."""

    def get(self, campaign_id: str) -> str:
        """Render the character list page for the campaign."""
        campaign = fetch_campaign_or_404(campaign_id)
        session["last_campaign_id"] = campaign_id

        return catalog.render("character_list.Index", campaign=campaign)


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters",
    view_func=CharacterListView.as_view("index"),
    methods=["GET"],
)
