"""Chapter detail blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, abort, request, session
from flask.views import MethodView
from vclient import sync_chapters_service

from vweb import catalog
from vweb.lib.api import fetch_book_or_404
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_manage_campaign
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.lib.jinja import htmx_response
from vweb.routes.chapter.views_notes import ChapterNotesTableView

if TYPE_CHECKING:
    from vclient.models import Asset, Campaign, CampaignBook, CampaignChapter

bp = Blueprint("chapter_view", __name__)

SECTIONS = ("story", "notes")
CHAPTER_CARD_ID = "chapter-story"


def _adjacent_chapters(
    chapters: list[CampaignChapter], chapter_id: str
) -> tuple[CampaignChapter | None, CampaignChapter | None, int]:
    """Return (prev, next, total) for the chapter with the given id."""
    sorted_chapters = sorted(chapters, key=lambda c: c.number)
    total = len(sorted_chapters)
    current_idx = next((i for i, c in enumerate(sorted_chapters) if c.id == chapter_id), None)
    if current_idx is None:
        return None, None, total
    prev_ch = sorted_chapters[current_idx - 1] if current_idx > 0 else None
    next_ch = sorted_chapters[current_idx + 1] if current_idx < total - 1 else None
    return prev_ch, next_ch, total


def _render_chapter_card(  # noqa: PLR0913
    *,
    chapter: CampaignChapter,
    book: CampaignBook,
    campaign: Campaign,
    assets: list[Asset],
    prev_chapter: CampaignChapter | None = None,
    next_chapter: CampaignChapter | None = None,
    total_chapters: int = 0,
    active_section: str = "story",
) -> str:
    """Render the full chapter content card (persistent wrapper with tabs)."""
    return catalog.render(
        "chapter.partials.ChapterContentCard",
        chapter=chapter,
        book=book,
        campaign=campaign,
        assets=assets,
        prev_chapter=prev_chapter,
        next_chapter=next_chapter,
        total_chapters=total_chapters,
        active_section=active_section,
    )


def _card_with_header_response(
    card_html: str,
    chapter: CampaignChapter,
    book: CampaignBook,
    campaign: Campaign,
) -> str:
    """Return an HTMX response pairing the chapter card with an OOB PageHeader swap."""
    header = catalog.render(
        "chapter.partials.ChapterPageHeader",
        chapter=chapter,
        book=book,
        campaign=campaign,
        oob=True,
    )
    return htmx_response(card_html, header)


class ChapterDetailView(MethodView):
    """Chapter detail page with tabbed navigation."""

    def get(
        self,
        campaign_id: str,
        book_id: str,
        chapter_id: str,
        section: str | None = None,
    ) -> str:
        """Render chapter detail page or tab fragment."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        user_id = session.get("user_id", "")

        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        if section is not None and section not in SECTIONS:
            section = "story"

        active_section = section or "story"

        # Only the story tab renders the image carousel; skip the asset fetch
        # when the notes tab is requested to avoid an extra API call.
        assets: list[Asset] = (
            ch_svc.list_all_assets(chapter_id) if active_section == "story" else []
        )

        is_htmx = request.headers.get("HX-Request")
        hx_target = request.headers.get("HX-Target", "")

        if is_htmx and section is not None and hx_target == CHAPTER_CARD_ID:
            prev_ch, next_ch, total_chapters = _adjacent_chapters(ch_svc.list_all(), chapter_id)
            card = _render_chapter_card(
                chapter=chapter,
                book=book,
                campaign=campaign,
                assets=assets,
                prev_chapter=prev_ch,
                next_chapter=next_ch,
                total_chapters=total_chapters,
                active_section=active_section,
            )
            return _card_with_header_response(card, chapter, book, campaign)

        if is_htmx and section is not None:
            content = self._render_section(active_section, chapter, book, campaign, assets=assets)
            nav = catalog.render(
                "chapter.components.ChapterNav",
                chapter_id=chapter_id,
                campaign_id=campaign_id,
                book_id=book_id,
                active_section=active_section,
                oob=True,
            )
            header = catalog.render(
                "chapter.partials.ChapterPageHeader",
                chapter=chapter,
                book=book,
                campaign=campaign,
                oob=True,
            )
            return htmx_response(content, nav, header)

        prev_ch, next_ch, total_chapters = _adjacent_chapters(ch_svc.list_all(), chapter_id)
        return catalog.render(
            "chapter.ChapterDetail",
            chapter=chapter,
            book=book,
            campaign=campaign,
            prev_chapter=prev_ch,
            next_chapter=next_ch,
            total_chapters=total_chapters,
            active_section=active_section,
            assets=assets,
        )

    def _render_section(
        self,
        section: str,
        chapter: CampaignChapter,
        book: CampaignBook,
        campaign: Campaign,
        *,
        assets: list[Asset],
    ) -> str:
        """Render a single tab inner fragment (swapped into #chapter-tab-content)."""
        if section == "notes":
            return catalog.render(
                "chapter.partials.ChapterNotes",
                chapter=chapter,
                book=book,
                campaign=campaign,
            )
        return catalog.render(
            "chapter.partials.ChapterStory",
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
        )

    def delete(
        self,
        campaign_id: str,
        book_id: str,
        chapter_id: str,
        section: str | None = None,  # noqa: ARG002
    ) -> str:
        """Delete chapter and return refreshed chapters card."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        user_id = session.get("user_id", "")

        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
        ch_svc.delete(chapter_id)
        clear_global_context_cache(session["company_id"], session["user_id"])

        chapters = ch_svc.list_all()
        chapters.sort(key=lambda c: c.number)

        return catalog.render(
            "book.partials.ChaptersCard",
            book=book,
            campaign=campaign,
            chapters=chapters,
        )


class ChapterEditView(MethodView):
    """Chapter edit form (GET form, POST update)."""

    def get(self, campaign_id: str, book_id: str, chapter_id: str) -> str:
        """Render chapter edit form fragment."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        user_id = session.get("user_id", "")
        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
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
        user_id = session.get("user_id", "")
        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
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
        prev_ch, next_ch, total_chapters = _adjacent_chapters(ch_svc.list_all(), chapter_id)
        card = _render_chapter_card(
            chapter=updated,
            book=book,
            campaign=campaign,
            assets=assets,
            prev_chapter=prev_ch,
            next_chapter=next_ch,
            total_chapters=total_chapters,
        )
        return _card_with_header_response(card, updated, book, campaign)


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
        user_id = session.get("user_id", "")

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

        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
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
        user_id = session.get("user_id", "")
        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        assets = upload_and_append_asset(
            svc=ch_svc, parent_id=chapter_id, file=request.files.get("image")
        )
        prev_ch, next_ch, total_chapters = _adjacent_chapters(ch_svc.list_all(), chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            prev_chapter=prev_ch,
            next_chapter=next_ch,
            total_chapters=total_chapters,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content_html, flash_html)


