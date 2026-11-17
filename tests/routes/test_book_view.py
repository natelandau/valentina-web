"""Tests for book view routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from werkzeug.exceptions import NotFound

from tests.conftest import get_csrf
from tests.helpers import build_global_context
from vweb.api_client.testing import CampaignBookFactory, Routes

if TYPE_CHECKING:
    from collections.abc import Callable

    from werkzeug.test import TestResponse

    from vweb.api_client.models import CampaignBook


@pytest.fixture
def _mock_book_lookup(mocker, mock_book, mock_campaign) -> None:
    """Mock the book/campaign lookup."""
    mocker.patch(
        "vweb.routes.book.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )


@pytest.fixture
def _mock_chapters_service(mocker, mock_chapters) -> None:
    """Mock the chapter lookup for book detail page."""
    mocker.patch(
        "vweb.lib.cache.campaign_content.chapters",
        return_value=mock_chapters,
    )


@pytest.fixture(autouse=True)
def _mock_books_service(fake_vclient) -> None:
    """Serve an empty asset list so book pages render without images."""
    fake_vclient.set_response(Routes.BOOKS_ASSETS_LIST, items=[])


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookDetailGet:
    """Tests for book detail GET route."""

    def test_returns_200(self, client, mock_book, mock_campaign) -> None:
        """Verify book detail page returns 200."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")
        assert response.status_code == 200

    def test_contains_book_title(self, client, mock_book, mock_campaign) -> None:
        """Verify book name appears in the response."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")
        assert mock_book.name.encode() in response.data

    def test_contains_chapter_list(self, client, mock_book, mock_campaign, mock_chapters) -> None:
        """Verify chapter names appear in the response."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")
        for ch in mock_chapters:
            assert ch.name.encode() in response.data

    def test_book_not_found_returns_404(self, client, mocker) -> None:
        """Verify 404 when book is not found."""
        mocker.patch(
            "vweb.routes.book.views.fetch_book_or_404",
            side_effect=NotFound(),
        )
        response = client.get("/campaign/camp-1/book/nonexistent")
        assert response.status_code == 404


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookCarouselChapterCount:
    """Tests for the carousel chapter count sourced from book.num_chapters."""

    def test_carousel_uses_num_chapters_facet(
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """Verify the carousel renders the chapter count from book.num_chapters."""
        # Given a book carrying a num_chapters facet from the API
        book_with_count = CampaignBookFactory.build(
            id="book-1",
            campaign_id="camp-1",
            name="The Gathering Storm",
            number=1,
            num_chapters=4,
        )
        mocker.patch(
            "vweb.lib.cache.campaign_content.books",
            return_value=[book_with_count],
        )

        # When rendering the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")

        # Then the carousel shows the facet count, not a per-book fetch
        assert b"4 chapter" in response.data


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookEditPermissions:
    """Tests for book edit permission checks."""

    def test_non_privileged_get_edit_returns_403(
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """Non-privileged users cannot access edit form."""
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=False)
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/edit")
        assert response.status_code == 403

    def test_non_privileged_post_edit_returns_403(
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """Non-privileged users cannot submit edit form."""
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/edit",
            data={"name": "New Name", "csrf_token": csrf},
        )
        assert response.status_code == 403

    def test_privileged_can_access_edit_form(
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """ADMIN/STORYTELLER users can access edit form."""
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/edit")
        assert response.status_code == 200

    def test_edit_form_keeps_card_outline(self, client, mocker, mock_book, mock_campaign) -> None:
        """Verify the edit form wrapper carries the surface-card styling."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)

        # When fetching the edit form fragment
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/edit")

        # Then the swap wrapper keeps the card outline
        assert b'id="book-content" class="surface-card"' in response.data


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookUpdate:
    """Tests for book update cache invalidation."""

    def test_update_clears_campaign_content_cache(
        self, client, mocker, fake_vclient, mock_book, mock_campaign
    ) -> None:
        """Verify updating a book invalidates the campaign's book-list cache."""
        # Given a privileged user and a patched cache-clear
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        clear_cache = mocker.patch("vweb.lib.cache.campaign_content.clear")
        csrf = get_csrf(client)

        # When submitting the book edit form
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}",
            data={"name": "Updated Name", "description": "A new tale", "csrf_token": csrf},
        )

        # Then the book is updated and the campaign's book cache is invalidated
        fake_vclient.assert_called(
            Routes.BOOKS_UPDATE,
            params={"campaign_id": mock_campaign.id, "book_id": mock_book.id},
            json_subset={"name": "Updated Name", "description": "A new tale"},
        )
        _, kwargs = clear_cache.call_args
        assert kwargs["campaign_id"] == mock_campaign.id


