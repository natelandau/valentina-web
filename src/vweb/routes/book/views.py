"""Book detail blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, abort, g, request, session
from flask.views import MethodView
from vclient import sync_books_service, sync_chapters_service

from vweb import catalog
from vweb.lib.api import fetch_book_or_404
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_manage_campaign
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.lib.jinja import htmx_response
from vweb.routes.book.views_notes import BookNotesTableView

if TYPE_CHECKING:
    from vclient.models import Asset, Campaign, CampaignBook, CampaignChapter


SECTIONS = ("description", "notes")
BOOK_CARD_ID = "book-content"


def _load_adjacent_books(
    campaign_id: str, book_number: int
) -> tuple[CampaignBook | None, CampaignBook | None, int]:
    """Resolve previous, next, and total book count for a campaign from the global context."""
    all_books = sorted(
        g.global_context.books_by_campaign.get(campaign_id, []),
        key=lambda x: x.number,
    )
    prev_book: CampaignBook | None = None
    next_book: CampaignBook | None = None
    for i, b in enumerate(all_books):
        if b.number == book_number:
            if i > 0:
                prev_book = all_books[i - 1]
            if i < len(all_books) - 1:
                next_book = all_books[i + 1]
            break
    return prev_book, next_book, len(all_books)


def _render_book_card(  # noqa: PLR0913
    *,
    book: CampaignBook,
    campaign: Campaign,
    assets: list[Asset],
    prev_book: CampaignBook | None = None,
    next_book: CampaignBook | None = None,
    total_books: int = 0,
    active_section: str = "description",
) -> str:
    """Render the full book content card (persistent wrapper with tabs)."""
    return catalog.render(
        "book.partials.BookContentCard",
        book=book,
        campaign=campaign,
        assets=assets,
        prev_book=prev_book,
        next_book=next_book,
        total_books=total_books,
        active_section=active_section,
    )


def _load_sorted_chapters(user_id: str, campaign_id: str, book_id: str) -> list[CampaignChapter]:
    """Fetch all chapters for a book, sorted by number."""
    chapters = sync_chapters_service(
        user_id=user_id,
        campaign_id=campaign_id,
        book_id=book_id,
        company_id=session["company_id"],
    ).list_all()
    chapters.sort(key=lambda c: c.number)
    return chapters


def _card_with_header_response(card_html: str, book: CampaignBook, *extra_oob: str) -> str:
    """Return an HTMX response pairing the book card with OOB PageHeader swap and extras."""
    header = catalog.render("book.partials.BookPageHeader", book=book, oob=True)
    return htmx_response(card_html, header, *extra_oob)


bp = Blueprint("book_view", __name__)


class BookDetailView(MethodView):
    """Book detail page and edit functionality."""

    def get(
        self,
        campaign_id: str,
        book_id: str,
        action: str | None = None,
        section: str | None = None,
    ) -> str:
        """Render book detail page, section fragment, or edit form fragment."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)

        if action == "edit":
            if not can_manage_campaign():
                abort(403)
            return catalog.render(
                "book.partials.BookEditForm",
                book=book,
                campaign=campaign,
                errors=[],
            )

        user_id = session.get("user_id", "")

        if section is not None and section not in SECTIONS:
            section = "description"
        active_section = section or "description"

        # Only the description tab renders the image carousel; skip the asset
        # fetch when the notes tab is requested to avoid an extra API call.
        assets: list[Asset] = (
            sync_books_service(
                user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
            ).list_all_assets(book.id)
            if active_section == "description"
            else []
        )

        is_htmx = request.headers.get("HX-Request")
        hx_target = request.headers.get("HX-Target", "")

        if is_htmx and hx_target == BOOK_CARD_ID:
            prev_book, next_book, total_books = _load_adjacent_books(campaign_id, book.number)
            card = _render_book_card(
                book=book,
                campaign=campaign,
                assets=assets,
                prev_book=prev_book,
                next_book=next_book,
                total_books=total_books,
                active_section=active_section,
            )
            chapters = _load_sorted_chapters(user_id, campaign_id, book_id)
            chapters_html = catalog.render(
                "book.partials.ChaptersCard",
                book=book,
                campaign=campaign,
                chapters=chapters,
                oob=True,
            )
            return _card_with_header_response(card, book, chapters_html)

        if is_htmx and section is not None:
            content = self._render_section(active_section, book, campaign, assets=assets)
            nav = catalog.render(
                "book.components.BookNav",
                book_id=book_id,
                campaign_id=campaign_id,
                active_section=active_section,
                oob=True,
            )
            header = catalog.render("book.partials.BookPageHeader", book=book, oob=True)
            return htmx_response(content, nav, header)

        prev_book, next_book, total_books = _load_adjacent_books(campaign_id, book.number)
        chapters = _load_sorted_chapters(user_id, campaign_id, book_id)

        return catalog.render(
            "book.BookDetail",
            book=book,
            campaign=campaign,
            chapters=chapters,
            prev_book=prev_book,
            next_book=next_book,
            total_books=total_books,
            active_section=active_section,
            assets=assets,
        )

    def _render_section(
        self,
        section: str,
        book: CampaignBook,
        campaign: Campaign,
        *,
        assets: list[Asset],
    ) -> str:
        """Render a single tab inner fragment (swapped into #book-tab-content)."""
        if section == "notes":
            return catalog.render("book.partials.BookNotes", book=book, campaign=campaign)
        return catalog.render(
            "book.partials.BookDescription",
            book=book,
            campaign=campaign,
            assets=assets,
        )

    def post(
        self,
        campaign_id: str,
        book_id: str,
        action: str | None = None,  # noqa: ARG002
        section: str | None = None,  # noqa: ARG002
    ) -> str:
        """Handle book edit form submission."""
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

        number = book.number
        if number_str:
            try:
                number = int(number_str)
            except ValueError:
                errors.append("Number must be a valid integer")

        if errors:
            return catalog.render(
                "book.partials.BookEditForm",
                book=book,
                campaign=campaign,
                errors=errors,
                form_data=request.form,
            )

        svc = sync_books_service(
            user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
        )
        updated_book = svc.update(book_id, name=name, description=description)
        if number != book.number:
            updated_book = svc.renumber(book_id, number)
        clear_global_context_cache(session["company_id"], session["user_id"])

        assets = svc.list_all_assets(book_id)
        prev_book, next_book, total_books = _load_adjacent_books(campaign_id, updated_book.number)

        card = _render_book_card(
            book=updated_book,
            campaign=campaign,
            assets=assets,
            prev_book=prev_book,
            next_book=next_book,
            total_books=total_books,
        )
        return _card_with_header_response(card, updated_book)


