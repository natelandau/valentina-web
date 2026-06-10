"""Manual character creation routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import flash, g, request, session, url_for
from flask.views import MethodView
from vclient.exceptions import APIError

from vweb.lib import cache
from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.catalog import catalog
from vweb.lib.guards import can_edit_character
from vweb.lib.htmx import hx_redirect
from vweb.routes.character_create import bp
from vweb.routes.character_create.autogen_services import fetch_form_options
from vweb.routes.character_create.manual_services import (
    build_trait_items,
    bulk_assign_traits,
    character_type_permission_error,
    clear_temp_session,
    fetch_character,
    load_temp_character_form_data,
    mark_character_permanent,
    save_temp_character,
    update_character_profile,
)
from vweb.routes.character_create.profile_form import character_to_form_data, validate_profile

if TYPE_CHECKING:
    from vclient.models import Campaign
    from werkzeug.wrappers.response import Response

logger = logging.getLogger(__name__)


class ManualProfileView(MethodView):
    """Render the manual creation profile form (step 1)."""

    def get(self, campaign_id: str) -> str:
        """Render the profile form for create or edit mode.

        Create mode (no character_id param): checks for temp_character_id in session.
        Edit mode (character_id param): pre-fills from the existing character.

        Args:
            campaign_id: The campaign ID.

        Returns:
            Rendered HTML for the profile form page or fragment.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        form_options = fetch_form_options()

        character_id = request.args.get("character_id")

        if character_id:
            character = fetch_character(character_id)
            form_data = character_to_form_data(character)
            mode = "edit"
        else:
            mode = "create"
            character_id = ""
            form_data = load_temp_character_form_data(
                is_resuming=request.args.get("resume") == "1",
                fallback=dict(request.args),
            )

        render_kwargs = {
            "campaign": campaign,
            "form_options": form_options,
            "form_data": form_data,
            "mode": mode,
            "character_id": character_id,
        }

        if request.headers.get("HX-Request"):
            return catalog.render(
                "character_create.manual.partials.ProfileForm",
                **render_kwargs,  # ty:ignore[invalid-argument-type]
            )

        return catalog.render(
            "character_create.manual.Main",
            **render_kwargs,  # ty:ignore[invalid-argument-type]
        )

    def post(self, campaign_id: str) -> str | Response:
        """Handle profile form submission for both create and edit modes.

        Args:
            campaign_id: The campaign ID.

        Returns:
            Rendered HTML fragment or HX-Redirect response.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        character_id = request.args.get("character_id")
        form_data = {k: v.strip() for k, v in request.form.items() if k != "csrf_token"}

        if character_id:
            return self._post_edit(campaign, character_id, form_data)

        return self._post_create(campaign, form_data)

    def _render_edit_form(
        self,
        campaign: Campaign,
        character_id: str,
        form_data: dict[str, str],
        errors: dict[str, str],
    ) -> str:
        """Render the profile form in edit mode with errors.

        Args:
            campaign: The campaign object.
            character_id: The character being edited.
            form_data: Form data to re-populate.
            errors: Validation or API errors keyed by field name.

        Returns:
            Rendered ProfileForm HTML.
        """
        return catalog.render(
            "character_create.manual.partials.ProfileForm",
            campaign=campaign,
            form_options=fetch_form_options(),
            form_data=form_data,
            errors=errors,
            mode="edit",
            character_id=character_id,
        )

    def _post_edit(
        self,
        campaign: Campaign,
        character_id: str,
        form_data: dict[str, str],
    ) -> str | Response:
        """Handle edit mode POST: validate, update character, redirect.

        Args:
            campaign: The campaign object.
            character_id: The character being edited.
            form_data: Stripped form data.

        Returns:
            Rendered form with errors or HX-Redirect on success.
        """
        try:
            character = fetch_character(character_id)
        except APIError as exc:
            errors = {"_general": exc.detail or exc.message or "Failed to load character"}
            return self._render_edit_form(campaign, character_id, form_data, errors)
        if not can_edit_character(character):
            flash("You are not authorized to edit this character", "error")
            return hx_redirect(url_for("character_view.character", character_id=character_id))

        errors = validate_profile(form_data)
        if errors:
            return self._render_edit_form(campaign, character_id, form_data, errors)

        type_error = character_type_permission_error(form_data.get("character_type") or "PLAYER")
        if type_error:
            return self._render_edit_form(
                campaign, character_id, form_data, {"character_type": type_error}
            )

        errors = update_character_profile(character_id, form_data)
        if errors:
            return self._render_edit_form(campaign, character_id, form_data, errors)

        cache.global_context.clear_current()
        flash("Profile updated successfully", "success")
        return hx_redirect(url_for("character_view.character", character_id=character_id))

    def _render_create_form(
        self,
        campaign: Campaign,
        form_data: dict[str, str],
        errors: dict[str, str],
    ) -> str:
        """Render the profile form in create mode with errors.

        Centralizes the repeated catalog.render call so all error paths in
        _post_create stay DRY and automatically pick up the latest form_options.

        Args:
            campaign: The campaign object.
            form_data: Form data to re-populate.
            errors: Validation or API errors keyed by field name.

        Returns:
            Rendered ProfileForm HTML in create mode.
        """
        return catalog.render(
            "character_create.manual.partials.ProfileForm",
            campaign=campaign,
            form_options=fetch_form_options(),
            form_data=form_data,
            errors=errors,
        )

    def _post_create(
        self,
        campaign: Campaign,
        form_data: dict[str, str],
    ) -> str:
        """Handle create mode POST: validate, create/update temp character, return traits form.

        Args:
            campaign: The campaign object.
            form_data: Stripped form data.

        Returns:
            Rendered HTML fragment (profile form on error, traits form on success).
        """
        errors = validate_profile(form_data)
        if errors:
            return self._render_create_form(campaign, form_data, errors)

        type_error = character_type_permission_error(form_data.get("character_type") or "PLAYER")
        if type_error:
            return self._render_create_form(campaign, form_data, {"character_type": type_error})

        errors = save_temp_character(campaign.id, form_data)
        if errors:
            return self._render_create_form(campaign, form_data, errors)

        character = fetch_character(session["temp_character_id"])
        full_sheet = cache.character_sheet.get(
            character.id, g.requesting_user.id, include_available_traits=True
        )

        back_url = url_for("character_create.manual_profile", campaign_id=campaign.id, resume="1")
        return catalog.render(
            "character_create.manual.partials.TraitsForm",
            campaign=campaign,
            full_sheet=full_sheet,
            back_url=back_url,
        )


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/profile_edit",
    view_func=ManualProfileView.as_view("manual_profile"),
    methods=["GET", "POST"],
)


class ManualTraitsView(MethodView):
    """Receive profile data and render the trait value form (step 2)."""

    def post(self, campaign_id: str) -> str:  # noqa: ARG002
        """Placeholder for traits form submission.

        Args:
            campaign_id: The campaign to create a character in.

        Returns:
            Minimal placeholder response.
        """
        return "<p>Traits form submission - coming soon</p>"


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/profile_edit/traits",
    view_func=ManualTraitsView.as_view("manual_traits"),
    methods=["POST"],
)


class ManualFinalizeView(MethodView):
    """Bulk-assign traits to the temporary character and finalize it."""

    def post(self, campaign_id: str) -> Response | str:
        """Assign selected traits via bulk assign, mark character as non-temporary.

        Args:
            campaign_id: The campaign the character belongs to.

        Returns:
            HX-Redirect on success, or re-rendered traits form on error.
        """
        campaign = fetch_campaign_or_404(campaign_id)
        temp_char_id = session.get("temp_character_id")

        if not temp_char_id:
            flash("No character in progress.", "error")
            return hx_redirect(url_for("character_create.manual_profile", campaign_id=campaign_id))

        trait_items = build_trait_items(request.form)

        try:
            failed_names = bulk_assign_traits(temp_char_id, trait_items)
            if failed_names:
                flash(f"Some traits failed to assign: {', '.join(failed_names)}", "warning")

            mark_character_permanent(temp_char_id)
        except APIError as exc:
            logger.exception("Failed to finalize character")
            flash(str(exc), "error")

            character = fetch_character(temp_char_id)
            full_sheet = cache.character_sheet.get(
                character.id, g.requesting_user.id, include_available_traits=True
            )
            back_url = url_for(
                "character_create.manual_profile", campaign_id=campaign_id, resume="1"
            )

            return catalog.render(
                "character_create.manual.partials.TraitsForm",
                campaign=campaign,
                full_sheet=full_sheet,
                back_url=back_url,
                errors=[str(exc)],
            )

        clear_temp_session()
        cache.global_context.clear_current()
        flash("Character created successfully!", "success")
        return hx_redirect(url_for("character_view.character", character_id=temp_char_id))


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/profile_edit/create",
    view_func=ManualFinalizeView.as_view("manual_finalize"),
    methods=["POST"],
)