class TestBookUpdateValidation:
    """Tests for book edit form validation."""

    @pytest.fixture(autouse=True)
    def _privileged(self, mocker) -> None:
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)

    @pytest.fixture
    def post_edit(self, client, mocker, mock_campaign) -> Callable[..., TestResponse]:
        """Return a function that posts the edit form for a given book."""

        def _post(book: CampaignBook, **form: str) -> TestResponse:
            mocker.patch(
                "vweb.routes.book.views.fetch_book_or_404", return_value=(book, mock_campaign)
            )
            return client.post(
                f"/campaign/{mock_campaign.id}/book/{book.id}",
                data={"number": str(book.number), **form, "csrf_token": get_csrf(client)},
            )

        return _post

    @pytest.mark.parametrize(
        ("name", "description", "expected_body"),
        [
            ("New Name", "", {"name": "New Name", "description": ""}),
            ("ab", "ab", {"name": "ab", "description": "ab"}),
        ],
    )
    def test_saves_short_values_and_cleared_description(
        self, post_edit, fake_vclient, mock_book, name, description, expected_body
    ) -> None:
        """Verify short values and a cleared description reach the API, which accepts them."""
        # Given a book that has a description
        assert mock_book.description

        # When saving the form
        response = post_edit(mock_book, name=name, description=description)

        # Then the submitted values are sent, with an empty description to clear it
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.BOOKS_UPDATE, params={"book_id": mock_book.id}, json=expected_body, times=1
        )

    @pytest.mark.parametrize(
        ("name", "message"),
        [("", "Name is required"), ("x" * 51, "Name must be 50 characters or fewer")],
    )
    def test_invalid_name_rerenders_form_without_calling_api(
        self, post_edit, fake_vclient, mock_book, name, message
    ) -> None:
        """Verify a missing or too long name shows a form error."""
        # When saving the form with an invalid name
        response = post_edit(mock_book, name=name, description="A fine tale")

        # Then the form shows the error and nothing reaches the API
        assert response.status_code == 200
        assert message in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.BOOKS_UPDATE)

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
        response = post_edit(mock_book, name="Taken Name", description=mock_book.description)

        # Then the form shows the API's reason
        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)

    def test_number_below_one_rerenders_form_without_calling_api(
        self, post_edit, fake_vclient, mock_book
    ) -> None:
        """Verify a number below 1 shows a form error before the name is saved."""
        # When saving the form with a new name and number 0
        response = post_edit(
            mock_book, name="New Name", description=mock_book.description, number="0"
        )

        # Then the form shows the error and nothing reaches the API
        assert response.status_code == 200
        assert "Number must be 1 or greater" in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.BOOKS_UPDATE)
        fake_vclient.assert_not_called(Routes.BOOKS_RENUMBER)

    def test_number_only_change_renumbers_without_updating(
        self, post_edit, fake_vclient, mock_book
    ) -> None:
        """Verify changing only the number skips the name and description update."""
        # When saving the form with only a new number
        response = post_edit(
            mock_book,
            name=mock_book.name,
            description=mock_book.description,
            number=str(mock_book.number + 1),
        )

        # Then only the renumber call reaches the API
        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.BOOKS_UPDATE)
        fake_vclient.assert_called(
            Routes.BOOKS_RENUMBER,
            params={"book_id": mock_book.id},
            json_subset={"number": mock_book.number + 1},
            times=1,
        )


@pytest.fixture
def _mock_campaign_lookup(mocker, mock_campaign) -> None:
    """Mock the campaign lookup used by the books index and create views."""
    mocker.patch(
        "vweb.routes.book.views.fetch_campaign_or_404",
        return_value=mock_campaign,
    )


