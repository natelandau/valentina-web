"""Chapter detail blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, abort, flash, request, session, url_for
from flask.views import MethodView
from vclient import sync_chapters_service

from vweb.lib import cache
from vweb.lib.api import (
    count_notes,
    fetch_book_or_404,
    fetch_chapter_or_404,
)
from vweb.lib.catalog import catalog
from vweb.lib.crud.routing import register_crud_table_routes
from vweb.lib.guards import can_manage_campaign
from vweb.lib.htmx import htmx_response_with_flash, hx_redirect
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.routes.chapter.views_notes import ChapterNotesTableView

if TYPE_CHECKING:
    from vclient._sync.services.campaign_book_chapters import SyncChaptersService
    from vclient.models import Asset, Campaign, CampaignBook, CampaignChapter

bp = Blueprint("chapter_view", __name__)

CHAPTER_CARD_ID = "chapter-content"
BOOK_CHAPTERS_CARD_ID = "book-chapters-card"


def _chapters_service(campaign_id: str, book_id: str) -> SyncChaptersService:
    """Build a chapters service scoped to the current user and company."""
    return sync_chapters_service(
        campaign_id=campaign_id,
        book_id=book_id,
        on_behalf_of=session.get("user_id", ""),
        company_id=session["company_id"],
    )


def _chapter_create_cancel_url(campaign_id: str, book_id: str, from_chapter: str) -> str:
    """Build the URL the chapter create form's Cancel button restores.

    From a chapter's detail page Cancel restores that chapter's content card;
    from the book page it restores the book's chapters card.
    """
    if from_chapter:
        return url_for(
            "chapter_view.chapter_detail",
            campaign_id=campaign_id,
            book_id=book_id,
            chapter_id=from_chapter,
        )
    return url_for("book_view.book_detail", campaign_id=campaign_id, book_id=book_id)


def _chapter_create_target(from_chapter: str) -> str:
    """Return the container id the create form swaps into.

    The target is derived server-side from whether a launching chapter is in
    scope: from a chapter's detail page the form replaces that page's content
    card; from the book page it replaces the chapters card. Deriving it (rather
    than accepting a client-supplied id) keeps a user-controlled value out of the
    form's hx-target/hx-select attributes.
    """
    return CHAPTER_CARD_ID if from_chapter else BOOK_CHAPTERS_CARD_ID


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
        chapter = fetch_chapter_or_404(campaign_id, book_id, chapter_id)
        chapters = cache.campaign_content.chapters(campaign_id, book_id)

        session["last_campaign_id"] = campaign_id

        chapters_service = _chapters_service(campaign_id, book_id)
        assets = chapters_service.list_all_assets(chapter_id)
        note_count = count_notes(chapters_service, chapter_id)

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
        chapters_service = _chapters_service(campaign_id, book_id)
        chapters_service.delete(chapter_id)
        cache.global_context.clear(session["company_id"], session["user_id"])
        cache.campaign_content.clear(
            session["company_id"], campaign_id=campaign_id, book_id=book_id
        )

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
        chapter = fetch_chapter_or_404(campaign_id, book_id, chapter_id)

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
        chapter = fetch_chapter_or_404(campaign_id, book_id, chapter_id)
        chapters_service = _chapters_service(campaign_id, book_id)

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

        updated = chapters_service.update(chapter_id, name=name, description=description)
        if number != chapter.number:
            updated = chapters_service.renumber(chapter_id, number)
        cache.global_context.clear(session["company_id"], session["user_id"])
        cache.campaign_content.clear(session["company_id"], book_id=book_id)

        assets = chapters_service.list_all_assets(chapter_id)
        note_count = count_notes(chapters_service, chapter_id)
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
        from_chapter = request.args.get("from_chapter", "")
        return catalog.render(
            "book.partials.ChapterCreateForm",
            book=book,
            campaign=campaign,
            target_id=_chapter_create_target(from_chapter),
            from_chapter=from_chapter,
            cancel_url=_chapter_create_cancel_url(campaign_id, book_id, from_chapter),
            errors=[],
        )

    def post(self, campaign_id: str, book_id: str) -> object:
        """Create a new chapter and redirect the client to its detail page."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        from_chapter = request.form.get("from_chapter", "")
        target_id = _chapter_create_target(from_chapter)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        errors: list[str] = []
        if not name:
            errors.append("Name is required")

        if errors:
            return catalog.render(
                "book.partials.ChapterCreateForm",
                book=book,
                campaign=campaign,
                target_id=target_id,
                from_chapter=from_chapter,
                cancel_url=_chapter_create_cancel_url(campaign_id, book_id, from_chapter),
                errors=errors,
                form_data=request.form,
            )

        chapters_service = _chapters_service(campaign_id, book_id)
        new_chapter = chapters_service.create(name=name, description=description)
        cache.global_context.clear(session["company_id"], session["user_id"])
        cache.campaign_content.clear(
            session["company_id"], campaign_id=campaign_id, book_id=book_id
        )

        flash(f"Created chapter: {name}", "success")
        return hx_redirect(
            url_for(
                "chapter_view.chapter_detail",
                campaign_id=campaign_id,
                book_id=book_id,
                chapter_id=new_chapter.id,
            )
        )


class ChapterImageUploadView(MethodView):
    """Upload an image asset for a chapter."""

    def post(self, campaign_id: str, book_id: str, chapter_id: str) -> object:
        """Handle a multipart image upload, validate, persist, and re-render the Story partial."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        chapter = fetch_chapter_or_404(campaign_id, book_id, chapter_id)
        chapters_service = _chapters_service(campaign_id, book_id)

        assets = upload_and_append_asset(
            svc=chapters_service, parent_id=chapter_id, file=request.files.get("image")
        )
        note_count = count_notes(chapters_service, chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            note_count=note_count,
        )
        return htmx_response_with_flash(content_html)


class ChapterImageDeleteView(MethodView):
    """Delete an image asset from a chapter."""

    def delete(self, campaign_id: str, book_id: str, chapter_id: str, asset_id: str) -> object:
        """Delete the asset and re-render the chapter content card."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        chapter = fetch_chapter_or_404(campaign_id, book_id, chapter_id)
        chapters_service = _chapters_service(campaign_id, book_id)

        handle_image_delete(svc=chapters_service, parent_id=chapter_id, asset_id=asset_id)

        assets = chapters_service.list_all_assets(chapter_id)
        note_count = count_notes(chapters_service, chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            note_count=note_count,
        )
        return htmx_response_with_flash(content_html)


register_crud_table_routes(
    bp,
    ChapterNotesTableView,
    base_path="/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/crud-notes",
    name_prefix="chapter_notes",
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
    methods=["GET", "POST"],
)
