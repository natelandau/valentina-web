"""Tests for book view routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_post
from tests.helpers import assert_redirects_to
from vweb.api_client.testing import CampaignBookFactory, CharacterFactory, Routes
from vweb.lib.form_validation import name_errors, position_number

if TYPE_CHECKING:
    from collections.abc import Callable

    from werkzeug.test import TestResponse

    from vweb.api_client.models import Campaign, CampaignBook

BOOK_WRITE_ROUTES = (
    Routes.BOOKS_CREATE,
    Routes.BOOKS_UPDATE,
    Routes.BOOKS_RENUMBER,
    Routes.BOOKS_DELETE,
    Routes.BOOKS_ASSETS_DELETE,
)


@pytest.fixture
def set_books(mocker, mock_book) -> Callable[..., None]:
    """Return a function that sets the campaign's book list served by the content cache."""

    def _set(books: list[CampaignBook]) -> None:
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=books)

    _set([mock_book])
    return _set


@pytest.fixture(autouse=True)
def _book_content(set_role, set_books, mocker, fake_vclient, mock_chapters) -> None:
    """Serve one book with three chapters and no images to a player in the test campaign."""
    set_role("PLAYER")
    mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=mock_chapters)
    fake_vclient.set_response(Routes.BOOKS_ASSETS_LIST, items=[])


@pytest.fixture
def clear_content_cache(mocker):
    """Patch the campaign content cache clear so tests can check what it invalidates."""
    return mocker.patch("vweb.lib.cache.campaign_content.clear")


def _book_url(campaign: Campaign, book: CampaignBook, suffix: str = "") -> str:
    return f"/campaign/{campaign.id}/book/{book.id}{suffix}"


class TestBookDetail:
    """Tests for the book detail page."""

    def test_shows_book_and_its_chapters(
        self, client, mock_book, mock_campaign, mock_chapters
    ) -> None:
        """Verify the page shows the book, each chapter, and remembers the campaign."""
        # When viewing the book
        response = client.get(_book_url(mock_campaign, mock_book))

        # Then the book and every chapter are shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert mock_book.name in body
        for chapter in mock_chapters:
            assert chapter.name in body

        # And the campaign is remembered for navigation
        with client.session_transaction() as sess:
            assert sess["last_campaign_id"] == mock_campaign.id

    def test_carousel_shows_chapter_count_from_book(
        self, client, set_books, mock_book, mock_campaign
    ) -> None:
        """Verify the carousel shows the book's num_chapters facet rather than counting fetches."""
        # Given a book carrying a num_chapters facet from the API
        set_books([CampaignBookFactory.build(id=mock_book.id, number=1, num_chapters=4)])

        # When viewing the book
        response = client.get(_book_url(mock_campaign, mock_book))

        # Then the facet count is shown
        assert b"4 chapter" in response.data

    def test_sidebar_links_associated_characters(
        self, client, set_role, set_books, mock_campaign
    ) -> None:
        """Verify the sidebar links to each character associated with the book."""
        # Given a book associated with a character on the campaign roster
        hero = CharacterFactory.build(
            id="hero-1", name="Sidebar Hero", campaign_id=mock_campaign.id
        )
        set_role("PLAYER", characters=[hero])
        book = CampaignBookFactory.build(id="book-1", number=1, character_ids=["hero-1"])
        set_books([book])

        # When viewing the book
        response = client.get(_book_url(mock_campaign, book))

        # Then the sidebar links to the character
        assert b"Sidebar Hero" in response.data
        assert b"/character/hero-1" in response.data

    @pytest.mark.parametrize(("role", "shows_add_card"), [("STORYTELLER", True), ("PLAYER", False)])
    def test_new_book_card_only_for_managers(
        self, client, set_role, mock_book, mock_campaign, role, shows_add_card
    ) -> None:
        """Verify only campaign managers get the carousel card that opens the create form."""
        # Given a user with the role
        set_role(role)

        # When viewing the book
        response = client.get(_book_url(mock_campaign, mock_book))

        # Then the create form link, which returns to this book on cancel, shows only to managers
        body = response.get_data(as_text=True)
        assert ("/books/create" in body) is shows_add_card
        assert (f"from_book={mock_book.id}" in body) is shows_add_card