class ChapterImageDeleteView(MethodView):
    """Delete an image asset from a chapter."""

    def delete(self, campaign_id: str, book_id: str, chapter_id: str, asset_id: str) -> object:
        """Delete the asset and re-render the Story partial."""
        if not can_manage_campaign():
            abort(403)

        book, campaign = fetch_book_or_404(campaign_id, book_id)
        user_id = session.get("user_id", "")
        ch_svc = sync_chapters_service(
            user_id=user_id,
            campaign_id=campaign_id,
            book_id=book_id,
            company_id=session["company_id"],
        )
        chapter = ch_svc.get(chapter_id)
        if chapter is None:
            abort(404)

        handle_image_delete(svc=ch_svc, parent_id=chapter_id, asset_id=asset_id)

        assets = ch_svc.list_all_assets(chapter_id)
        prev_ch, next_ch, total_chapters = _adjacent_chapters(ch_svc.list_all(), chapter_id)
        content_html = _render_chapter_card(
            chapter=chapter,
            book=book,
            campaign=campaign,
            assets=assets,
            prev_chapter=prev_ch,
            next_chapter=next_ch,
            total_chapters=total_chapters,
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
    defaults={"section": None},
    methods=["GET", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter/<chapter_id>/<section>",
    view_func=ChapterDetailView.as_view("chapter_detail_section"),
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/chapter",
    view_func=ChapterCreateView.as_view("chapter_create"),
)
