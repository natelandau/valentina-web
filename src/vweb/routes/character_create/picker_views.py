"""Character creation picker and single-autogen views."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flask import Response, abort, flash, request, session, url_for
from flask.views import MethodView
from vclient.exceptions import APIError

if TYPE_CHECKING:
    from vclient.models import ChargenSessionResponse, User

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404, get_user_campaign_experience
from vweb.lib.character_sheet import CharacterSheetService
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import is_storyteller
from vweb.routes.character_create import bp
from vweb.routes.character_create.autogen_services import (
    fetch_form_options,
    generate_single,
    list_sessions,
)

logger = logging.getLogger(__name__)


def build_characters_data(session_response: ChargenSessionResponse, user: User) -> list[dict]:
    """Build the character sheet data list for the comparison template.

    Args:
        session_response: The chargen session containing characters.
        user: The requesting user (needed for sheet rendering permissions).

    Returns:
        List of dicts with character, sheet_top, and sheet_sections keys.
    """
    characters_data = []
    for char in session_response.characters:
        sheet_svc = CharacterSheetService(char, user)
        full_sheet = sheet_svc.get_full_sheet()
        characters_data.append(
            {
                "character": char,
                "full_sheet": full_sheet,
            }
        )
    return characters_data


def selection_card_context(campaign_id: str) -> dict:
    """Build the shared template context for the selection card grid.

    Args:
        campaign_id: The campaign to look up XP info for.

    Returns:
        Dict with user_xp, and pending_sessions keys.
    """
    campaign_experience = get_user_campaign_experience(session["user_id"], campaign_id)
    user_xp = campaign_experience.xp_current if campaign_experience else 0

    now = datetime.now(tz=UTC)
    try:
        all_sessions = list_sessions(user_id=session["user_id"], campaign_id=campaign_id)
        pending_sessions = [s for s in all_sessions if s.expires_at > now]
    except APIError:
        logger.exception("Failed to list chargen sessions")
        pending_sessions = []

    return {
        "user_xp": user_xp,
        "pending_sessions": pending_sessions,
    }


class SelectionPageView(MethodView):
    """Full-page selection page for character creation methods."""

    def get(self, campaign_id: str) -> str:
        """Render the character creation selection page.

        Args:
            campaign_id: The campaign to create a character in.

        Returns:
            Rendered HTML for the selection page.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        return catalog.render(
            "character_create.Main",
            campaign=campaign,
            **selection_card_context(campaign_id),
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new",
    view_func=SelectionPageView.as_view("selection_page"),
    methods=["GET"],
)


class SelectionCardsView(MethodView):
    """Return the selection cards fragment for back navigation."""

    def get(self, campaign_id: str) -> str:
        """Render the selection cards fragment.

        Args:
            campaign_id: The campaign context.

        Returns:
            Rendered HTML fragment with the selection cards.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        return catalog.render(
            "character_create.partials.SelectionCards",
            campaign=campaign,
            **selection_card_context(campaign_id),
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/cards",
    view_func=SelectionCardsView.as_view("selection_cards"),
    methods=["GET"],
)


class SingleAutogenFormView(MethodView):
    """Single autogen form and submission."""

    def get(self, campaign_id: str) -> str:
        """Render the single autogen form with dropdown options.

        Args:
            campaign_id: The campaign to create a character in.

        Returns:
            Rendered HTML fragment for the form.
        """
        if not is_storyteller():
            abort(403)

        campaign = fetch_campaign_or_404(campaign_id)
        options = fetch_form_options()

        form_data: dict[str, str] = {}
        character_type = request.args.get("character_type", "").strip()
        if character_type:
            form_data["character_type"] = character_type

        return catalog.render(
            "character_create.partials.SingleAutogenForm",
            campaign=campaign,
            form_data=form_data,
            **options,
        )

    def post(self, campaign_id: str) -> Response | str:
        """Submit the single autogen form.

        Args:
            campaign_id: The campaign to create a character in.

        Returns:
            HX-Redirect on success, or re-rendered form with errors.
        """
        if not is_storyteller():
            abort(403)

        campaign = fetch_campaign_or_404(campaign_id)
        form_data = {k: v.strip() for k, v in request.form.items() if k != "csrf_token"}

        character_type = form_data.get("character_type", "")
        if not character_type:
            options = fetch_form_options()
            return catalog.render(
                "character_create.partials.SingleAutogenForm",
                campaign=campaign,
                errors=["Character type is required."],
                form_data=form_data,
                **options,
            )

        try:
            new_char = generate_single(
                user_id=session["user_id"],
                campaign_id=campaign_id,
                character_type=character_type,
                character_class=form_data.get("character_class") or None,
                experience_level=form_data.get("experience_level") or None,
                skill_focus=form_data.get("skill_focus") or None,
                concept_id=form_data.get("concept_id") or None,
                vampire_clan_id=form_data.get("vampire_clan_id") or None,
                werewolf_tribe_id=form_data.get("werewolf_tribe_id") or None,
                werewolf_auspice_id=form_data.get("werewolf_auspice_id") or None,
            )
        except APIError as exc:
            options = fetch_form_options()
            return catalog.render(
                "character_create.partials.SingleAutogenForm",
                campaign=campaign,
                errors=[str(exc)],
                form_data=form_data,
                **options,
            )

        clear_global_context_cache()
        flash("Character created successfully!", "success")
        redirect_url = url_for("character_view.character", character_id=new_char.id)
        return Response("", status=200, headers={"HX-Redirect": redirect_url})


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/single-autogen",
    view_func=SingleAutogenFormView.as_view("single_autogen_form"),
    methods=["GET", "POST"],
)
