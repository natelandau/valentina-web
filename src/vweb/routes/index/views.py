"""Main application routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    Response,
    abort,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import (
    get_active_campaign,
    get_campaign_name,
    get_user_campaign_experience,
    validate_and_submit_experience,
)
from vweb.lib.guards import can_grant_experience

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
            return catalog.render("index.Index", campaign=None)

        return redirect(url_for("campaign.campaign", campaign_id=selected.id))


class IndexExperienceCardView(MethodView):
    """Render the index experience card fragment."""

    def get(self, campaign_id: str) -> str:
        """Return the experience card HTML fragment with updated values."""
        user = g.requesting_user
        campaign_experience = get_user_campaign_experience(user.id, campaign_id)

        return catalog.render(
            "index.components.ExperienceCard",
            user=user,
            campaign_id=campaign_id,
            campaign_experience=campaign_experience,
        )


class IndexExperienceFormView(MethodView):
    """Serve the index experience form fragment."""

    def get(self, campaign_id: str) -> str:
        """Return the experience form HTML fragment."""
        user_id = g.requesting_user.id
        if not can_grant_experience(user_id):
            abort(403)
        return catalog.render(
            "index.partials.ExperienceForm",
            user_id=user_id,
            campaign_id=campaign_id,
            campaign_name=get_campaign_name(campaign_id),
        )


class IndexAddExperienceView(MethodView):
    """Handle experience form submission from the index page."""

    def post(self, campaign_id: str) -> str | Response:
        """Award XP and/or cool points for a campaign."""
        user_id = session["user_id"]
        if not can_grant_experience(user_id):
            abort(403)
        form_data = request.form.to_dict()
        errors = validate_and_submit_experience(
            form_data, user_id, campaign_id, on_behalf_of=user_id
        )

        if errors:
            return catalog.render(
                "index.partials.ExperienceForm",
                user_id=user_id,
                campaign_id=campaign_id,
                campaign_name=get_campaign_name(campaign_id),
                form_data=form_data,
                errors=errors,
            )

        card_url = url_for("index.experience_card", campaign_id=campaign_id)
        return render_template(
            "partials/crud_refetch.html",
            table_url=card_url,
            table_target_id="index-experience-card",
        )


bp.add_url_rule("/", view_func=IndexView.as_view("index"))
bp.add_url_rule(
    "/experience/<string:campaign_id>",
    view_func=IndexExperienceCardView.as_view("experience_card"),
)
bp.add_url_rule(
    "/experience/<string:campaign_id>/form",
    view_func=IndexExperienceFormView.as_view("experience_form"),
)
bp.add_url_rule(
    "/experience/<string:campaign_id>",
    view_func=IndexAddExperienceView.as_view("add_experience"),
    methods=["POST"],
)
