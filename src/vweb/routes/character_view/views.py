"""Character routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    g,
    make_response,
    redirect,
    request,
    session,
    url_for,
)
from flask.views import MethodView
from vclient import sync_character_blueprint_service, sync_characters_service

from vweb import catalog
from vweb.lib.api import get_character_and_campaign
from vweb.lib.character_sheet import CharacterSheetService
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_edit_character
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.lib.jinja import htmx_response, hx_redirect
from vweb.routes.character_view.views_inventory import CharacterInventoryTableView
from vweb.routes.character_view.views_notes import CharacterNotesTableView
from vweb.routes.dictionary.cache import get_all_terms

if TYPE_CHECKING:
    from vclient.models import Campaign, Character
    from werkzeug.wrappers.response import Response

bp = Blueprint("character_view", __name__)

SECTIONS = ("sheet", "info", "profile", "images", "stats")


class CharacterView(MethodView):
    """Character detail view handling all section tabs."""

    @staticmethod
    def _fetch_section_data(
        section: str,
        character: Character,
        campaign: Campaign,
    ) -> dict:
        """Fetch the API data required by a specific tab section's template.

        Args:
            section: One of the SECTIONS values (sheet, info, profile, images, stats).
            character: The character being viewed. Must not be None.
            campaign: The campaign the character belongs to. Must not be None.

        Returns:
            Template variables dict including character, campaign, and section-specific data.
            The dict is ready to be passed to the template renderer.
        """
        user = g.requesting_user
        data: dict = {
            "character": character,
            "campaign": campaign,
        }

        match section:
            case "sheet":
                svc = CharacterSheetService(character=character, requesting_user=user)
                full_sheet = svc.get_full_sheet()
                data["full_sheet"] = full_sheet
                data["dictionary_terms"] = get_all_terms()
            case "profile":
                svc = CharacterSheetService(character, user)
                data["concept"] = (
                    sync_character_blueprint_service(company_id=session["company_id"]).get_concept(
                        concept_id=character.concept_id
                    )
                    if character.concept_id
                    else None
                )
                data["dictionary_terms"] = get_all_terms()
            case "info":
                pass
            case "images":
                char_svc = sync_characters_service(
                    on_behalf_of=user.id,
                    company_id=session["company_id"],
                )
                data["assets"] = char_svc.list_all_assets(character.id)
            case "stats":
                char_svc = sync_characters_service(
                    on_behalf_of=user.id,
                    company_id=session["company_id"],
                )
                data["statistics"] = char_svc.get_statistics(character.id)

        return data

    @staticmethod
    def _render_section(section: str, section_data: dict) -> str:
        """Render a section fragment via catalog.

        Args:
            section: The section name.
            section_data: Template variables dict from _fetch_section_data.

        Returns:
            Rendered HTML string.
        """
        match section:
            case "sheet":
                return catalog.render(
                    "character_view.partials.SheetContent",
                    full_sheet=section_data["full_sheet"],
                    dictionary_terms=section_data["dictionary_terms"],
                )
            case "info":
                return catalog.render(
                    "character_view.partials.InfoContent",
                    character=section_data["character"],
                )
            case "profile":
                return catalog.render(
                    "character_view.partials.ProfileContent",
                    character=section_data["character"],
                    concept=section_data.get("concept"),
                    dictionary_terms=section_data["dictionary_terms"],
                )
            case "images":
                return catalog.render(
                    "character_view.partials.ImagesContent",
                    character=section_data["character"],
                    assets=section_data["assets"],
                )
            case "stats":
                return catalog.render(
                    "character_view.partials.StatsContent",
                    statistics=section_data["statistics"],
                )
            case _:
                msg = f"Unknown section: {section}"
                raise ValueError(msg)

    def get(self, character_id: str, section: str = "sheet") -> str | Response:
        """Render a character section, returning a fragment for HTMX or a full page.

        Args:
            character_id: The character's unique identifier.
            section: One of the SECTIONS values (sheet, info, profile, images, stats).

        Returns:
            Rendered HTML string or a redirect/error response.
        """
        if section not in SECTIONS:
            section = "sheet"

        character, campaign = get_character_and_campaign(character_id)

        if not character or not campaign:
            if request.headers.get("HX-Request"):
                return hx_redirect(url_for("index.index"))

            return redirect(url_for("index.index"))  # ty:ignore[invalid-return-type]

        section_data = self._fetch_section_data(section, character, campaign)

        if request.headers.get("HX-Request"):
            content = CharacterView._render_section(section, section_data)
            nav = catalog.render(
                "character_view.components.CharacterNav",
                character_id=character_id,
                active_section=section,
                oob=True,
            )
            return htmx_response(content, nav)

        return catalog.render(
            "character_view.Main",
            **section_data,
            active_section=section,
        )


_view = CharacterView.as_view("character")
bp.add_url_rule("/character/<string:character_id>", defaults={"section": "sheet"}, view_func=_view)
bp.add_url_rule("/character/<string:character_id>/<string:section>", view_func=_view)


class CharacterDeleteView(MethodView):
    """Handle character deletion."""

    def delete(self, character_id: str) -> Response:
        """Delete a character and redirect to home.

        Args:
            character_id: The character to delete.

        Returns:
            An HX-Redirect response to the home page.
        """
        character, _campaign = get_character_and_campaign(character_id)

        if not character or not can_edit_character(character):
            return make_response("", 403)

        user = g.requesting_user
        char_svc = sync_characters_service(on_behalf_of=user.id, company_id=session["company_id"])
        char_svc.delete(character_id)
        clear_global_context_cache(session["company_id"], session["user_id"])

        return hx_redirect("/")


bp.add_url_rule(
    "/character/<string:character_id>",
    view_func=CharacterDeleteView.as_view("delete"),
    methods=["DELETE"],
)


class ImageUploadView(MethodView):
    """Handle image upload for a character."""

    def post(self, character_id: str) -> str | Response:
        """Upload an image to a character's gallery.

        Args:
            character_id: The character to upload the image for.

        Returns:
            Updated ImagesContent fragment or 403/404 response.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            return make_response("", 404)

        if not can_edit_character(character):
            return make_response("", 403)

        user = g.requesting_user
        char_svc = sync_characters_service(on_behalf_of=user.id, company_id=session["company_id"])

        assets = upload_and_append_asset(
            svc=char_svc, parent_id=character_id, file=request.files.get("image")
        )
        content = catalog.render(
            "character_view.partials.ImagesContent",
            character=character,
            assets=assets,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content, flash_html)


