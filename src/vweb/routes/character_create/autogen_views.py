"""Multi-autogen character creation views."""

from __future__ import annotations

import logging

from flask import Response, flash, g, request, session, url_for
from flask.views import MethodView
from vclient.exceptions import APIError

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.global_context import clear_global_context_cache
from vweb.routes.character_create import bp
from vweb.routes.character_create.autogen_services import (
    finalize_session,
    get_session,
    start_session,
)
from vweb.routes.character_create.picker_views import (
    build_characters_data,
    selection_card_context,
)

logger = logging.getLogger(__name__)


class MultiAutogenView(MethodView):
    """Start a multi-autogen chargen session."""

    def post(self, campaign_id: str) -> Response | str:
        """Start a chargen session and render character comparison.

        Args:
            campaign_id: The campaign to create a character in.

        Returns:
            Rendered comparison fragment, or selection cards with error.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        user = g.requesting_user

        try:
            session_response = start_session(
                user_id=user.id,
                campaign_id=campaign_id,
            )
        except APIError:
            logger.exception("Failed to start chargen session")
            return catalog.render(
                "character_create.partials.SelectionCards",
                campaign=campaign,
                **selection_card_context(campaign_id),
                errors=["Failed to start character generation session. Please try again."],
            )

        return catalog.render(
            "character_create.partials.MultiAutogenCompare",
            campaign=campaign,
            session_id=session_response.id,
            characters_data=build_characters_data(session_response, user),
            expires_at=session_response.expires_at,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/multi-autogen",
    view_func=MultiAutogenView.as_view("multi_autogen"),
    methods=["POST"],
)


class MultiAutogenFinalizeView(MethodView):
    """Finalize a multi-autogen session by selecting a character."""

    def post(self, campaign_id: str) -> Response | str:
        """Finalize the chargen session with the selected character.

        Args:
            campaign_id: The campaign the session belongs to.

        Returns:
            HX-Redirect on success, or error redirect.
        """
        fetch_campaign_or_404(campaign_id)

        session_id = request.form.get("session_id", "")
        selected_character_id = request.form.get("selected_character_id", "")

        if not session_id or not selected_character_id:
            flash("Invalid session. Please start a new session.", "error")
            redirect_url = url_for("character_create.selection_page", campaign_id=campaign_id)
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        try:
            new_char = finalize_session(
                user_id=session["user_id"],
                campaign_id=campaign_id,
                session_id=session_id,
                selected_character_id=selected_character_id,
            )
        except APIError:
            logger.exception("Failed to finalize chargen session")
            flash("Failed to finalize character. Please try again.", "error")
            redirect_url = url_for("character_create.selection_page", campaign_id=campaign_id)
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        clear_global_context_cache(session["company_id"], session["user_id"])
        flash("Character created successfully!", "success")
        redirect_url = url_for("character_view.character", character_id=new_char.id)
        return Response("", status=200, headers={"HX-Redirect": redirect_url})


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/multi-autogen/finalize",
    view_func=MultiAutogenFinalizeView.as_view("multi_autogen_finalize"),
    methods=["POST"],
)


class ResumeSessionView(MethodView):
    """Resume a pending multi-autogen chargen session."""

    def get(self, campaign_id: str, session_id: str) -> Response | str:
        """Load a pending session and render the character comparison view.

        Args:
            campaign_id: The campaign the session belongs to.
            session_id: The chargen session to resume.

        Returns:
            Rendered comparison fragment, or redirect on error.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        user = g.requesting_user

        try:
            session_response = get_session(
                user_id=user.id,
                campaign_id=campaign_id,
                session_id=session_id,
            )
        except APIError:
            logger.exception("Failed to resume chargen session %s", session_id)
            flash("This session has expired or is no longer available.", "error")
            redirect_url = url_for("character_create.selection_page", campaign_id=campaign_id)
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        return catalog.render(
            "character_create.partials.MultiAutogenCompare",
            campaign=campaign,
            session_id=session_response.id,
            characters_data=build_characters_data(session_response, user),
            expires_at=session_response.expires_at,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/new/multi-autogen/session/<string:session_id>/resume",
    view_func=ResumeSessionView.as_view("resume_session"),
    methods=["GET"],
)
