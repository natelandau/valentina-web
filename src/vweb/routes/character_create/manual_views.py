"""Manual character creation routes."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, cast

from flask import Response, flash, g, request, session, url_for
from flask.views import MethodView
from pydantic import ValidationError as PydanticValidationError
from vclient import sync_character_traits_service, sync_characters_service
from vclient.exceptions import APIError, ValidationError
from vclient.models import CharacterCreate, CharacterTraitAdd, CharacterUpdate

from vweb import catalog
from vweb.lib.api import fetch_campaign_or_404
from vweb.lib.character_sheet import CharacterSheetService
from vweb.lib.global_context import clear_global_context_cache
from vweb.routes.character_create import bp
from vweb.routes.character_create.autogen_services import fetch_form_options
from vweb.routes.character_create.profile import (
    build_class_attrs,
    character_to_form_data,
    validate_profile,
)

if TYPE_CHECKING:
    from vclient.constants import CharacterClass, CharacterType, GameVersion
    from vclient.models import Campaign

logger = logging.getLogger(__name__)


_TRAIT_PREFIX: str = "trait:"
_SESSION_TTL_SECONDS: int = 30 * 60  # 30 minutes


def _clear_temp_session() -> None:
    """Remove temporary character creation data from the session."""
    session.pop("temp_character_id", None)
    session.pop("temp_character_created_at", None)


def _is_temp_session_expired() -> bool:
    """Check whether the temporary character session data has exceeded its TTL."""
    created_at = session.get("temp_character_created_at")
    if created_at is None:
        return False
    return (time.monotonic() - created_at) > _SESSION_TTL_SECONDS


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
            svc = sync_characters_service(user_id=session["user_id"], campaign_id=campaign_id)
            character = svc.get(character_id)
            form_data = character_to_form_data(character)
            mode = "edit"
        else:
            mode = "create"
            character_id = ""

            is_resuming = request.args.get("resume") == "1"
            if not is_resuming or _is_temp_session_expired():
                _clear_temp_session()

            temp_char_id = session.get("temp_character_id")
            if temp_char_id:
                try:
                    svc = sync_characters_service(
                        user_id=session["user_id"], campaign_id=campaign_id
                    )
                    character = svc.get(temp_char_id)
                    form_data = character_to_form_data(character)
                except APIError:
                    logger.warning("Failed to fetch temp character %s", temp_char_id)
                    _clear_temp_session()
                    form_data = dict(request.args)
            else:
                form_data = dict(request.args)

        render_kwargs = {
            "campaign": campaign,
            "form_options": form_options,
            "form_data": form_data,
            "mode": mode,
            "character_id": character_id,
        }

        if request.headers.get("HX-Request"):
            return catalog.render(
                "character_manual_create.partials.ProfileForm",
                **render_kwargs,  # ty:ignore[invalid-argument-type]
            )

        return catalog.render(
            "character_manual_create.Main",
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
            "character_manual_create.partials.ProfileForm",
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
        errors = validate_profile(form_data)
        if errors:
            return self._render_edit_form(campaign, character_id, form_data, errors)

        character_class = cast("CharacterClass", form_data["character_class"])
        game_version = cast("GameVersion", form_data["game_version"])
        age_str = form_data.get("age", "").strip()

        _create_attrs, update_attrs = build_class_attrs(character_class, form_data)
        vampire_u, werewolf_u, hunter_u, mage_attrs = update_attrs

        char_type = cast("CharacterType", form_data.get("character_type") or "PLAYER")

        svc = sync_characters_service(user_id=session["user_id"], campaign_id=campaign.id)
        try:
            update_payload = CharacterUpdate(
                character_class=character_class,
                game_version=game_version,
                name_first=form_data["name_first"],
                name_last=form_data["name_last"],
                type=char_type,
                name_nick=form_data.get("name_nick") or None,
                age=int(age_str) if age_str else None,
                biography=form_data.get("biography") or None,
                demeanor=form_data.get("demeanor") or None,
                nature=form_data.get("nature") or None,
                concept_id=form_data.get("concept_id") or None,
                vampire_attributes=vampire_u,
                werewolf_attributes=werewolf_u,
                hunter_attributes=hunter_u,
                mage_attributes=mage_attrs,
            )
            svc.update(character_id, update_payload)
        except PydanticValidationError as e:
            errors = {}
            for err in e.errors():
                field_name = str(err["loc"][0]) if err["loc"] else "unknown"
                errors[field_name] = err["msg"]
            return self._render_edit_form(campaign, character_id, form_data, errors)
        except ValidationError as e:
            errors = {p["field"]: p["message"] for p in e.invalid_parameters}
            if e.detail:
                errors["_general"] = e.detail
            return self._render_edit_form(campaign, character_id, form_data, errors)
        except APIError as e:
            errors = {"_general": e.detail or e.message or "Failed to update profile"}
            return self._render_edit_form(campaign, character_id, form_data, errors)

        clear_global_context_cache(session["company_id"], session["user_id"])
        flash("Profile updated successfully", "success")
        return Response(
            "",
            status=200,
            headers={"HX-Redirect": url_for("character_view.character", character_id=character_id)},
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
        campaign_id = campaign.id
        errors = validate_profile(form_data)
        if errors:
            form_options = fetch_form_options()
            return catalog.render(
                "character_manual_create.partials.ProfileForm",
                campaign=campaign,
                form_options=form_options,
                form_data=form_data,
                errors=errors,
            )

        character_class = cast("CharacterClass", form_data["character_class"])
        game_version = cast("GameVersion", form_data["game_version"])
        age_str = form_data.get("age", "").strip()

        create_attrs, update_attrs = build_class_attrs(character_class, form_data)
        vampire_c, werewolf_c, hunter_c, mage_attrs = create_attrs
        vampire_u, werewolf_u, hunter_u, _ = update_attrs

        char_type = cast("CharacterType", form_data.get("character_type") or "PLAYER")
        name_nick = form_data.get("name_nick") or None
        age = int(age_str) if age_str else None
        biography = form_data.get("biography") or None
        demeanor = form_data.get("demeanor") or None
        nature = form_data.get("nature") or None
        concept_id = form_data.get("concept_id") or None

        svc = sync_characters_service(user_id=session["user_id"], campaign_id=campaign_id)
        temp_char_id = session.get("temp_character_id")

        try:
            if temp_char_id:
                update_payload = CharacterUpdate(
                    character_class=character_class,
                    game_version=game_version,
                    name_first=form_data["name_first"],
                    name_last=form_data["name_last"],
                    type=char_type,
                    name_nick=name_nick,
                    age=age,
                    biography=biography,
                    demeanor=demeanor,
                    nature=nature,
                    concept_id=concept_id,
                    vampire_attributes=vampire_u,
                    werewolf_attributes=werewolf_u,
                    hunter_attributes=hunter_u,
                    mage_attributes=mage_attrs,
                )
                svc.update(temp_char_id, update_payload)
            else:
                create_payload = CharacterCreate(
                    character_class=character_class,
                    game_version=game_version,
                    name_first=form_data["name_first"],
                    name_last=form_data["name_last"],
                    type=char_type,
                    name_nick=name_nick,
                    age=age,
                    biography=biography,
                    demeanor=demeanor,
                    nature=nature,
                    concept_id=concept_id,
                    is_temporary=True,
                    user_player_id=session["user_id"],
                    vampire_attributes=vampire_c,
                    werewolf_attributes=werewolf_c,
                    hunter_attributes=hunter_c,
                    mage_attributes=mage_attrs,
                )
                new_char = svc.create(create_payload)
                session["temp_character_id"] = new_char.id
                session["temp_character_created_at"] = time.monotonic()
        except APIError as exc:
            logger.exception("Failed to save temporary character")
            flash(str(exc), "error")
            form_options = fetch_form_options()
            return catalog.render(
                "character_manual_create.partials.ProfileForm",
                campaign=campaign,
                form_options=form_options,
                form_data=form_data,
            )

        char_id = temp_char_id or session["temp_character_id"]
        character = svc.get(char_id)
        sheet_svc = CharacterSheetService(character=character, requesting_user=g.requesting_user)
        full_sheet = sheet_svc.get_full_sheet(include_available_traits=True)

        back_url = url_for("character_create.manual_profile", campaign_id=campaign_id, resume="1")
        return catalog.render(
            "character_manual_create.partials.TraitsForm",
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
        return "<p>Traits form submission — coming soon</p>"


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
            return Response(
                "",
                status=200,
                headers={
                    "HX-Redirect": url_for(
                        "character_create.manual_profile", campaign_id=campaign_id
                    )
                },
            )

        trait_items: list[CharacterTraitAdd] = []
        for key, value in request.form.items():
            if not key.startswith(_TRAIT_PREFIX):
                continue
            trait_id = key[len(_TRAIT_PREFIX) :]
            try:
                int_val = int(value)
            except ValueError:
                continue
            if int_val > 0:
                trait_items.append(
                    CharacterTraitAdd(trait_id=trait_id, value=int_val, currency="NO_COST")
                )

        user_id = session["user_id"]

        try:
            if trait_items:
                traits_svc = sync_character_traits_service(
                    user_id=user_id, campaign_id=campaign_id, character_id=temp_char_id
                )
                result = traits_svc.bulk_assign(trait_items)
                if result.failed:
                    failed_names = [f.trait_id for f in result.failed]
                    flash(f"Some traits failed to assign: {', '.join(failed_names)}", "warning")

            char_svc = sync_characters_service(user_id=user_id, campaign_id=campaign_id)
            char_svc.update(temp_char_id, CharacterUpdate(is_temporary=False))
        except APIError as exc:
            logger.exception("Failed to finalize character")
            flash(str(exc), "error")

            character = sync_characters_service(user_id=user_id, campaign_id=campaign_id).get(
                temp_char_id
            )
            sheet_svc = CharacterSheetService(
                character=character, requesting_user=g.requesting_user
            )
            full_sheet = sheet_svc.get_full_sheet(include_available_traits=True)
            back_url = url_for(
                "character_create.manual_profile", campaign_id=campaign_id, resume="1"
            )

            return catalog.render(
                "character_manual_create.partials.TraitsForm",
                campaign=campaign,
                full_sheet=full_sheet,
                back_url=back_url,
                errors=[str(exc)],
            )

        _clear_temp_session()
        clear_global_context_cache(session["company_id"], session["user_id"])
        flash("Character created successfully!", "success")
        redirect_url = url_for("character_view.character", character_id=temp_char_id)
        return Response("", status=200, headers={"HX-Redirect": redirect_url})


bp.add_url_rule(
    "/campaign/<string:campaign_id>/characters/profile_edit/create",
    view_func=ManualFinalizeView.as_view("manual_finalize"),
    methods=["POST"],
)
