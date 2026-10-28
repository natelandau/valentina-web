"""Manage ability specialties from the trait edit page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import flash, g, request, session, url_for
from flask.views import MethodView
from vclient import sync_character_traits_service

from vweb.lib import cache
from vweb.lib.api import get_character_and_campaign
from vweb.lib.catalog import catalog
from vweb.lib.character_profile import TRAIT_API_ERRORS, find_character_trait
from vweb.lib.guards import can_edit_character, can_edit_traits_free
from vweb.lib.htmx import hx_redirect
from vweb.lib.trait_rules import accepts_specialties
from vweb.routes.character_trait_edit.services import (
    SPECIALTY_COST,
    SPECIALTY_NAME_MAX_LENGTH,
    SPECIALTY_NAME_MIN_LENGTH,
    humanize_spend_type,
    specialty_add_label,
    specialty_cost,
    specialty_help_text,
    specialty_name_error,
)

if TYPE_CHECKING:
    from vclient._sync.services import SyncCharacterTraitsService
    from vclient.constants import TraitModifyCurrency
    from vclient.models import Character, CharacterTrait
    from werkzeug.wrappers.response import Response


class _SpecialtyBaseView(MethodView):
    """Shared authorization and lookup for the specialty views."""

    def __init__(self, spend_type: TraitModifyCurrency) -> None:
        self.spend_type = spend_type
        self.character: Character
        self.character_trait: CharacterTrait
        self.form_url = ""

    def _resolve(self, character_id: str, character_trait_id: str) -> Response | None:
        """Authorize the request and load the character trait.

        Returns:
            An HX-Redirect response when the request is denied or the trait is unknown,
            otherwise None with ``character``, ``character_trait`` and ``form_url`` set.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            return hx_redirect(url_for("index.index"))

        sheet_url = url_for("character_view.character", character_id=character_id)
        if not can_edit_character(character):
            flash("You are not authorized to update this character", "error")
            return hx_redirect(sheet_url)

        if self.spend_type == "NO_COST" and not can_edit_traits_free(character):
            flash("You are not authorized to update traits without spending points", "error")
            return hx_redirect(sheet_url)

        self.character = character
        self.form_url = url_for(
            f"character_trait_edit.{self.spend_type}", character_id=character_id
        )

        full_sheet = cache.character_sheet.get(
            character.id, g.requesting_user.id, include_available_traits=True
        )
        character_trait = find_character_trait(full_sheet, character_trait_id)
        if character_trait is None:
            flash("Trait not found", "error")
            return hx_redirect(self.form_url)

        self.character_trait = character_trait
        return None

    def _service(self) -> SyncCharacterTraitsService:
        return sync_character_traits_service(
            on_behalf_of=g.requesting_user.id,
            character_id=self.character.id,
            company_id=session["company_id"],
        )

    def _finish(self, message: str) -> Response:
        """Flash success, invalidate caches, and reload the edit page."""
        flash(message, "success")
        cache.character_sheet.clear(self.character.id)
        cache.global_context.clear_current()
        return hx_redirect(self.form_url)

    @property
    def _ability_name(self) -> str:
        return self.character_trait.trait.name.strip().title()


class SpecialtiesView(_SpecialtyBaseView):
    """Render the specialty dialog (GET) and add a specialty (POST)."""

    def get(self, character_id: str, character_trait_id: str) -> str | Response:
        """Render the dialog body."""
        denied = self._resolve(character_id, character_trait_id)
        if denied is not None:
            return denied

        if not accepts_specialties(self.character_trait):
            flash("Only abilities with at least one dot can have specialties", "warning")
            return hx_redirect(self.form_url)

        settings = g.global_context.company.settings
        return catalog.render(
            "character_trait_edit.partials.SpecialtyDialog",
            character=self.character,
            character_trait=self.character_trait,
            spend_type=self.spend_type,
            add_label=specialty_add_label(self.spend_type, settings),
            help_text=specialty_help_text(settings),
            ability_name=self._ability_name,
            name_min=SPECIALTY_NAME_MIN_LENGTH,
            name_max=SPECIALTY_NAME_MAX_LENGTH,
        )

    def post(self, character_id: str, character_trait_id: str) -> Response:
        """Add a specialty."""
        denied = self._resolve(character_id, character_trait_id)
        if denied is not None:
            return denied

        name = request.form.get("name", "").strip()
        if error_message := specialty_name_error(name):
            flash(error_message, "warning")
            return hx_redirect(self.form_url)

        if not accepts_specialties(self.character_trait):
            flash("Only abilities with at least one dot can have specialties", "warning")
            return hx_redirect(self.form_url)

        try:
            self._service().add_specialty(character_trait_id, name, currency=self.spend_type)
        except TRAIT_API_ERRORS as error:
            flash(error.detail or "Failed to update specialty", "error")
            return hx_redirect(self.form_url)

        message = f"Added {name} to {self._ability_name}."
        if specialty_cost(self.spend_type, g.global_context.company.settings):
            message += f" You spent {SPECIALTY_COST} {humanize_spend_type(self.spend_type)}"
        return self._finish(message)


class SpecialtyView(_SpecialtyBaseView):
    """Rename (POST) or remove (DELETE) a single specialty."""

    def _current_name(self, specialty_id: str) -> str | None:
        return next(
            (s.name for s in self.character_trait.specialties if s.id == specialty_id), None
        )

    def post(self, character_id: str, character_trait_id: str, specialty_id: str) -> Response:
        """Rename a specialty."""
        denied = self._resolve(character_id, character_trait_id)
        if denied is not None:
            return denied

        name = request.form.get("name", "").strip()
        if error_message := specialty_name_error(name):
            flash(error_message, "warning")
            return hx_redirect(self.form_url)

        old_name = self._current_name(specialty_id)
        try:
            self._service().update_specialty(character_trait_id, specialty_id, name)
        except TRAIT_API_ERRORS as error:
            flash(error.detail or "Failed to update specialty", "error")
            return hx_redirect(self.form_url)

        return self._finish(f"Renamed {old_name or 'a specialty'} to {name}.")

    def delete(self, character_id: str, character_trait_id: str, specialty_id: str) -> Response:
        """Remove a specialty."""
        denied = self._resolve(character_id, character_trait_id)
        if denied is not None:
            return denied

        old_name = self._current_name(specialty_id)
        try:
            self._service().delete_specialty(character_trait_id, specialty_id)
        except TRAIT_API_ERRORS as error:
            flash(error.detail or "Failed to update specialty", "error")
            return hx_redirect(self.form_url)

        return self._finish(f"Removed {old_name or 'a specialty'} from {self._ability_name}.")