class TestBooksIndex:
    """Tests for the books landing page."""

    def test_redirects_to_first_book(self, client, set_books, mock_campaign) -> None:
        """Verify the landing page opens the campaign's first book."""
        # Given a campaign with two books
        first, second = CampaignBookFactory.batch(2)
        set_books([first, second])

        # When opening the books landing page
        response = client.get(f"/campaign/{mock_campaign.id}/books")

        # Then the user is sent to the first book
        assert_redirects_to(response, _book_url(mock_campaign, first))

    @pytest.mark.parametrize(("role", "shows_create"), [("STORYTELLER", True), ("PLAYER", False)])
    def test_empty_state_offers_create_only_to_managers(
        self, client, set_role, set_books, mock_campaign, role, shows_create
    ) -> None:
        """Verify a campaign with no books offers the create form only to managers."""
        # Given a campaign with no books
        set_role(role)
        set_books([])

        # When opening the books landing page
        response = client.get(f"/campaign/{mock_campaign.id}/books")

        # Then the create form link shows only to managers
        assert response.status_code == 200
        assert (b"/books/create" in response.data) is shows_create


class TestBookAccessControl:
    """Tests that players cannot manage books."""

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [
            ("get", "/books/create"),
            ("post", "/books/create"),
            ("get", "/book/book-1/edit"),
            ("post", "/book/book-1/edit"),
            ("post", "/book/book-1"),
            ("delete", "/book/book-1"),
            ("delete", "/book/book-1/images/asset-1"),
        ],
    )
    def test_player_is_forbidden(self, client, fake_vclient, mock_campaign, method, suffix) -> None:
        """Verify a player gets 403 and no book write reaches the API."""
        # When a player sends the request directly
        response = getattr(client, method)(
            f"/campaign/{mock_campaign.id}{suffix}",
            data={"name": "New Name", "csrf_token": get_csrf(client)},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then it is refused before any write
        assert response.status_code == 403
        for route in BOOK_WRITE_ROUTES:
            fake_vclient.assert_not_called(route)


@pytest.mark.usefixtures("storyteller")
class TestBookUpdate:
    """Tests for the book edit form."""

    @pytest.fixture
    def post_edit(self, client, mock_book, mock_campaign) -> Callable[..., TestResponse]:
        """Return a function that submits the edit form for the test book."""

        def _post(**form: str) -> TestResponse:
            return htmx_post(
                client,
                _book_url(mock_campaign, mock_book),
                {"number": str(mock_book.number), **form},
                htmx=False,
            )

        return _post

    def test_edit_form_is_prefilled(self, client, mock_book, mock_campaign) -> None:
        """Verify the edit form opens with the book's current name."""
        response = client.get(_book_url(mock_campaign, mock_book, "/edit"))

        assert response.status_code == 200
        assert mock_book.name in response.get_data(as_text=True)

    @pytest.mark.parametrize(
        ("name", "description", "expected_body"),
        [
            ("New Name", "", {"name": "New Name", "description": ""}),
            ("ab", "ab", {"name": "ab", "description": "ab"}),
        ],
        ids=["cleared-description", "short-values"],
    )
    def test_sends_changes_to_api(
        self, post_edit, fake_vclient, mock_book, name, description, expected_body
    ) -> None:
        """Verify short values and a cleared description reach the API, which accepts them."""
        # Given a book that has a description
        assert mock_book.description

        # When saving the form
        response = post_edit(name=name, description=description)

        # Then the submitted values are sent, with an empty description to clear it
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.BOOKS_UPDATE, params={"book_id": mock_book.id}, json=expected_body, times=1
        )

    def test_save_clears_campaign_book_cache(
        self, post_edit, clear_content_cache, mock_campaign
    ) -> None:
        """Verify saving a book invalidates the campaign's book list."""
        post_edit(name="Updated Name", description="A new tale")

        _, kwargs = clear_content_cache.call_args
        assert kwargs["campaign_id"] == mock_campaign.id

    @pytest.mark.parametrize(
        ("form", "error"),
        [
            ({"name": ""}, name_errors("")[0]),
            ({"name": "x" * 51}, name_errors("x" * 51)[0]),
            ({"name": "New Name", "number": "0"}, position_number("0", 1)[1]),
        ],
        ids=["empty-name", "long-name", "number-below-one"],
    )
    def test_invalid_input_rerenders_form_without_calling_api(
        self, post_edit, fake_vclient, form, error
    ) -> None:
        """Verify invalid input shows a form error and nothing reaches the API."""
        response = post_edit(description="A fine tale", **form)

        assert response.status_code == 200
        assert error in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.BOOKS_UPDATE)
        fake_vclient.assert_not_called(Routes.BOOKS_RENUMBER)

    def test_api_rejection_rerenders_form_with_its_reason(
        self, post_edit, fake_vclient, mock_book
    ) -> None:
        """Verify a validation error from the API shows on the form instead of a server error."""
        # Given an API that rejects the new name
        fake_vclient.set_error(
            Routes.BOOKS_UPDATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        # When saving the form
        response = post_edit(name="Taken Name", description=mock_book.description)

        # Then the form shows the API's reason
        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)

    def test_number_only_change_renumbers_without_updating(
        self, post_edit, fake_vclient, mock_book
    ) -> None:
        """Verify changing only the number skips the name and description update."""
        response = post_edit(
            name=mock_book.name,
            description=mock_book.description,
            number=str(mock_book.number + 1),
        )

        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.BOOKS_UPDATE)
        fake_vclient.assert_called(
            Routes.BOOKS_RENUMBER,
            params={"book_id": mock_book.id},
            json_subset={"number": mock_book.number + 1},
            times=1,
        )


