"""Campaign-scoped character list views.

One blueprint with two endpoints:

- Full page shell at ``/campaign/<campaign_id>/characters`` — renders the
  CampaignChrome, filter bar, and initial server-rendered list.
- HTMX partial at ``/campaign/<campaign_id>/characters/list`` — returns the
  filtered list card, swapped into ``#character-list-body`` on filter change.
"""

from __future__ import annotations

from flask import Blueprint, g, request, session
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404, get_visible_characters_for_campaign
from vweb.lib.guards import is_storyteller
from vweb.routes.character_list import services

bp = Blueprint("character_list", __name__)


def _users_by_id() -> dict[str, str]:
    """Build a lookup of user id → username from the global context."""
    return {user.id: user.username for user in g.global_context.users}


def _read_filters() -> tuple[str | None, str | None, str | None]:
    """Read filter params from the request, returning None for missing/empty values.

    The ``type`` filter is silently dropped for non-storyteller callers even if
    the param is present — defense in depth around the storyteller-only filter.
    """
    player_id = request.args.get("player", "").strip() or None
    character_class = request.args.get("char_class", "").strip() or None
    type_filter = request.args.get("type", "").strip() or None
    if type_filter and not is_storyteller():
        type_filter = None
    return player_id, character_class, type_filter


class CharacterListView(MethodView):
    """Full page: CampaignChrome + filter bar + initial list."""

    def get(self, campaign_id: str) -> str:
        """Render the character list page for the campaign."""
        campaign = fetch_campaign_or_404(campaign_id)
        session["last_campaign_id"] = campaign_id

        characters = get_visible_characters_for_campaign(campaign_id)
        users_by_id = _users_by_id()
        player_options, class_options = services.build_filter_options(characters, users_by_id)

        return catalog.render(
            "character_list.Index",
            campaign=campaign,
            characters=characters,
            player_options=player_options,
            class_options=class_options,
            is_storyteller=is_storyteller(),
        )


class CharacterListPartialView(MethodView):
    """HTMX endpoint: returns the filtered list card for swap into the body slot."""

    def get(self, campaign_id: str) -> str:
        """Return the filtered list card."""
        fetch_campaign_or_404(campaign_id)

        player_id, character_class, type_filter = _read_filters()
        visible = get_visible_characters_for_campaign(campaign_id)
        filtered = services.filter_characters(
            visible,
            player_id=player_id,
            character_class=character_class,
            type_filter=type_filter,
        )

        return catalog.render(
            "character_list.partials.CharacterList",
            campaign_id=campaign_id,
            characters=filtered,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters",
    view_func=CharacterListView.as_view("index"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/list",
    view_func=CharacterListPartialView.as_view("list_partial"),
    methods=["GET"],
)
