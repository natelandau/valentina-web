"""Campaign routes."""

from __future__ import annotations

from flask import Blueprint, Response, abort, g, render_template, request, session, url_for
from flask.views import MethodView
from vclient import sync_campaigns_service
from vclient.models import CampaignCreate, CampaignUpdate

from vweb import catalog
from vweb.lib.api import (
    fetch_campaign_or_404,
    get_campaign_name,
    get_chapter_count_for_campaign,
    get_recent_player_dicerolls,
    get_user_campaign_experience,
    get_visible_characters_for_campaign,
    validate_and_submit_experience,
)
from vweb.lib.global_context import clear_global_context_cache, get_campaign_statistics
from vweb.lib.guards import can_grant_experience, can_manage_campaign
from vweb.lib.jinja import hx_redirect

bp = Blueprint("campaign", __name__)

_NAME_MIN_LEN = 3
_NAME_MAX_LEN = 50
_DESC_MIN_LEN = 3


def _validate_campaign_form(name: str, description: str) -> list[str]:
    """Validate campaign form fields.

    Args:
        name: The campaign name from the form.
        description: The campaign description from the form.

    Returns:
        A list of validation error messages (empty if valid).
    """
    errors: list[str] = []
    if not name or len(name) < _NAME_MIN_LEN:
        errors.append("Name must be at least 3 characters.")
    if len(name) > _NAME_MAX_LEN:
        errors.append("Name must be 50 characters or fewer.")
    if description and len(description) < _DESC_MIN_LEN:
        errors.append("Description must be at least 3 characters if provided.")
    return errors


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

        ctx = g.global_context
        user_id = session["user_id"]
        visible_characters = get_visible_characters_for_campaign(campaign_id)
        user_characters = [c for c in visible_characters if c.user_player_id == user_id]
        other_characters = [c for c in visible_characters if c.user_player_id != user_id]

        books = ctx.books_by_campaign.get(campaign_id, [])
        campaign_experience = get_user_campaign_experience(user_id, campaign_id)
        chapter_count = get_chapter_count_for_campaign(campaign_id)

        # Statistics and Recent Dicerolls are fetched by HTMX-lazy-loaded fragments
        # (see RecentDicerollsCardView / CampaignStatisticsCardView) so the overview
        # paints without waiting on their remote calls.
        return catalog.render(
            "campaign.CampaignDetail",
            campaign=campaign,
            user_characters=user_characters,
            other_characters=other_characters,
            books=books,
            chapter_count=chapter_count,
            campaign_experience=campaign_experience,
            user=g.requesting_user,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>",
    view_func=CampaignView.as_view("campaign"),
    methods=["GET"],
)


class RecentDicerollsCardView(MethodView):
    """Lazy-loaded Recent Dicerolls card for the campaign overview."""

    def get(self, campaign_id: str) -> str:
        """Render the Recent Dicerolls card populated with the latest rolls."""
        fetch_campaign_or_404(campaign_id)
        rolls = get_recent_player_dicerolls(campaign_id)
        return catalog.render(
            "campaign.components.RecentDiceRollsCard",
            rolls=rolls,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/recent-dicerolls",
    view_func=RecentDicerollsCardView.as_view("recent_dicerolls_card"),
    methods=["GET"],
)


class CampaignStatisticsCardView(MethodView):
    """Lazy-loaded campaign statistics card for the campaign overview."""

    def get(self, campaign_id: str) -> str:
        """Render the campaign statistics card with fresh (30s-cached) data."""
        fetch_campaign_or_404(campaign_id)
        statistics = get_campaign_statistics(campaign_id)
        return catalog.render(
            "shared.cards.StatisticsCard",
            statistics=statistics,
            col_span=2,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/statistics",
    view_func=CampaignStatisticsCardView.as_view("statistics_card"),
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

        errors = _validate_campaign_form(name, description)

        if errors:
            return catalog.render(
                "shared.layout.CampaignCreateModalContent",
                errors=errors,
                form_data={"name": name, "description": description},
            )

        service = sync_campaigns_service(
            on_behalf_of=g.requesting_user.id, company_id=session["company_id"]
        )
        new_campaign = service.create(CampaignCreate(name=name, description=description or None))
        clear_global_context_cache(session["company_id"], session["user_id"])

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

        errors = _validate_campaign_form(name, description)
        if errors:
            return catalog.render(
                "shared.layout.CampaignCreateModalContent",
                errors=errors,
                form_data={"name": name, "description": description},
                campaign=campaign,
            )

        service = sync_campaigns_service(
            on_behalf_of=g.requesting_user.id, company_id=session["company_id"]
        )
        service.update(campaign_id, CampaignUpdate(name=name, description=description or None))
        clear_global_context_cache(session["company_id"], session["user_id"])

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

        service = sync_campaigns_service(
            on_behalf_of=g.requesting_user.id, company_id=session["company_id"]
        )
        service.delete(campaign_id)
        clear_global_context_cache(session["company_id"], session["user_id"])
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

        service = sync_campaigns_service(
            on_behalf_of=g.requesting_user.id, company_id=session["company_id"]
        )
        campaign = service.update(campaign_id, update)
        clear_global_context_cache(session["company_id"], session["user_id"])
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
            user_id=user_id,
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
        errors = validate_and_submit_experience(
            form_data, user_id, campaign_id, on_behalf_of=user_id
        )

        if errors:
            return catalog.render(
                "campaign.partials.ExperienceForm",
                user_id=user_id,
                campaign_id=campaign_id,
                campaign_name=get_campaign_name(campaign_id),
                form_data=form_data,
                errors=errors,
            )

        card_url = url_for("campaign.experience_card", campaign_id=campaign_id)
        return render_template(
            "partials/crud_refetch.html",
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
