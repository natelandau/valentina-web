"""Book detail blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, abort, redirect, request, session, url_for
from flask.views import MethodView
from vclient import sync_books_service

from vweb import catalog
from vweb.lib.api import (
    count_notes,
    fetch_book_or_404,
    fetch_campaign_or_404,
    get_books_for_campaign,
    get_chapters_for_book,
)
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import can_manage_campaign
from vweb.lib.image_uploads import handle_image_delete, upload_and_append_asset
from vweb.lib.jinja import htmx_response_with_flash, hx_redirect
from vweb.routes.book.views_notes import BookNotesTableView

if TYPE_CHECKING:
    from vclient.models import Asset, Campaign, CampaignBook


BOOK_CARD_ID = "book-content"


def _render_book_card(
    *,
    book: CampaignBook,
    campaign: Campaign,
    assets: list[Asset],
    chapters: list,
    note_count: int,
) -> str:
    """Render the full book content card (title + thumbnails + sub-tabs + metadata sidebar)."""
    return catalog.render(
        "book.partials.BookContentCard",
        book=book,
        campaign=campaign,
        assets=assets,
        chapters=chapters,
        note_count=note_count,
    )


bp = Blueprint("book_view", __name__)


class BooksIndexView(MethodView):
    """Landing view for the Books & Chapters section.

    With books present, redirect to the first book's detail page so the
    carousel + content render for a real selection. With no books, render the
    empty-state page with a create-book CTA.
    """

    def get(self, campaign_id: str) -> object:
        """Redirect to the first book or render the empty state."""
        campaign = fetch_campaign_or_404(campaign_id)
        session["last_campaign_id"] = campaign_id
        books = get_books_for_campaign(campaign_id)
        if not books:
            return catalog.render("book.BooksEmpty", campaign=campaign)
        return redirect(
            url_for("book_view.book_detail", campaign_id=campaign_id, book_id=books[0].id)
        )


class BookDetailView(MethodView):
    """Book detail page and edit functionality."""

    def get(
        self,
        campaign_id: str,
        book_id: str,
        action: str | None = None,
    ) -> str:
        """Render the book detail page, or the edit form fragment when action=edit."""
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
        session["last_campaign_id"] = campaign_id

        books_service = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=user_id, company_id=session["company_id"]
        )
        assets = books_service.list_all_assets(book.id)

        chapters = get_chapters_for_book(book_id)
        note_count = count_notes(books_service, book_id)
        all_books = get_books_for_campaign(campaign_id)

        return catalog.render(
            "book.BookDetail",
            book=book,
            campaign=campaign,
            chapters=chapters,
            all_books=all_books,
            assets=assets,
            note_count=note_count,
        )

    def post(
        self,
        campaign_id: str,
        book_id: str,
        action: str | None = None,  # noqa: ARG002
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

        books_service = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=user_id, company_id=session["company_id"]
        )
        updated_book = books_service.update(book_id, name=name, description=description)
        if number != book.number:
            updated_book = books_service.renumber(book_id, number)
        clear_global_context_cache(session["company_id"], session["user_id"])

        assets = books_service.list_all_assets(book_id)
        chapters = get_chapters_for_book(book_id)
        note_count = count_notes(books_service, book_id)

        return _render_book_card(
            book=updated_book,
            campaign=campaign,
            assets=assets,
            chapters=chapters,
            note_count=note_count,
        )

    def delete(
        self,
        campaign_id: str,
        book_id: str,
        action: str | None = None,  # noqa: ARG002
    ) -> object:
        """Delete the book and redirect the client to the books landing page."""
        if not can_manage_campaign():
            abort(403)

        book, _ = fetch_book_or_404(campaign_id, book_id)
        user_id = session.get("user_id", "")

        books_service = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=user_id, company_id=session["company_id"]
        )
        books_service.delete(book.id)
        clear_global_context_cache(session["company_id"], session["user_id"])

        return hx_redirect(url_for("book_view.books_index", campaign_id=campaign_id))


class BookImageUploadView(MethodView):
    """Upload an image asset for a book."""

    def post(self, campaign_id: str, book_id: str) -> object:
        """Handle a multipart image upload, validate, persist, and re-render the Story partial."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        if not can_manage_campaign():
            abort(403)

        user_id = session.get("user_id", "")
        books_service = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=user_id, company_id=session["company_id"]
        )

        assets = upload_and_append_asset(
            svc=books_service, parent_id=book_id, file=request.files.get("image")
        )
        chapters = get_chapters_for_book(book_id)
        note_count = count_notes(books_service, book_id)
        content_html = _render_book_card(
            book=book,
            campaign=campaign,
            assets=assets,
            chapters=chapters,
            note_count=note_count,
        )
        return htmx_response_with_flash(content_html)


class BookImageDeleteView(MethodView):
    """Delete an image asset from a book."""

    def delete(self, campaign_id: str, book_id: str, asset_id: str) -> object:
        """Delete the asset and re-render the book content card."""
        book, campaign = fetch_book_or_404(campaign_id, book_id)
        if not can_manage_campaign():
            abort(403)

        user_id = session.get("user_id", "")
        books_service = sync_books_service(
            campaign_id=campaign_id, on_behalf_of=user_id, company_id=session["company_id"]
        )

        handle_image_delete(svc=books_service, parent_id=book_id, asset_id=asset_id)

        assets = books_service.list_all_assets(book_id)
        chapters = get_chapters_for_book(book_id)
        note_count = count_notes(books_service, book_id)
        content_html = _render_book_card(
            book=book,
            campaign=campaign,
            assets=assets,
            chapters=chapters,
            note_count=note_count,
        )
        return htmx_response_with_flash(content_html)


bp.add_url_rule(
    "/campaign/<campaign_id>/books",
    view_func=BooksIndexView.as_view("books_index"),
    methods=["GET"],
)

_book_detail_view = BookDetailView.as_view("book_detail")
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>",
    view_func=_book_detail_view,
    defaults={"action": None},
    methods=["GET", "POST", "DELETE"],
)
bp.add_url_rule(
    "/campaign/<campaign_id>/book/<book_id>/<action>",
    view_func=BookDetailView.as_view("book_detail_action"),
    methods=["GET", "POST"],
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
