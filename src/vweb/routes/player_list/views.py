"""Campaign-scoped player list views.

Mirrors the character_list pattern: a full-page shell + an HTMX partial that
swaps into the body slot on filter change.
"""

from __future__ import annotations

from flask import Blueprint, request, session
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404
from vweb.routes.player_list import services

bp = Blueprint("player_list", __name__)


def _read_filters() -> tuple[str | None, str | None]:
    """Read the role and has_characters filter params, returning None for empties."""
    role = request.args.get("role", "").strip() or None
    has_characters = request.args.get("has_characters", "").strip() or None
    return role, has_characters


class PlayerListView(MethodView):
    """Full page: CampaignChrome + filter bar + initial list."""

    def get(self, campaign_id: str) -> str:
        """Render the player list page for the campaign."""
        campaign = fetch_campaign_or_404(campaign_id)
        session["last_campaign_id"] = campaign_id

        users = services.get_all_players()
        role_options = services.build_filter_options(users)

        return catalog.render(
            "player_list.Index",
            campaign=campaign,
            users=users,
            role_options=role_options,
        )


class PlayerListPartialView(MethodView):
    """HTMX endpoint: returns the filtered list card for swap into the body slot."""

    def get(self, campaign_id: str) -> str:
        """Return the filtered list card."""
        fetch_campaign_or_404(campaign_id)

        role, has_characters = _read_filters()
        users = services.get_all_players()
        filtered = services.filter_players(
            users,
            campaign_id,
            role=role,
            has_characters=has_characters,
        )

        return catalog.render(
            "player_list.partials.PlayerList",
            campaign_id=campaign_id,
            users=filtered,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/players",
    view_func=PlayerListView.as_view("index"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/players/list",
    view_func=PlayerListPartialView.as_view("list_partial"),
    methods=["GET"],
)