@pytest.mark.usefixtures("storyteller")
class TestBookCreate:
    """Tests for the book create form."""

    @pytest.fixture
    def post_create(self, client, fake_vclient, mock_campaign) -> Callable[..., TestResponse]:
        """Return a function that submits the create form with the API returning a new book."""
        fake_vclient.set_response(
            Routes.BOOKS_CREATE,
            model=CampaignBookFactory.build(id="book-new", campaign_id=mock_campaign.id),
        )

        def _post(**form: str) -> TestResponse:
            return htmx_post(client, f"/campaign/{mock_campaign.id}/books/create", form, htmx=False)

        return _post

    @pytest.mark.parametrize(
        ("query", "cancel_path"), [("", "/books"), ("?from_book=book-9", "/book/book-9")]
    )
    def test_cancel_returns_to_launching_page(
        self, client, mock_campaign, query, cancel_path
    ) -> None:
        """Verify Cancel restores the books index, or the book the form was opened from."""
        response = client.get(f"/campaign/{mock_campaign.id}/books/create{query}")

        assert response.status_code == 200
        expected = f'hx-get="/campaign/{mock_campaign.id}{cancel_path}"'
        assert expected in response.get_data(as_text=True)

    @pytest.mark.parametrize(
        ("description", "expected_body"),
        [
            ("A fresh start", {"name": "New Book", "description": "A fresh start"}),
            ("", {"name": "New Book"}),
        ],
        ids=["with-description", "blank-description-omitted"],
    )
    def test_creates_book_and_redirects_to_it(
        self, post_create, fake_vclient, mock_campaign, description, expected_body
    ) -> None:
        """Verify the book is created and the client is sent to it."""
        response = post_create(name="New Book", description=description)

        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == f"/campaign/{mock_campaign.id}/book/book-new"
        fake_vclient.assert_called(
            Routes.BOOKS_CREATE,
            params={"campaign_id": mock_campaign.id},
            json=expected_body,
            times=1,
        )

    def test_create_clears_caches(self, post_create, mocker, mock_campaign) -> None:
        """Verify creating a book invalidates the global context and the campaign's book list."""
        clear_content = mocker.patch("vweb.lib.cache.campaign_content.clear")
        clear_context = mocker.patch("vweb.lib.cache.global_context.clear")

        post_create(name="New Book")

        _, kwargs = clear_content.call_args
        assert kwargs["campaign_id"] == mock_campaign.id
        clear_context.assert_called_once()

    @pytest.mark.parametrize("name", ["   ", "x" * 51], ids=["blank", "too-long"])
    def test_invalid_name_rerenders_form_without_calling_api(
        self, post_create, fake_vclient, name
    ) -> None:
        """Verify an invalid name shows a form error and nothing is created."""
        response = post_create(name=name)

        assert response.status_code == 200
        assert name_errors(name.strip())[0] in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.BOOKS_CREATE)

    def test_api_rejection_rerenders_form_with_its_reason(self, post_create, fake_vclient) -> None:
        """Verify a validation error from the API shows on the create form."""
        fake_vclient.set_error(
            Routes.BOOKS_CREATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        response = post_create(name="Taken Name")

        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)


@pytest.mark.usefixtures("storyteller")
class TestBookDelete:
    """Tests for deleting a book."""

    def test_deletes_book_and_redirects_to_index(
        self, client, fake_vclient, clear_content_cache, mock_book, mock_campaign
    ) -> None:
        """Verify the book is deleted, its caches are cleared, and the client goes to the index."""
        response = client.delete(
            _book_url(mock_campaign, mock_book), headers={"X-CSRFToken": get_csrf(client)}
        )

        assert response.headers.get("HX-Redirect") == f"/campaign/{mock_campaign.id}/books"
        fake_vclient.assert_called(
            Routes.BOOKS_DELETE,
            params={"campaign_id": mock_campaign.id, "book_id": mock_book.id},
            times=1,
        )
        _, kwargs = clear_content_cache.call_args
        assert kwargs["campaign_id"] == mock_campaign.id
        assert kwargs["book_id"] == mock_book.id
