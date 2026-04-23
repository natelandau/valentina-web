"""Shared lazy-card endpoints.

Serve HTMX fragments for reusable cards like Statistics and Recent Dicerolls.
Parent templates drop a ``<shared.cards.X>`` wrapper and the wrapper points
its ``hx-get`` at an endpoint here.
"""

from __future__ import annotations

from flask import Blueprint, abort, request
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import get_recent_player_dicerolls
from vweb.lib.statistics_cache import ScopeType, get_statistics

bp = Blueprint("shared_cards", __name__, url_prefix="/cards")


class StatisticsCardView(MethodView):
    """Lazy statistics card, scoped by exactly one of campaign/user/character."""

    def get(self) -> str:
        """Validate exactly one scope query arg and render the statistics fragment."""
        scopes: list[tuple[ScopeType, str]] = [
            ("campaign", request.args.get("campaign_id", "")),
            ("user", request.args.get("user_id", "")),
            ("character", request.args.get("character_id", "")),
        ]
        set_scopes = [(name, value) for name, value in scopes if value]
        if len(set_scopes) != 1:
            abort(400)

        scope_type, scope_id = set_scopes[0]
        return catalog.render(
            "shared.cards.partials.StatisticsContent",
            statistics=get_statistics(scope_type, scope_id),
            title=request.args.get("title", "Statistics"),
            col_span=request.args.get("col_span", 0, type=int),
        )


bp.add_url_rule(
    "/statistics",
    view_func=StatisticsCardView.as_view("statistics"),
    methods=["GET"],
)


class DiceRollsCardView(MethodView):
    """Lazy Recent Dicerolls card, scoped by at least one of campaign/user/character."""

    def get(self) -> str:
        """Validate at least one scope query arg and render the dicerolls fragment."""
        campaign_id = request.args.get("campaign_id", "")
        user_id = request.args.get("user_id", "")
        character_id = request.args.get("character_id", "")

        if not any([campaign_id, user_id, character_id]):
            abort(400)

        rolls = get_recent_player_dicerolls(
            campaign_id=campaign_id,
            character_id=character_id,
            user_id=user_id,
            limit=request.args.get("limit", 50, type=int),
        )
        return catalog.render(
            "shared.cards.partials.RecentDiceRollsContent",
            rolls=rolls,
            col_span=request.args.get("col_span", 1, type=int),
            pagination=request.args.get("pagination", 5, type=int),
            title=request.args.get("title", "Recent Dicerolls"),
            empty_message=request.args.get("empty_message", "No dicerolls yet"),
        )


bp.add_url_rule(
    "/dice-rolls",
    view_func=DiceRollsCardView.as_view("dice_rolls"),
    methods=["GET"],
)
