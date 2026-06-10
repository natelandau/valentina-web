"""Character creation picker and single-autogen views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import abort, flash, request, session, url_for
from flask.views import MethodView
from vclient.exceptions import APIError

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response

from vweb.lib import cache
from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.catalog import catalog
from vweb.lib.guards import is_storyteller
from vweb.lib.htmx import hx_redirect
from vweb.routes.character_create import bp
from vweb.routes.character_create.autogen_services import (
    fetch_form_options,
    generate_single,
)
from vweb.routes.character_create.picker_services import selection_card_context


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

        cache.global_context.clear(session["company_id"], session["user_id"])
        flash("Character created successfully!", "success")
        return hx_redirect(url_for("character_view.character", character_id=new_char.id))


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/single-autogen",
    view_func=SingleAutogenFormView.as_view("single_autogen_form"),
    methods=["GET", "POST"],
)