@pytest.mark.usefixtures("_mock_campaign_lookup")
class TestBookCreateGet:
    """Tests for the book create form GET route."""

    def test_non_privileged_returns_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-privileged users cannot fetch the create form."""
        # Given a non-privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=False)

        # When fetching the create form
        response = client.get(f"/campaign/{mock_campaign.id}/books/create")

        # Then access is forbidden
        assert response.status_code == 403

    def test_privileged_gets_form(self, client, mocker, mock_campaign) -> None:
        """Verify managers receive the create form with an index cancel target."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)

        # When fetching the create form without a from_book param
        response = client.get(f"/campaign/{mock_campaign.id}/books/create")

        # Then the form renders and Cancel restores the books index
        assert response.status_code == 200
        assert b"Create Book" in response.data
        assert f'hx-get="/campaign/{mock_campaign.id}/books"'.encode() in response.data

    def test_from_book_changes_cancel_target(self, client, mocker, mock_campaign) -> None:
        """Verify from_book points Cancel back at that book's detail page."""
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        response = client.get(f"/campaign/{mock_campaign.id}/books/create?from_book=book-9")
        assert f"/campaign/{mock_campaign.id}/book/book-9".encode() in response.data


@pytest.mark.usefixtures("_mock_campaign_lookup")
class TestBookCreatePost:
    """Tests for the book create POST route."""

    def test_non_privileged_returns_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-privileged users cannot create books."""
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "New Book", "csrf_token": csrf},
        )
        assert response.status_code == 403

    def test_create_redirects_to_new_book(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify a successful create responds with HX-Redirect to the new book."""
        # Given a privileged user and an API returning the new book
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        fake_vclient.set_response(
            Routes.BOOKS_CREATE,
            model=CampaignBookFactory.build(
                id="book-new", campaign_id=mock_campaign.id, name="New Book"
            ),
        )
        csrf = get_csrf(client)

        # When submitting the create form
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "New Book", "description": "A fresh start", "csrf_token": csrf},
        )

        # Then the book is created and the client is redirected to it
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == f"/campaign/{mock_campaign.id}/book/book-new"
        fake_vclient.assert_called(
            Routes.BOOKS_CREATE,
            params={"campaign_id": mock_campaign.id},
            json={"name": "New Book", "description": "A fresh start"},
            times=1,
        )

    def test_create_clears_caches(self, client, mocker, fake_vclient, mock_campaign) -> None:
        """Verify creating a book invalidates the global-context and book-list caches."""
        # Given a privileged user and patched cache-clears
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        fake_vclient.set_response(
            Routes.BOOKS_CREATE,
            model=CampaignBookFactory.build(id="book-new", campaign_id=mock_campaign.id),
        )
        clear_content = mocker.patch("vweb.lib.cache.campaign_content.clear")
        clear_context = mocker.patch("vweb.lib.cache.global_context.clear")
        csrf = get_csrf(client)

        # When creating a book
        client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "New Book", "csrf_token": csrf},
        )

        # Then the campaign's book-list cache and the global context are invalidated
        _, kwargs = clear_content.call_args
        assert kwargs["campaign_id"] == mock_campaign.id
        clear_context.assert_called_once()

    def test_empty_name_rerenders_form_with_error(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify an empty name re-renders the form with an error and no create call."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When submitting an empty name
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "   ", "csrf_token": csrf},
        )

        # Then the form re-renders with the error and nothing is created
        assert response.status_code == 200
        assert b"Name is required" in response.data
        assert b"Create Book" in response.data
        fake_vclient.assert_not_called(Routes.BOOKS_CREATE)

    def test_api_rejection_rerenders_form_with_its_reason(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify a validation error from the API shows on the create form."""
        # Given a privileged user and an API that rejects the name
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        fake_vclient.set_error(
            Routes.BOOKS_CREATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        # When submitting the form
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "Taken Name", "csrf_token": get_csrf(client)},
        )

        # Then the form shows the API's reason
        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)

    def test_blank_description_creates_with_none(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify a blank description is omitted rather than sent as an empty string."""
        # Given a privileged user and an API returning the new book
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        fake_vclient.set_response(
            Routes.BOOKS_CREATE,
            model=CampaignBookFactory.build(id="book-new", campaign_id=mock_campaign.id),
        )
        csrf = get_csrf(client)

        # When submitting with the description left blank
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "New Book", "description": "", "csrf_token": csrf},
        )

        # Then the book is created without a description (not an empty string)
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.BOOKS_CREATE,
            params={"campaign_id": mock_campaign.id},
            json={"name": "New Book"},
            times=1,
        )

    def test_long_name_rerenders_with_error(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify a name longer than the API maximum re-renders with an error, no create."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When submitting a 51-character name
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "x" * 51, "csrf_token": csrf},
        )

        # Then the form re-renders with a length error and nothing is created
        assert response.status_code == 200
        assert b"50 characters or fewer" in response.data
        fake_vclient.assert_not_called(Routes.BOOKS_CREATE)


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookDelete:
    """Tests for book delete cache invalidation."""

    def test_delete_clears_campaign_content_cache(
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """Verify deleting a book invalidates the campaign's book-list cache."""
        # Given a privileged user and a patched cache-clear
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        clear_cache = mocker.patch("vweb.lib.cache.campaign_content.clear")
        csrf = get_csrf(client)

        # When deleting the book
        client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}",
            headers={"X-CSRFToken": csrf},
        )

        # Then both the campaign's book cache and the deleted book's chapters cache
        # are invalidated
        _, kwargs = clear_cache.call_args
        assert kwargs["campaign_id"] == mock_campaign.id
        assert kwargs["book_id"] == mock_book.id