bp.add_url_rule(
    "/character/<string:character_id>/images",
    view_func=ImageUploadView.as_view("image_upload"),
    methods=["POST"],
)


class ImageDeleteView(MethodView):
    """Handle image deletion for a character."""

    def delete(self, character_id: str, asset_id: str) -> str | Response:
        """Delete an image from a character's gallery.

        Args:
            character_id: The character that owns the image.
            asset_id: The asset to delete.

        Returns:
            Updated ImagesContent fragment or 403/404 response.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            return make_response("", 404)

        if not can_edit_character(character):
            return make_response("", 403)

        user = g.requesting_user
        char_svc = sync_characters_service(on_behalf_of=user.id, company_id=session["company_id"])

        handle_image_delete(svc=char_svc, parent_id=character_id, asset_id=asset_id)

        assets = char_svc.list_all_assets(character.id)
        content = catalog.render(
            "character_view.partials.ImagesContent",
            character=character,
            assets=assets,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content, flash_html)


bp.add_url_rule(
    "/character/<string:character_id>/images/<string:asset_id>",
    view_func=ImageDeleteView.as_view("image_delete"),
    methods=["DELETE"],
)


# ---------------------------------------------------------------------------
# Character notes CRUD table
# ---------------------------------------------------------------------------
_notes_view = CharacterNotesTableView.as_view("character_notes")
bp.add_url_rule(
    "/character/<string:parent_id>/notes",
    defaults={"item_id": None},
    view_func=_notes_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/notes/<string:item_id>",
    view_func=_notes_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/notes/form",
    defaults={"item_id": None},
    view_func=CharacterNotesTableView.as_view("character_notes_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/notes/form/<string:item_id>",
    view_func=CharacterNotesTableView.as_view("character_notes_form_edit"),
    methods=["GET"],
)


# ---------------------------------------------------------------------------
# Character inventory CRUD table
# ---------------------------------------------------------------------------
_inventory_view = CharacterInventoryTableView.as_view("character_inventory")
bp.add_url_rule(
    "/character/<string:parent_id>/inventory",
    defaults={"item_id": None},
    view_func=_inventory_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/inventory/<string:item_id>",
    view_func=_inventory_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/inventory/form",
    defaults={"item_id": None},
    view_func=CharacterInventoryTableView.as_view("character_inventory_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/character/<string:parent_id>/inventory/form/<string:item_id>",
    view_func=CharacterInventoryTableView.as_view("character_inventory_form_edit"),
    methods=["GET"],
)
