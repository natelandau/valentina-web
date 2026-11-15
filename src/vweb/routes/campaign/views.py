"""Campaign routes."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, abort, g, request, session, url_for
from flask.views import MethodView

from vweb.api_client.models import CampaignCreate, CampaignUpdate
from vweb.lib import api_services, cache
from vweb.lib.api import (
    fetch_campaign_or_404,
    get_campaign_name,
    get_user_campaign_experience,
    validate_and_submit_experience,
)
from vweb.lib.api_errors import USER_FACING_API_ERRORS, api_error_message
from vweb.lib.catalog import catalog
from vweb.lib.form_validation import CAMPAIGN_NAME_MIN_LENGTH, name_errors
from vweb.lib.guards import can_grant_experience, can_manage_campaign
from vweb.lib.htmx import hx_redirect

bp = Blueprint("campaign", __name__)

def _parse_in_game_date(value: str) -> date | None:
    """Parse the campaign's in-game date from a date input.

    Args:
        value: The submitted ``YYYY-MM-DD`` text, or blank.

    Returns:
        The date, or None when blank or not a valid calendar date.
    """
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _in_game_date_errors(value: str) -> list[str]:
    """Return the error for an in-game date that is not a valid calendar date."""
    if value and _parse_in_game_date(value) is None:
        return ["In-game date must be a valid date."]
    return []



class CampaignView(MethodView):
    """Campaign dashboard page."""

    def get(self, campaign_id: str) -> str:
        """Render the campaign dashboard for the given campaign.

        Args:
            campaign_id: The unique identifier of the campaign to display.

        Returns:
            Rendered HTML for the campaign dashboard.
        """
        campaign = fetch_campaign_or_404(campaign_id)

        session["last_campaign_id"] = campaign_id

        user_id = session["user_id"]
        campaign_experience = get_user_campaign_experience(user_id, campaign_id)

        return catalog.render(
            "campaign.CampaignDetail",
            campaign=campaign,
            campaign_experience=campaign_experience,
            user=g.requesting_user,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>",
    view_func=CampaignView.as_view("campaign"),
    methods=["GET"],
)


class CampaignEditFormView(MethodView):
    """Return the pre-filled campaign edit form for the modal."""

    def get(self, campaign_id: str) -> str:
        """Render the campaign edit form with current values.

        Args:
            campaign_id: The campaign to edit.

        Returns:
            Rendered HTML for the edit modal content.
        """
        if not can_manage_campaign():
            abort(403)

        campaign = fetch_campaign_or_404(campaign_id)

        return catalog.render(
            "shared.layout.CampaignCreateModalContent",
            campaign=campaign,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/edit-form",
    view_func=CampaignEditFormView.as_view("edit_form"),
    methods=["GET"],
)


class CampaignCreateView(MethodView):
    """Handle campaign creation."""

    def post(self) -> Response | str:
        """Create a new campaign and redirect to it.

        Returns:
            An HX-Redirect response on success, or re-rendered form content with errors.
        """
        if not can_manage_campaign():
            abort(403)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        in_game_date = request.form.get("in_game_date", "").strip()

        errors = name_errors(name, min_length=CAMPAIGN_NAME_MIN_LENGTH)
        errors += _in_game_date_errors(in_game_date)
        if not errors:
            try:
                new_campaign = api_services.campaigns().create(
                    CampaignCreate(
                        name=name,
                        description=description or None,
                        in_game_date=_parse_in_game_date(in_game_date),
                    )
                )
            except USER_FACING_API_ERRORS as error:
                errors = [api_error_message(error, fallback="Could not create the campaign")]
        if errors:
            return catalog.render(
                "shared.layout.CampaignCreateModalContent",
                errors=errors,
                form_data={
                    "name": name,
                    "description": description,
                    "in_game_date": in_game_date,
                },
            )

        cache.global_context.clear_current()

        return hx_redirect(url_for("campaign.campaign", campaign_id=new_campaign.id))


bp.add_url_rule(
    "/campaign/create",
    view_func=CampaignCreateView.as_view("create"),
    methods=["POST"],
)


class CampaignUpdateView(MethodView):
    """Handle campaign updates."""

    def post(self, campaign_id: str) -> Response | str:
        """Update an existing campaign.

        Args:
            campaign_id: The campaign to update.

        Returns:
            An HX-Redirect response on success, or re-rendered form content with errors.
        """
        if not can_manage_campaign():
            abort(403)

        campaign = fetch_campaign_or_404(campaign_id)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        in_game_date = request.form.get("in_game_date", "").strip()

        errors = name_errors(name, min_length=CAMPAIGN_NAME_MIN_LENGTH)
        errors += _in_game_date_errors(in_game_date)
        if not errors:
            try:
                api_services.campaigns().update(
                    # An empty description is sent as-is so the API clears it
                    campaign_id,
                    CampaignUpdate(
                        name=name,
                        description=description,
                        in_game_date=_parse_in_game_date(in_game_date),
                    ),
                )
            except USER_FACING_API_ERRORS as error:
                errors = [api_error_message(error, fallback="Could not save the campaign")]
        if errors:
            return catalog.render(
                "shared.layout.CampaignCreateModalContent",
                errors=errors,
                form_data={
                    "name": name,
                    "description": description,
                    "in_game_date": in_game_date,
                },
                campaign=campaign,
            )

        cache.global_context.clear_current()

        return hx_redirect(url_for("campaign.campaign", campaign_id=campaign_id))


bp.add_url_rule(
    "/campaign/<string:campaign_id>/update",
    view_func=CampaignUpdateView.as_view("update"),
    methods=["POST"],
)


class CampaignDeleteView(MethodView):
    """Handle campaign deletion."""

    def delete(self, campaign_id: str) -> Response:
        """Delete a campaign and redirect to home.

        Args:
            campaign_id: The campaign to delete.

        Returns:
            An HX-Redirect response to the home page.
        """
        if not can_manage_campaign():
            abort(403)

        fetch_campaign_or_404(campaign_id)

        service = api_services.campaigns()
        service.delete(campaign_id)
        cache.global_context.clear_current()
        session.pop("last_campaign_id", None)

        return hx_redirect("/")


bp.add_url_rule(
    "/campaign/<string:campaign_id>",
    view_func=CampaignDeleteView.as_view("delete"),
    methods=["DELETE"],
)

_DANGER_DESPERATION_MIN = 0
_DANGER_DESPERATION_MAX = 5


class CampaignUpdateDangerDesperationView(MethodView):
    """Handle inline danger/desperation badge updates."""

    def post(self, campaign_id: str, field: str) -> str:
        """Update a campaign's danger or desperation value.

        Args:
            campaign_id: The campaign to update.
            field: Either ``"danger"`` or ``"desperation"``.

        Returns:
            Re-rendered badge partial HTML.
        """
        if not can_manage_campaign():
            abort(403)

        if field not in ("danger", "desperation"):
            abort(400)

        raw_value = request.form.get("value", "")
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            abort(400)

        if not _DANGER_DESPERATION_MIN <= value <= _DANGER_DESPERATION_MAX:
            abort(400)

        if field == "danger":
            update = CampaignUpdate(danger=value)
        else:
            update = CampaignUpdate(desperation=value)

        service = api_services.campaigns()
        campaign = service.update(campaign_id, update)
        cache.global_context.clear_current()
        return catalog.render(
            "campaign.partials.DangerDesperation",
            campaign=campaign,
            vertical=True,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/update/<string:field>",
    view_func=CampaignUpdateDangerDesperationView.as_view("update_danger_desperation"),
    methods=["POST"],
)


class CampaignExperienceCardView(MethodView):
    """Render the experience card fragment for a campaign."""

    def get(self, campaign_id: str) -> str:
        """Return the experience card HTML fragment with updated values."""
        user = g.requesting_user
        campaign_experience = get_user_campaign_experience(user.id, campaign_id)

        return catalog.render(
            "campaign.components.ExperienceCard",
            user=user,
            campaign_id=campaign_id,
            campaign_experience=campaign_experience,
        )


class CampaignExperienceFormView(MethodView):
    """Serve the experience form fragment for a campaign."""

    def get(self, campaign_id: str) -> str:
        """Return the experience form HTML fragment."""
        user_id = g.requesting_user.id
        if not can_grant_experience(user_id):
            abort(403)
        return catalog.render(
            "campaign.partials.ExperienceForm",
            campaign_id=campaign_id,
            campaign_name=get_campaign_name(campaign_id),
        )


class CampaignAddExperienceView(MethodView):
    """Handle experience form submission for a campaign."""

    def post(self, campaign_id: str) -> str | Response:
        """Award XP and/or cool points for a campaign."""
        user_id = session["user_id"]
        if not can_grant_experience(user_id):
            abort(403)
        form_data = request.form.to_dict()
        errors = validate_and_submit_experience(form_data, user_id, campaign_id)

        if errors:
            return catalog.render(
                "campaign.partials.ExperienceForm",
                campaign_id=campaign_id,
                campaign_name=get_campaign_name(campaign_id),
                form_data=form_data,
                errors=errors,
            )

        card_url = url_for("campaign.experience_card", campaign_id=campaign_id)
        return catalog.render(
            "shared.crud.Refetch",
            table_url=card_url,
            table_target_id="index-experience-card",
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/experience",
    view_func=CampaignExperienceCardView.as_view("experience_card"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/experience/form",
    view_func=CampaignExperienceFormView.as_view("experience_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<string:campaign_id>/experience",
    view_func=CampaignAddExperienceView.as_view("add_experience"),
    methods=["POST"],
)
