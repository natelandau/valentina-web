"""Update character trait routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, get_args

from flask import (
    Blueprint,
    flash,
    g,
    make_response,
    redirect,
    request,
    session,
    url_for,
)
from flask.views import MethodView
from vclient import sync_character_traits_service
from vclient.constants import TraitModifyCurrency
from vclient.exceptions import ConflictError, ValidationError
from vclient.models import TraitCreate

from vweb import catalog
from vweb.lib.api import get_character_and_campaign
from vweb.lib.blueprint_cache import get_trait as get_blueprint_trait
from vweb.lib.character_sheet import CharacterSheetService
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_edit_character, can_edit_traits_free

bp = Blueprint("character_trait_edit", __name__)

if TYPE_CHECKING:
    from vclient._sync.services import SyncCharacterTraitsService
    from werkzeug.wrappers.response import Response


class CharacterTraitsView(MethodView):
    """Character traits view."""

    def __init__(self, spend_type: TraitModifyCurrency) -> None:
        self.spend_type = spend_type
        self.spend_type_humanized = spend_type.lower().replace("_", " ")
        self.xp_current: int = 0
        self.xp_total: int = 0

    def _update_trait_value(
        self,
        svc: SyncCharacterTraitsService,
        *,
        trait_id: str,
        value: str,
        get_method_url: str,
    ) -> str:
        """Update a trait value.

        Args:
            svc: The character traits service.
            trait_id: The trait ID.
            value: The value to set the trait to. A string of an integer.
            get_method_url: The URL to redirect to.

        Returns:
            A string to redirect to.
        """
        value_options = svc.get_value_options(trait_id)
        if value not in value_options.options:
            flash(
                f"You don't have the ability to set {value_options.name.strip().title()} to {value}",
                "warning",
            )
            return f'<script>window.location.href="{get_method_url}"</script>'

        requested_option = value_options.options[str(value)]
        direction = requested_option.direction
        point_change = requested_option.point_change
        can_update = (
            requested_option.can_use_xp
            if self.spend_type == "XP"
            else requested_option.can_use_starting_points
            if self.spend_type == "STARTING_POINTS"
            else True
        )

        if not can_update:
            flash(
                f"You don't have enough {self.spend_type_humanized} to set {value_options.name.strip().title()} to {value}. You would need {point_change} more {self.spend_type_humanized}",
                "warning",
            )
            return f'<script>window.location.href="{get_method_url}"</script>'

        svc.change_value(trait_id, int(value), currency=self.spend_type)

        flash(
            f"Updated {value_options.name.strip().title()} to {value}.<br>You {'recouped' if direction == 'decrease' else 'spent'} {point_change} {self.spend_type_humanized}",
            "success",
        )
        return f'<script>window.location.href="{get_method_url}"</script>'

    def _delete_trait(
        self,
        svc: SyncCharacterTraitsService,
        *,
        trait_id: str,
        get_method_url: str,
    ) -> str:
        """Delete a trait.

        Args:
            svc: The character traits service.
            trait_id: The trait ID.
            get_method_url: The URL to redirect to.

        Returns:
            A string to redirect to.
        """
        value_options = svc.get_value_options(trait_id)
        point_change = value_options.options["DELETE"].point_change

        svc.delete(trait_id, currency=self.spend_type)

        msg = "Trait deleted."
        if self.spend_type in ["XP", "STARTING_POINTS"]:
            msg += f"<br>You recouped {point_change} {self.spend_type_humanized}"
        flash(msg, "success")
        return f'<script>window.location.href="{get_method_url}"</script>'

    def get(self, character_id: str) -> str | Response:
        """Get the character traits form."""
        requesting_user = g.requesting_user
        character, campaign = get_character_and_campaign(character_id)

        if not character or not campaign:
            response = make_response("")
            if request.headers.get("HX-Request"):
                response.headers["HX-Redirect"] = url_for("index.index")
            return response

        if self.spend_type == "NO_COST" and not can_edit_traits_free(character):
            flash("You are not authorized to update traits without spending points", "error")
            return redirect(url_for("character_view.character", character_id=character_id))

        if not can_edit_character(character):
            flash("You are not authorized to update this character", "error")
            return redirect(url_for("character_view.character", character_id=character_id))

        if self.spend_type == "XP":
            character_owner = next(
                (u for u in g.global_context.users if u.id == character.user_player_id),
                None,
            )
            if character_owner is None:
                msg = f"Character owner {character.user_player_id} not found"
                flash(msg, "error")
                return redirect(url_for("character_view.character", character_id=character_id))

            campaign_experience = next(
                (
                    c
                    for c in character_owner.campaign_experience
                    if c.campaign_id == character.campaign_id
                ),
                None,
            )
            self.xp_current = campaign_experience.xp_current if campaign_experience else 0
            self.xp_total = campaign_experience.xp_total if campaign_experience else 0

        sheet_svc = CharacterSheetService(character=character, requesting_user=requesting_user)
        full_sheet = sheet_svc.get_full_sheet(include_available_traits=True)

        return catalog.render(
            "character_trait_edit.Main",
            current_spend_type=self.spend_type,
            character=character,
            campaign=campaign,
            xp_current=self.xp_current,
            xp_total=self.xp_total,
            full_sheet=full_sheet,
            post_url=url_for(f"character_trait_edit.{self.spend_type}", character_id=character_id),
        )

    def post(self, character_id: str) -> str | Response:  # noqa: C901, PLR0911
        """Post the character traits form."""
        requesting_user = g.requesting_user
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            if request.headers.get("HX-Request"):
                response = make_response("")
                response.headers["HX-Redirect"] = url_for("index.index")
            return response

        get_method_url = url_for(
            f"character_trait_edit.{self.spend_type}", character_id=character_id
        )

        api_svc = sync_character_traits_service(
            user_id=requesting_user.id,
            campaign_id=campaign.id,
            character_id=character.id,
            company_id=session["company_id"],
        )
        sheet_svc = CharacterSheetService(character=character, requesting_user=requesting_user)
        sheet_svc.clear_cache()
        clear_global_context_cache(session["company_id"], session["user_id"])

        for trait_id, value in request.form.items():
            if value == "DELETE":
                return self._delete_trait(
                    svc=api_svc,
                    trait_id=trait_id,
                    get_method_url=get_method_url,
                )

            if trait_id.startswith("ADD_UNASSIGNED"):
                new_trait_id = value

                trait = get_blueprint_trait(new_trait_id)
                if trait is None:
                    flash("Trait not found", "error")
                    return f'<script>window.location.href="{get_method_url}"</script>'
                try:
                    api_svc.assign(
                        trait_id=new_trait_id, value=trait.min_value, currency=self.spend_type
                    )
                except (ConflictError, ValidationError) as error:
                    flash(error.detail or "Failed to assign trait", "error")
                    return f'<script>window.location.href="{get_method_url}"</script>'

                flash(f"Assigned {trait.name}", "success")
                return f'<script>window.location.href="{get_method_url}"</script>'

            if trait_id.startswith("CUSTOM_"):
                new_trait_name = value.strip().title()
                if not new_trait_name:
                    flash("Trait name is required", "warning")
                    return f'<script>window.location.href="{get_method_url}"</script>'
                custom_trait = TraitCreate(
                    name=new_trait_name,
                    show_when_zero=True,
                    category_id=trait_id.split("_")[1],
                )
                try:
                    api_svc.create(custom_trait)
                except (ConflictError, ValidationError) as error:
                    flash(error.detail or "Failed to create custom trait", "error")
                    return f'<script>window.location.href="{get_method_url}"</script>'

                flash(f"Created {new_trait_name}", "success")
                return f'<script>window.location.href="{get_method_url}"</script>'

            return self._update_trait_value(
                svc=api_svc,
                trait_id=trait_id,
                value=value,
                get_method_url=get_method_url,
            )

        flash("Something went wrong", "error")
        return f'<script>window.location.href="{get_method_url}"</script>'


for spend_type in get_args(TraitModifyCurrency):
    bp.add_url_rule(
        f"/character/<string:character_id>/traits/{spend_type}",
        view_func=CharacterTraitsView.as_view(spend_type, spend_type=spend_type),
        methods=["GET", "POST"],
    )
