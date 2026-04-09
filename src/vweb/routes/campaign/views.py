"""Campaign routes."""

from flask import Blueprint, Response, abort, g, request, session, url_for
from flask.views import MethodView
from vclient import sync_campaigns_service
from vclient.models import CampaignCreate, CampaignUpdate

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404, get_user_campaign_experience
from vweb.lib.global_context import clear_global_context_cache, get_campaign_statistics
from vweb.lib.guards import can_manage_campaign, is_storyteller

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
        all_characters = ctx.characters_by_campaign.get(campaign_id, [])

        privileged = is_storyteller()
        user_characters: list = []
        other_characters: list = []
        for char in sorted(all_characters, key=lambda c: c.name):
            is_visible = char.type == "PLAYER" or (privileged and char.type == "STORYTELLER")
            if not is_visible:
                continue
            if char.user_player_id == user_id:
                user_characters.append(char)
            else:
                other_characters.append(char)

        books = ctx.books_by_campaign.get(campaign_id, [])
        campaign_statistics = get_campaign_statistics(campaign_id)
        campaign_experience = get_user_campaign_experience(user_id, campaign_id)

        return catalog.render(
            "index.Index",
            campaign=campaign,
            user_characters=user_characters,
            other_characters=other_characters,
            books=books,
            campaign_statistics=campaign_statistics,
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

        errors = _validate_campaign_form(name, description)

        if errors:
            return catalog.render(
                "shared.layout.CampaignCreateModalContent",
                errors=errors,
                form_data={"name": name, "description": description},
            )

        service = sync_campaigns_service(
            user_id=g.requesting_user.id, company_id=session["company_id"]
        )
        new_campaign = service.create(CampaignCreate(name=name, description=description or None))
        clear_global_context_cache(session["company_id"], session["user_id"])

        redirect_url = url_for("campaign.campaign", campaign_id=new_campaign.id)
        return Response("", status=200, headers={"HX-Redirect": redirect_url})


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
            user_id=g.requesting_user.id, company_id=session["company_id"]
        )
        service.update(campaign_id, CampaignUpdate(name=name, description=description or None))
        clear_global_context_cache(session["company_id"], session["user_id"])

        redirect_url = url_for("campaign.campaign", campaign_id=campaign_id)
        return Response("", status=200, headers={"HX-Redirect": redirect_url})


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
            user_id=g.requesting_user.id, company_id=session["company_id"]
        )
        service.delete(campaign_id)
        clear_global_context_cache(session["company_id"], session["user_id"])
        session.pop("last_campaign_id", None)

        return Response("", status=200, headers={"HX-Redirect": "/"})


bp.add_url_rule(
    "/campaign/<string:campaign_id>",
    view_func=CampaignDeleteView.as_view("delete"),
    methods=["DELETE"],
)
