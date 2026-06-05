"""Tests for book view routes."""

from __future__ import annotations

import pytest
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
)
from werkzeug.exceptions import NotFound

from tests.conftest import get_csrf
from tests.helpers import build_global_context


@pytest.fixture
def mock_campaign():
    """Build a factory campaign."""
    return CampaignFactory.build(id="camp-1")


@pytest.fixture
def mock_book():
    """Build a factory book."""
    return CampaignBookFactory.build(
        id="book-1",
        campaign_id="camp-1",
        name="The Gathering Storm",
        number=1,
        description="A tale of beginnings.",
    )


@pytest.fixture
def mock_chapters():
    """Build factory chapters."""
    return [
        CampaignChapterFactory.build(id="ch-1", book_id="book-1", number=1, name="Chapter One"),
        CampaignChapterFactory.build(id="ch-2", book_id="book-1", number=2, name="Chapter Two"),
    ]


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
def _mock_books_service(mocker) -> None:
    """Mock the books service so list_all_assets does not hit the API."""
    svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
    svc.list_all_assets.return_value = []


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
        self, client, mocker, mock_book, mock_campaign
    ) -> None:
        """Verify updating a book invalidates the campaign's book-list cache."""
        # Given a privileged user and a patched cache-clear
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        clear_cache = mocker.patch("vweb.lib.cache.campaign_content.clear")
        csrf = get_csrf(client)

        # When submitting the book edit form
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}",
            data={"name": "Updated Name", "csrf_token": csrf},
        )

        # Then the campaign's book cache is invalidated
        _, kwargs = clear_cache.call_args
        assert kwargs["campaign_id"] == mock_campaign.id


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

    def test_create_redirects_to_new_book(self, client, mocker, mock_campaign) -> None:
        """Verify a successful create responds with HX-Redirect to the new book."""
        # Given a privileged user and a books service returning the new book
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
        svc.create.return_value = CampaignBookFactory.build(
            id="book-new", campaign_id=mock_campaign.id, name="New Book"
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
        svc.create.assert_called_once_with(name="New Book", description="A fresh start")

    def test_create_clears_caches(self, client, mocker, mock_campaign) -> None:
        """Verify creating a book invalidates the global-context and book-list caches."""
        # Given a privileged user and patched cache-clears
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
        svc.create.return_value = CampaignBookFactory.build(
            id="book-new", campaign_id=mock_campaign.id
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

    def test_empty_name_rerenders_form_with_error(self, client, mocker, mock_campaign) -> None:
        """Verify an empty name re-renders the form with an error and no create call."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
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
        svc.create.assert_not_called()

    def test_blank_description_creates_with_none(self, client, mocker, mock_campaign) -> None:
        """Verify a blank description is sent as None (vclient rejects empty strings)."""
        # Given a privileged user and a books service returning the new book
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
        svc.create.return_value = CampaignBookFactory.build(
            id="book-new", campaign_id=mock_campaign.id
        )
        csrf = get_csrf(client)

        # When submitting with the description left blank
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "New Book", "description": "", "csrf_token": csrf},
        )

        # Then the book is created with description=None (not an empty string)
        assert response.status_code == 200
        svc.create.assert_called_once_with(name="New Book", description=None)

    def test_short_name_rerenders_with_error(self, client, mocker, mock_campaign) -> None:
        """Verify a name shorter than the API minimum re-renders with an error, no create."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        svc = mocker.patch("vweb.routes.book.views.sync_books_service").return_value
        csrf = get_csrf(client)

        # When submitting a 2-character name
        response = client.post(
            f"/campaign/{mock_campaign.id}/books/create",
            data={"name": "Ab", "csrf_token": csrf},
        )

        # Then the form re-renders with a length error and nothing is created
        assert response.status_code == 200
        assert b"between 3 and 50" in response.data
        svc.create.assert_not_called()


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
