"""Chapter detail blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, abort, request, session, url_for
from flask.views import MethodView
from vclient import sync_chapters_service

from vweb import catalog
from vweb.lib.api import count_notes, fetch_book_or_404
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_manage_campaign
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.lib.jinja import htmx_response, hx_redirect
from vweb.routes.chapter.views_notes import ChapterNotesTableView

if TYPE_CHECKING:
    from vclient.models import Asset, Campaign, CampaignBook, CampaignChapter

bp = Blueprint("chapter_view", __name__)

CHAPTER_CARD_ID = "chapter-content"


def _chapters_svc(campaign_id: str, book_id: str):  # noqa: ANN202
    """Build a chapters service scoped to the current user and company."""
    return sync_chapters_service(
        campaign_id=campaign_id,
        book_id=book_id,
        on_behalf_of=session.get("user_id", ""),
        company_id=session["company_id"],
    )


def _render_chapter_card(
    *,
    chapter: CampaignChapter,
    book: CampaignBook,
    campaign: Campaign,
    assets: list[Asset],
    note_count: int,
) -> str:
    """Render the full chapter content card (title + thumbnails + sub-tabs + metadata sidebar)."""
    return catalog.render(
        "chapter.partials.ChapterContentCard",
        chapter=chapter,
        book=book,
        campaign=campaign,
        assets=assets,
        note_count=note_count,
    )


class ChapterDetailView(MethodView):
    """Chapter detail page."""

    def get(
        self,
        campaign_id: str,
        book_id: str,
        chapter_id: str,
    ) -> str:
        """Render the chapter detail page."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        session["last_campaign_id"] = campaign_id

        assets = ch_svc.list_all_assets(chapter_id)
        note_count = count_notes(ch_svc, chapter_id)

        chapters = ch_svc.list_all()
        chapters.sort(key=lambda c: c.number)

        return catalog.render(
            "chapter.ChapterDetail",
            chapter=chapter,
            book=book,
            campaign=campaign,
            chapters=chapters,
            assets=assets,
            note_count=note_count,
        )

    def delete(
        self,
        campaign_id: str,
        book_id: str,
        chapter_id: str,
    ) -> object:
        """Delete the chapter and redirect to the parent book page."""
        if not can_manage_campaign():
            abort(403)

        fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        ch_svc.delete(chapter_id)
        clear_global_context_cache(session["company_id"], session["user_id"])

        return hx_redirect(
            url_for("book_view.book_detail", campaign_id=campaign_id, book_id=book_id)
        )


class ChapterEditView(MethodView):
    """Chapter edit form (GET form, POST update)."""

    def get(self, campaign_id: str, book_id: str, chapter_id: str) -> str:
        """Render chapter edit form fragment."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        return catalog.render(
            "chapter.partials.ChapterEditForm",
            chapter=chapter,
            book=book,
            campaign=campaign,
            errors=[],
        )

    def post(self, campaign_id: str, book_id: str, chapter_id: str) -> str:
        """Handle chapter edit form submission."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        name = request.form.get("name", "").strip()
        number_str = request.form.get("number", "").strip()
        description = request.form.get("description", "").strip()

        errors: list[str] = []
        if not name:
            errors.append("Name is required")

        number = chapter.number
        if number_str:
            try:
                number = int(number_str)
            except ValueError:
                errors.append("Number must be a valid integer")

        if errors:
            return catalog.render(
                "chapter.partials.ChapterEditForm",
                chapter=chapter,
                book=book,
                campaign=campaign,
                errors=errors,
                form_data=request.form,
            )

        updated = ch_svc.update(chapter_id, name=name, description=description)
        if number != chapter.number:
            updated = ch_svc.renumber(chapter_id, number)
        clear_global_context_cache(session["company_id"], session["user_id"])

        assets = ch_svc.list_all_assets(chapter_id)
        note_count = count_notes(ch_svc, chapter_id)
        return _render_chapter_card(
            chapter=updated,
            book=book,
            campaign=campaign,
            assets=assets,
            note_count=note_count,
        )


class ChapterCreateView(MethodView):
    """Create a new chapter (inline form on book page)."""

    def get(self, campaign_id: str, book_id: str) -> str:
        """Render chapter create form."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        return catalog.render(
            "book.partials.ChapterCreateForm",
            book=book,
            campaign=campaign,
            errors=[],
        )

    def post(self, campaign_id: str, book_id: str) -> str:
        """Create a new chapter and return updated chapters card."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)

        name = request.form.get("name", "").strip()
        number_str = request.form.get("number", "").strip()
        description = request.form.get("description", "").strip()

        errors: list[str] = []
        if not name:
            errors.append("Name is required")

        number = 0
        if number_str:
            try:
                number = int(number_str)
            except ValueError:
                errors.append("Number must be a valid integer")

        if errors:
            return catalog.render(
                "book.partials.ChapterCreateForm",
                book=book,
                campaign=campaign,
                errors=errors,
                form_data=request.form,
            )

        ch_svc = _chapters_svc(campaign_id, book_id)
        ch_svc.create(name=name, number=number, description=description)
        clear_global_context_cache(session["company_id"], session["user_id"])

        chapters = ch_svc.list_all()
        chapters.sort(key=lambda c: c.number)

        return catalog.render(
            "book.partials.ChaptersCard",
            book=book,
            campaign=campaign,
            chapters=chapters,
        )


class ChapterImageUploadView(MethodView):
    """Upload an image asset for a chapter."""

    def post(self, campaign_id: str, book_id: str, chapter_id: str) -> object:
        """Handle a multipart image upload, validate, persist, and re-render the Story partial."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        assets = upload_and_append_asset(
            svc=ch_svc, parent_id=chapter_id, file=request.files.get("image")
        )
        note_count = count_notes(ch_svc, chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            note_count=note_count,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content_html, flash_html)


class ChapterImageDeleteView(MethodView):
    """Delete an image asset from a chapter."""

    def delete(self, campaign_id: str, book_id: str, chapter_id: str, asset_id: str) -> object:
        """Delete the asset and re-render the chapter content card."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        ch_svc = _chapters_svc(campaign_id, book_id)
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        handle_image_delete(svc=ch_svc, parent_id=chapter_id, asset_id=asset_id)

        assets = ch_svc.list_all_assets(chapter_id)
        note_count = count_notes(ch_svc, chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            note_count=note_count,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content_html, flash_html)


_ch_notes_view = ChapterNotesTableView.as_view("chapter_notes")
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/crud-notes",
    defaults={"item_id": None},
    view_func=_ch_notes_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/crud-notes/<string:item_id>",
    view_func=_ch_notes_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/crud-notes/form",
    defaults={"item_id": None},
    view_func=ChapterNotesTableView.as_view("chapter_notes_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/crud-notes/form/<string:item_id>",
    view_func=ChapterNotesTableView.as_view("chapter_notes_form_edit"),
    methods=["GET"],
)

# Register routes
# IMPORTANT: Register edit and image routes BEFORE the wildcard <section> route,
# otherwise /chapter/<id>/edit (or /images) would be captured as section="edit".
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/edit",
    view_func=ChapterEditView.as_view("chapter_edit"),
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/images",
    view_func=ChapterImageUploadView.as_view("chapter_image_upload"),
    methods=["POST"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/images/<asset_id>",
    view_func=ChapterImageDeleteView.as_view("chapter_image_delete"),
    methods=["DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>",
    view_func=ChapterDetailView.as_view("chapter_detail"),
    methods=["GET", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter",
    view_func=ChapterCreateView.as_view("chapter_create"),
)