class BookImageUploadView(MethodView):
    """Upload an image asset for a book."""

    def post(self, campaign_id: str, book_id: str) -> object:
        """Handle a multipart image upload, validate, persist, and re-render the Story partial."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        if not can_manage_campaign():
            abort(403)

        user_id = session.get("user_id", "")
        svc = sync_books_service(
            user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
        )

        assets = upload_and_append_asset(
            svc=svc, parent_id=book_id, file=request.files.get("image")
        )
        prev_book, next_book, total_books = _load_adjacent_books(campaign_id, book.number)
        content_html = _render_book_card(
            book=book,
            campaign=campaign,
            assets=assets,
            prev_book=prev_book,
            next_book=next_book,
            total_books=total_books,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content_html, flash_html)


class BookImageDeleteView(MethodView):
    """Delete an image asset from a book."""

    def delete(self, campaign_id: str, book_id: str, asset_id: str) -> object:
        """Delete the asset and re-render the Story partial."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        if not can_manage_campaign():
            abort(403)

        user_id = session.get("user_id", "")
        svc = sync_books_service(
            user_id=user_id, campaign_id=campaign_id, company_id=session["company_id"]
        )

        handle_image_delete(svc=svc, parent_id=book_id, asset_id=asset_id)

        assets = svc.list_all_assets(book_id)
        prev_book, next_book, total_books = _load_adjacent_books(campaign_id, book.number)
        content_html = _render_book_card(
            book=book,
            campaign=campaign,
            assets=assets,
            prev_book=prev_book,
            next_book=next_book,
            total_books=total_books,
        )
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(content_html, flash_html)


_book_detail_view = BookDetailView.as_view("book_detail")
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>",
    view_func=_book_detail_view,
    defaults={"action": None, "section": None},
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/section/<section>",
    view_func=BookDetailView.as_view("book_detail_section"),
    defaults={"action": None},
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/<action>",
    view_func=BookDetailView.as_view("book_detail_action"),
    defaults={"section": None},
)

_book_notes_view = BookNotesTableView.as_view("book_notes")
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/notes",
    defaults={"item_id": None},
    view_func=_book_notes_view,
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/notes/<string:item_id>",
    view_func=_book_notes_view,
    methods=["POST", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/notes/form",
    defaults={"item_id": None},
    view_func=BookNotesTableView.as_view("book_notes_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/notes/form/<string:item_id>",
    view_func=BookNotesTableView.as_view("book_notes_form_edit"),
    methods=["GET"],
)

bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/images",
    view_func=BookImageUploadView.as_view("book_image_upload"),
    methods=["POST"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/images/<asset_id>",
    view_func=BookImageDeleteView.as_view("book_image_delete"),
    methods=["DELETE"],
)
