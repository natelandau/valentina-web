"""User profile routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    abort,
    g,
    render_template,
    request,
    session,
    url_for,
)
from flask.views import MethodView

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response
from vclient import sync_users_service
from vclient.models.users import UserUpdate

from vweb import catalog
from vweb.lib.api import get_campaign_name, validate_and_submit_experience
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_grant_experience, is_self
from vweb.lib.jinja import hx_redirect
from vweb.routes.profile.views_quickrolls import QuickrollsTableView

bp = Blueprint("profile", __name__)


class ProfileView(MethodView):
    """Display and edit user profiles."""

    def get(self, user_id: str) -> str:
        """Render the user profile page."""
        ctx = g.global_context
        user = next((u for u in ctx.users if u.id == user_id), None)
        if user is None:
            abort(404)

        user_characters = [ch for ch in ctx.characters if ch.user_player_id == user_id]

        # Fetch statistics
        svc = sync_users_service(on_behalf_of=session["user_id"], company_id=session["company_id"])
        statistics = svc.get_statistics(user_id)

        experience_rows, lifetime_xp, lifetime_cool_points = _build_experience_rows(user_id)

        return catalog.render(
            "profile.Profile",
            user=user,
            user_characters=user_characters,
            statistics=statistics,
            lifetime_xp=lifetime_xp,
            lifetime_cool_points=lifetime_cool_points,
            experience_rows=experience_rows,
            character_count=len(user_characters),
        )

    def post(self, user_id: str) -> str | Response:
        """Handle profile edit form submission."""
        if not is_self(user_id):
            abort(403)

        form_data = request.form.to_dict()
        errors: list[str] = []

        # Validate required fields
        if not form_data.get("username", "").strip():
            errors.append("Username is required")
        email = form_data.get("email", "").strip()
        if not email:
            errors.append("Email is required")
        elif "@" not in email:
            errors.append("Email must be a valid email address")

        if errors:
            ctx = g.global_context
            user = next((u for u in ctx.users if u.id == user_id), None)
            if user is None:
                abort(404)
            return catalog.render(
                "profile.partials.ProfileEditForm",
                user=user,
                form_data=form_data,
                errors=errors,
            )

        svc = sync_users_service(on_behalf_of=session["user_id"], company_id=session["company_id"])
        update_request = UserUpdate(
            name_first=form_data.get("name_first", "").strip() or None,
            name_last=form_data.get("name_last", "").strip() or None,
            username=form_data["username"].strip(),
            email=form_data["email"].strip(),
        )
        svc.update(user_id, request=update_request)
        clear_global_context_cache(session["company_id"], session["user_id"])

        return hx_redirect(url_for("profile.profile", user_id=user_id))


def _build_experience_rows(user_id: str) -> tuple[list[dict], int, int]:
    """Build experience table data from global context.

    Returns:
        Tuple of (experience_rows, lifetime_xp, lifetime_cool_points).
    """
    ctx = g.global_context
    user = next((u for u in ctx.users if u.id == user_id), None)
    if user is None:
        abort(404)

    campaign_map = {c.id: c.name for c in ctx.campaigns}
    experience_rows = [
        {
            "campaign_id": ce.campaign_id,
            "campaign_name": campaign_map.get(ce.campaign_id, "Unknown"),
            "xp_current": ce.xp_current,
            "xp_total": ce.xp_total,
            "cool_points": ce.cool_points,
        }
        for ce in user.campaign_experience
    ]
    lifetime_xp = sum(ce.xp_total for ce in user.campaign_experience)
    lifetime_cool_points = sum(ce.cool_points for ce in user.campaign_experience)
    return experience_rows, lifetime_xp, lifetime_cool_points


class ExperienceCardView(MethodView):
    """Render the full experience card fragment."""

    def get(self, user_id: str) -> str:
        """Return the experience card HTML fragment with updated lifetime stats."""
        experience_rows, lifetime_xp, lifetime_cool_points = _build_experience_rows(user_id)

        return catalog.render(
            "profile.components.ExperienceCard",
            user_id=user_id,
            lifetime_xp=lifetime_xp,
            lifetime_cool_points=lifetime_cool_points,
            experience_rows=experience_rows,
        )


class ExperienceFormView(MethodView):
    """Serve the experience add form fragment."""

    def get(self, user_id: str, campaign_id: str) -> str:
        """Return the experience form HTML fragment."""
        if not can_grant_experience(user_id):
            abort(403)
        return catalog.render(
            "profile.partials.ExperienceForm",
            user_id=user_id,
            campaign_id=campaign_id,
            campaign_name=get_campaign_name(campaign_id),
        )


class AddExperienceView(MethodView):
    """Handle experience form submission."""

    def post(self, user_id: str, campaign_id: str) -> str | Response:
        """Award XP and/or cool points for a campaign."""
        if not can_grant_experience(user_id):
            abort(403)
        form_data = request.form.to_dict()
        errors = validate_and_submit_experience(
            form_data, user_id, campaign_id, on_behalf_of=session["user_id"]
        )

        if errors:
            return catalog.render(
                "profile.partials.ExperienceForm",
                user_id=user_id,
                campaign_id=campaign_id,
                campaign_name=get_campaign_name(campaign_id),
                form_data=form_data,
                errors=errors,
            )

        card_url = url_for("profile.experience_card", user_id=user_id)
        return render_template(
            "partials/crud_refetch.html",
            table_url=card_url,
            table_target_id="experience-card",
        )


class EditProfileView(MethodView):
    """Serve the profile edit form fragment."""

    def get(self, user_id: str) -> str:
        """Return the edit form HTML fragment."""
        if not is_self(user_id):
            abort(403)

        ctx = g.global_context
        user = next((u for u in ctx.users if u.id == user_id), None)
        if user is None:
            abort(404)

        return catalog.render("profile.partials.ProfileEditForm", user=user)


bp.add_url_rule(
    "/profile/<string:user_id>",
    view_func=ProfileView.as_view("profile"),
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/profile/<string:user_id>/experience",
    view_func=ExperienceCardView.as_view("experience_card"),
)
bp.add_url_rule(
    "/profile/<string:user_id>/experience/<string:campaign_id>/form",
    view_func=ExperienceFormView.as_view("experience_form"),
)
bp.add_url_rule(
    "/profile/<string:user_id>/experience/<string:campaign_id>",
    view_func=AddExperienceView.as_view("add_experience"),
    methods=["POST"],
)
bp.add_url_rule("/profile/<string:user_id>/edit", view_func=EditProfileView.as_view("edit_profile"))

_quickrolls_view = QuickrollsTableView.as_view("quickrolls")
bp.add_url_rule(
    "/profile/<string:user_id>/quickrolls",
    defaults={"item_id": None},
    view_func=_quickrolls_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/profile/<string:user_id>/quickrolls/<string:item_id>",
    view_func=_quickrolls_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/profile/<string:user_id>/quickrolls/form",
    defaults={"item_id": None},
    view_func=QuickrollsTableView.as_view("quickrolls_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/profile/<string:user_id>/quickrolls/form/<string:item_id>",
    view_func=QuickrollsTableView.as_view("quickrolls_form_edit"),
    methods=["GET"],
)
