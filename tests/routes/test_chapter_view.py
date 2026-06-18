"""Tests for chapter view routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import CampaignChapterFactory

from tests.conftest import get_csrf
from tests.helpers import build_global_context

if TYPE_CHECKING:
    from vclient.models import CampaignChapter


@pytest.fixture
def chapters_service(_mock_chapter_lookup) -> object:
    """Return the chapters service mock from _mock_chapter_lookup for assertion-based tests."""
    return _mock_chapter_lookup


@pytest.fixture
def _mock_chapter_lookup(mocker, mock_book, mock_campaign, mock_chapters) -> None:
    """Mock book lookup, chapter lookup, and chapters service for chapter detail."""
    mocker.patch(
        "vweb.routes.chapter.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )

    def _fetch_chapter(campaign_id: str, book_id: str, chapter_id: str) -> CampaignChapter:
        return next((c for c in mock_chapters if c.id == chapter_id), mock_chapters[1])

    mocker.patch(
        "vweb.routes.chapter.views.fetch_chapter_or_404",
        side_effect=_fetch_chapter,
    )
    mocker.patch(
        "vweb.lib.cache.campaign_content.chapters",
        return_value=mock_chapters,
    )
    chapters_service = mocker.patch("vweb.routes.chapter.views.sync_chapters_service").return_value
    chapters_service.list_all.return_value = mock_chapters
    chapters_service.list_all_assets.return_value = []
    chapters_service.list_all_notes.return_value = []
    chapters_service.create.return_value = CampaignChapterFactory.build(
        id="ch-new", book_id="book-1", number=4, name="New Chapter"
    )
    return chapters_service


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterDetailGet:
    """Tests for chapter detail GET route."""

    def test_returns_200(self, client, mock_campaign, mock_book) -> None:
        """Verify chapter detail page returns 200."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")
        assert response.status_code == 200

    def test_contains_chapter_title(self, client, mock_campaign, mock_book) -> None:
        """Verify chapter name appears in the response."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")
        assert b"Chapter Two" in response.data

    def test_carousel_links_to_sibling_chapters(self, client, mock_campaign, mock_book) -> None:
        """Verify the chapter carousel renders anchors to sibling chapters."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")
        assert b"chapter/ch-1" in response.data
        assert b"chapter/ch-3" in response.data


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterEditPermissions:
    """Tests for chapter edit permission checks."""

    def test_non_privileged_get_edit_returns_403(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Non-privileged users cannot access chapter edit form."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=False)
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/edit")
        assert response.status_code == 403

    def test_non_privileged_post_edit_returns_403(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Non-privileged users cannot submit chapter edit form."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/edit",
            data={"name": "New", "csrf_token": csrf},
        )
        assert response.status_code == 403


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterCreate:
    """Tests for chapter create route."""

    def test_non_privileged_returns_403(self, client, mocker, mock_campaign, mock_book) -> None:
        """Non-privileged users cannot create chapters."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter",
            data={"name": "New Chapter", "csrf_token": csrf},
        )
        assert response.status_code == 403

    def test_create_redirects_to_new_chapter(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify a successful create responds with HX-Redirect to the new chapter."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When submitting the create form
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter",
            data={"name": "New Chapter", "csrf_token": csrf},
        )

        # Then the client is redirected to the new chapter's detail page
        assert response.status_code == 200
        assert (
            response.headers.get("HX-Redirect")
            == f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-new"
        )

    def test_get_form_defaults_to_book_page_target(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify the create form defaults to the book page's chapters card target."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter")
        assert b'id="book-chapters-card"' in response.data

    def test_get_form_derives_chapter_target_from_from_chapter(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify from_chapter alone retargets the form to the chapter card and Cancel."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)

        # When fetching the form launched from a chapter page (from_chapter only)
        response = client.get(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter?from_chapter=ch-2"
        )

        # Then the swap target is derived as the chapter content card and Cancel restores ch-2
        assert b'id="chapter-content"' in response.data
        assert b"/chapter/ch-2" in response.data

    def test_get_form_ignores_client_supplied_target(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify a client-supplied target query param cannot reach the swap attributes."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)

        # When requesting the form with a bogus target and no from_chapter
        response = client.get(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter?target=evil%20x"
        )

        # Then the target is derived server-side (book chapters card) and the input is not reflected
        assert b'id="book-chapters-card"' in response.data
        assert b"evil" not in response.data

    def test_create_clears_campaign_content_cache(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify creating a chapter invalidates the book and campaign book-list caches."""
        # Given a privileged user and a patched cache-clear
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        clear_cache = mocker.patch("vweb.lib.cache.campaign_content.clear")
        csrf = get_csrf(client)

        # When creating a chapter
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter",
            data={"name": "New Chapter", "csrf_token": csrf},
        )

        # Then both the book's chapter cache and the campaign's book-list cache
        # are invalidated so each book's num_chapters facet refreshes
        _, kwargs = clear_cache.call_args
        assert kwargs["book_id"] == mock_book.id
        assert kwargs["campaign_id"] == mock_campaign.id


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterDelete:
    """Tests for chapter delete route."""

    def test_non_privileged_returns_403(self, client, mocker, mock_campaign, mock_book) -> None:
        """Non-privileged users cannot delete chapters."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)
        response = client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-1",
            headers={"X-CSRFToken": csrf},
        )
        assert response.status_code == 403

    def test_delete_redirects_to_book_page(
        self, client, mocker, mock_campaign, mock_book, mock_chapters
    ) -> None:
        """Privileged delete redirects back to the parent book page via HX-Redirect."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)
        response = client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-1",
            headers={"X-CSRFToken": csrf},
        )
        assert response.status_code == 200
        assert (
            response.headers.get("HX-Redirect")
            == f"/campaign/{mock_campaign.id}/book/{mock_book.id}"
        )

    def test_delete_clears_campaign_content_cache(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify deleting a chapter invalidates the book and campaign book-list caches."""
        # Given a privileged user and a patched cache-clear
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        clear_cache = mocker.patch("vweb.lib.cache.campaign_content.clear")
        csrf = get_csrf(client)

        # When deleting the chapter
        client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-1",
            headers={"X-CSRFToken": csrf},
        )

        # Then both the book's chapter cache and the campaign's book-list cache
        # are invalidated so each book's num_chapters facet refreshes
        _, kwargs = clear_cache.call_args
        assert kwargs["book_id"] == mock_book.id
        assert kwargs["campaign_id"] == mock_campaign.id


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterCharacterAssociations:
    """Tests for associating characters via the chapter create/edit forms."""

    def test_create_forwards_character_ids(
        self, client, mocker, mock_campaign, mock_book, chapters_service
    ) -> None:
        """Verify selected character ids are forwarded to the create call."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When creating a chapter with two selected characters
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter",
            data={"name": "New Chapter", "character_ids": ["c1", "c2"], "csrf_token": csrf},
        )

        # Then the ids are passed through to vclient create
        _, kwargs = chapters_service.create.call_args
        assert kwargs["character_ids"] == ["c1", "c2"]

    def test_edit_forwards_character_ids(
        self, client, mocker, mock_campaign, mock_book, chapters_service
    ) -> None:
        """Verify the chapter edit form forwards the selected ids to update."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When submitting the edit form with one selected character
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/edit",
            data={"name": "Chapter Two", "character_ids": ["c9"], "csrf_token": csrf},
        )

        # Then the id list is passed to vclient update
        _, kwargs = chapters_service.update.call_args
        assert kwargs["character_ids"] == ["c9"]

    def test_edit_clears_associations_when_none_selected(
        self, client, mocker, mock_campaign, mock_book, chapters_service
    ) -> None:
        """Verify submitting the edit form with no characters clears associations."""
        # Given a privileged user
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)

        # When submitting the edit form with no character_ids
        client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/edit",
            data={"name": "Chapter Two", "csrf_token": csrf},
        )

        # Then an empty list is passed to clear all associations
        _, kwargs = chapters_service.update.call_args
        assert kwargs["character_ids"] == []

    def test_edit_invalid_character_id_rerenders_form(
        self, client, mocker, mock_campaign, mock_book, chapters_service
    ) -> None:
        """Verify a server-rejected character id re-renders the form, not a 500."""
        # Given a privileged user and an update that the API rejects
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        from vclient.exceptions import ValidationError

        chapters_service.update.side_effect = ValidationError(
            "bad",
            response_data={
                "detail": "unknown character",
                "invalid_parameters": [{"field": "character_ids", "message": "unknown character"}],
            },
        )
        csrf = get_csrf(client)

        # When submitting with an invalid character id
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/edit",
            data={"name": "Chapter Two", "character_ids": ["nope"], "csrf_token": csrf},
        )

        # Then the form is re-rendered with an error and no 500 is raised
        assert response.status_code == 200
        assert b"chapter-content" in response.data


class TestChapterSidebarCharacters:
    """Tests for associated-character links in the chapter sidebar."""

    def test_sidebar_links_associated_characters(
        self, client, mocker, mock_campaign, mock_book
    ) -> None:
        """Verify the chapter sidebar renders a link to each associated character."""
        # Given a campaign whose roster contains the associated character
        from vclient.testing import CampaignChapterFactory, CharacterFactory

        hero = CharacterFactory.build(
            id="hero-1", type="PLAYER", name="Sidebar Hero", campaign_id=mock_campaign.id
        )
        ctx = build_global_context(user_role="PLAYER", campaign=mock_campaign, characters=[hero])
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        chapter = CampaignChapterFactory.build(
            id="ch-2", book_id=mock_book.id, number=2, name="Chapter Two", character_ids=["hero-1"]
        )
        mocker.patch("vweb.routes.chapter.views.fetch_chapter_or_404", return_value=chapter)
        mocker.patch(
            "vweb.routes.chapter.views.fetch_book_or_404", return_value=(mock_book, mock_campaign)
        )
        svc = mocker.patch("vweb.routes.chapter.views.sync_chapters_service").return_value
        svc.list_all_assets.return_value = []
        svc.list_all_notes.return_value = []
        mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=[chapter])

        # When viewing the chapter
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")

        # Then the sidebar links to the character detail page
        assert b"Sidebar Hero" in response.data
        assert b"/character/hero-1" in response.data


@pytest.mark.usefixtures("_mock_chapter_lookup")
class TestChapterCarouselAddCard:
    """Tests for the create-chapter add-card in the chapter carousel."""

    def test_add_card_visible_for_manager(self, client, mocker, mock_campaign, mock_book) -> None:
        """Verify managers see the New Chapter add-card in the carousel."""
        # Given a storyteller user
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When rendering a chapter detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")

        # Then the add-card renders the create-form URL scoped to the current chapter
        assert b"New Chapter" in response.data
        assert b"/book/book-1/chapter?from_chapter=ch-2" in response.data

    def test_add_card_hidden_for_player(self, client, mock_campaign, mock_book) -> None:
        """Verify players do not see the New Chapter add-card."""
        # Given the default PLAYER user, when rendering a chapter detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")

        # Then no create affordance renders
        assert b"New Chapter" not in response.data
        assert b"from_chapter=ch-2" not in response.data