@pytest.mark.usefixtures("_mock_campaign_lookup")
class TestBooksEmptyState:
    """Tests for the no-books empty state."""

    def test_create_button_live_for_manager(self, client, mocker, mock_campaign) -> None:
        """Verify the empty-state CTA fetches the create form for managers."""
        # Given a storyteller and a campaign with no books
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[])

        # When rendering the books index
        response = client.get(f"/campaign/{mock_campaign.id}/books")

        # Then the CTA is live and the placeholder caption is gone
        assert response.status_code == 200
        assert b"/books/create" in response.data
        assert b'id="book-content"' in response.data
        assert b"coming soon" not in response.data

    def test_create_button_hidden_for_player(self, client, mocker, mock_campaign) -> None:
        """Verify players see no create affordance on the empty state."""
        # Given the default PLAYER user and no books
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[])

        # When rendering the books index
        response = client.get(f"/campaign/{mock_campaign.id}/books")

        # Then no create affordance renders
        assert b"/books/create" not in response.data


class TestBookSidebarCharacters:
    """Tests for associated-character links in the book sidebar."""

    def test_sidebar_links_associated_characters(
        self, client, mocker, mock_campaign, mock_chapters
    ) -> None:
        """Verify the book sidebar renders a link to each associated character."""
        from vweb.api_client.testing import CharacterFactory

        # Given a campaign whose roster contains the associated character
        hero = CharacterFactory.build(
            id="hero-1", type="PLAYER", name="Sidebar Hero", campaign_id=mock_campaign.id
        )
        ctx = build_global_context(user_role="PLAYER", campaign=mock_campaign, characters=[hero])
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        book = CampaignBookFactory.build(
            id="book-1",
            campaign_id=mock_campaign.id,
            name="The Gathering Storm",
            number=1,
            character_ids=["hero-1"],
        )
        mocker.patch(
            "vweb.routes.book.views.fetch_book_or_404",
            return_value=(book, mock_campaign),
        )
        mocker.patch(
            "vweb.lib.cache.campaign_content.chapters",
            return_value=mock_chapters,
        )

        # When viewing the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{book.id}")

        # Then the sidebar links to the character detail page
        assert b"Sidebar Hero" in response.data
        assert b"/character/hero-1" in response.data


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookCarouselAddCard:
    """Tests for the create-book add-card in the book carousel."""

    def test_add_card_visible_for_manager(self, client, mocker, mock_book, mock_campaign) -> None:
        """Verify managers see the New Book add-card in the carousel."""
        # Given a storyteller user
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When rendering the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")

        # Then the add-card renders with the create-form URL and current-book cancel hint
        assert b"New Book" in response.data
        assert b"/books/create" in response.data
        assert f"from_book={mock_book.id}".encode() in response.data

    def test_add_card_hidden_for_player(self, client, mock_book, mock_campaign) -> None:
        """Verify players do not see the New Book add-card."""
        # Given the default PLAYER user, when rendering the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")

        # Then no create affordance renders
        assert b"/books/create" not in response.data
