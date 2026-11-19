"""Tests for chapter view routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_post
from vweb.api_client.testing import CampaignChapterFactory, CharacterFactory, Routes
from vweb.lib.form_validation import name_errors, position_number

if TYPE_CHECKING:
    from collections.abc import Callable

    from werkzeug.test import TestResponse

    from vweb.api_client.models import CampaignChapter

CHAPTER_WRITE_ROUTES = (
    Routes.CHAPTERS_CREATE,
    Routes.CHAPTERS_UPDATE,
    Routes.CHAPTERS_RENUMBER,
    Routes.CHAPTERS_DELETE,
    Routes.CHAPTERS_ASSETS_DELETE,
)

BOOK_URL = "/campaign/camp-1/book/book-1"


@pytest.fixture
def set_chapters(mocker, mock_chapters) -> Callable[[list[CampaignChapter]], None]:
    """Return a function that sets the book's chapter list served by the content cache."""

    def _set(chapters: list[CampaignChapter]) -> None:
        mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=chapters)

    _set(mock_chapters)
    return _set


@pytest.fixture(autouse=True)
def _chapter_content(set_role, set_chapters, mocker, fake_vclient, mock_book) -> None:
    """Serve one book with three chapters and no images to a player in the test campaign."""
    set_role("PLAYER")
    mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[mock_book])
    fake_vclient.set_response(Routes.CHAPTERS_ASSETS_LIST, items=[])
    fake_vclient.set_response(Routes.CHAPTERS_NOTES_LIST, items=[])
    fake_vclient.set_response(
        Routes.CHAPTERS_CREATE,
        model=CampaignChapterFactory.build(id="ch-new", book_id="book-1", number=4),
    )


@pytest.fixture
def clear_content_cache(mocker):
    """Patch the campaign content cache clear so tests can check what it invalidates."""
    return mocker.patch("vweb.lib.cache.campaign_content.clear")


class TestChapterDetail:
    """Tests for the chapter detail page."""

    def test_shows_chapter_and_links_siblings(self, client) -> None:
        """Verify the page shows the chapter and links to the other chapters in the book."""
        response = client.get(f"{BOOK_URL}/chapter/ch-2")

        assert response.status_code == 200
        assert b"Chapter Two" in response.data
        assert b"chapter/ch-1" in response.data
        assert b"chapter/ch-3" in response.data

    def test_sidebar_links_associated_characters(self, client, set_role, set_chapters) -> None:
        """Verify the sidebar links to each character associated with the chapter."""
        # Given a chapter associated with a character on the campaign roster
        hero = CharacterFactory.build(id="hero-1", name="Sidebar Hero", campaign_id="camp-1")
        set_role("PLAYER", characters=[hero])
        set_chapters(
            [CampaignChapterFactory.build(id="ch-2", book_id="book-1", character_ids=["hero-1"])]
        )

        # When viewing the chapter
        response = client.get(f"{BOOK_URL}/chapter/ch-2")

        # Then the sidebar links to the character
        assert b"Sidebar Hero" in response.data
        assert b"/character/hero-1" in response.data

    @pytest.mark.parametrize(("role", "shows_add_card"), [("STORYTELLER", True), ("PLAYER", False)])
    def test_new_chapter_card_only_for_managers(
        self, client, set_role, role, shows_add_card
    ) -> None:
        """Verify only campaign managers get the carousel card that opens the create form."""
        set_role(role)

        response = client.get(f"{BOOK_URL}/chapter/ch-2")

        assert (b"/book/book-1/chapter?from_chapter=ch-2" in response.data) is shows_add_card


class TestChapterAccessControl:
    """Tests that players cannot manage chapters."""

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [
            ("get", "/chapter"),
            ("post", "/chapter"),
            ("get", "/chapter/ch-2/edit"),
            ("post", "/chapter/ch-2/edit"),
            ("delete", "/chapter/ch-2"),
            ("delete", "/chapter/ch-2/images/asset-1"),
        ],
    )
    def test_player_is_forbidden(self, client, fake_vclient, method, suffix) -> None:
        """Verify a player gets 403 and no chapter write reaches the API."""
        # When a player sends the request directly
        response = getattr(client, method)(
            f"{BOOK_URL}{suffix}",
            data={"name": "New Name", "csrf_token": get_csrf(client)},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then it is refused before any write
        assert response.status_code == 403
        for route in CHAPTER_WRITE_ROUTES:
            fake_vclient.assert_not_called(route)


@pytest.mark.usefixtures("storyteller")
class TestChapterCreate:
    """Tests for the chapter create form."""

    @pytest.fixture
    def post_create(self, client) -> Callable[..., TestResponse]:
        """Return a function that submits the create form."""

        def _post(**form: str | list[str]) -> TestResponse:
            return htmx_post(client, f"{BOOK_URL}/chapter", form, htmx=False)

        return _post

    @pytest.mark.parametrize(
        ("query", "target_id", "cancel_path"),
        [
            ("", "book-chapters-card", BOOK_URL),
            ("?from_chapter=ch-2", "chapter-content", f"{BOOK_URL}/chapter/ch-2"),
            ("?target=evil%20x", "book-chapters-card", BOOK_URL),
        ],
        ids=["from-book", "from-chapter", "ignores-client-target"],
    )
    def test_form_targets_launching_page(self, client, query, target_id, cancel_path) -> None:
        """Verify the form swaps into, and cancels back to, the page that opened it.

        The swap target is derived server side, so a client-supplied target is never reflected.
        """
        response = client.get(f"{BOOK_URL}/chapter{query}")

        body = response.get_data(as_text=True)
        assert f'id="{target_id}"' in body
        assert f'hx-get="{cancel_path}"' in body
        assert "evil" not in body

    def test_creates_chapter_and_redirects_to_it(self, post_create, fake_vclient) -> None:
        """Verify the chapter is created with its characters and the client is sent to it."""
        response = post_create(name="New Chapter", character_ids=["c1", "c2"])

        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == f"{BOOK_URL}/chapter/ch-new"
        fake_vclient.assert_called(
            Routes.CHAPTERS_CREATE,
            params={"campaign_id": "camp-1", "book_id": "book-1"},
            json_subset={"name": "New Chapter", "character_ids": ["c1", "c2"]},
            times=1,
        )

    def test_create_clears_book_and_campaign_caches(self, post_create, clear_content_cache) -> None:
        """Verify creating a chapter refreshes the book's chapters and the books' chapter counts."""
        post_create(name="New Chapter")

        _, kwargs = clear_content_cache.call_args
        assert kwargs["book_id"] == "book-1"
        assert kwargs["campaign_id"] == "camp-1"

    def test_blank_name_rerenders_form_without_calling_api(self, post_create, fake_vclient) -> None:
        """Verify a blank name shows a form error and nothing is created."""
        response = post_create(name="   ")

        assert response.status_code == 200
        assert name_errors("")[0] in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHAPTERS_CREATE)

    def test_api_rejection_rerenders_form_with_its_reason(self, post_create, fake_vclient) -> None:
        """Verify an API rejection on create shows its reason on the form."""
        fake_vclient.set_error(
            Routes.CHAPTERS_CREATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        response = post_create(name="Taken Name")

        assert response.status_code == 200
        assert b"Name is already taken" in response.data


@pytest.mark.usefixtures("storyteller")
class TestChapterEdit:
    """Tests for the chapter edit form."""

    @pytest.fixture
    def post_edit(self, client) -> Callable[..., TestResponse]:
        """Return a function that submits the edit form for chapter two."""

        def _post(**form: str | list[str]) -> TestResponse:
            return htmx_post(client, f"{BOOK_URL}/chapter/ch-2/edit", form, htmx=False)

        return _post

    @pytest.mark.parametrize(
        ("selected", "expected"), [(["c9"], ["c9"]), ([], [])], ids=["one", "none-clears"]
    )
    def test_sends_selected_characters(self, post_edit, fake_vclient, selected, expected) -> None:
        """Verify the selected characters are sent, and none selected clears the associations."""
        post_edit(name="Chapter Two", character_ids=selected)

        fake_vclient.assert_called(
            Routes.CHAPTERS_UPDATE,
            params={"campaign_id": "camp-1", "book_id": "book-1", "chapter_id": "ch-2"},
            json_subset={"character_ids": expected},
            times=1,
        )

    @pytest.mark.parametrize(
        ("form", "error"),
        [
            ({"name": "  "}, name_errors("")[0]),
            ({"name": "Chapter Two", "number": "0"}, position_number("0", 1)[1]),
        ],
        ids=["blank-name", "number-below-one"],
    )
    def test_invalid_input_rerenders_form_without_calling_api(
        self, post_edit, fake_vclient, form, error
    ) -> None:
        """Verify invalid input shows a form error and nothing reaches the API."""
        response = post_edit(**form)

        assert response.status_code == 200
        assert error in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHAPTERS_UPDATE)

    @pytest.mark.parametrize(
        ("route", "form"),
        [
            (Routes.CHAPTERS_UPDATE, {"name": "Chapter Two", "character_ids": ["nope"]}),
            (Routes.CHAPTERS_RENUMBER, {"name": "Chapter Two", "number": "7"}),
        ],
        ids=["update", "renumber"],
    )
    def test_api_rejection_rerenders_form_with_its_reason(
        self, post_edit, fake_vclient, route, form
    ) -> None:
        """Verify an API rejection on update or renumber shows its reason instead of a 500."""
        fake_vclient.set_error(route, status_code=400, detail="Rejected by the API")

        response = post_edit(**form)

        assert response.status_code == 200
        assert b"Rejected by the API" in response.data

    def test_edit_form_keeps_associations_the_picker_cannot_offer(
        self, client, set_role, set_chapters
    ) -> None:
        """Verify an associated storyteller character is kept in the picker, not dropped."""
        # Given a chapter associated with a storyteller character the picker would not offer
        boss = CharacterFactory.build(
            id="boss-1", type="STORYTELLER", name="Story Boss", campaign_id="camp-1"
        )
        set_role("STORYTELLER", characters=[boss])
        set_chapters(
            [CampaignChapterFactory.build(id="ch-2", book_id="book-1", character_ids=["boss-1"])]
        )

        # When opening the edit form
        response = client.get(f"{BOOK_URL}/chapter/ch-2/edit")

        # Then the association is seeded into the picker
        assert response.status_code == 200
        assert b"boss-1" in response.data
        assert b"Story Boss" in response.data


@pytest.mark.usefixtures("storyteller")
class TestChapterDelete:
    """Tests for deleting a chapter."""

    def test_deletes_chapter_and_redirects_to_book(
        self, client, fake_vclient, clear_content_cache
    ) -> None:
        """Verify the chapter is deleted, caches are cleared, and the client returns to the book."""
        response = client.delete(
            f"{BOOK_URL}/chapter/ch-1", headers={"X-CSRFToken": get_csrf(client)}
        )

        assert response.headers.get("HX-Redirect") == BOOK_URL
        fake_vclient.assert_called(
            Routes.CHAPTERS_DELETE,
            params={"campaign_id": "camp-1", "book_id": "book-1", "chapter_id": "ch-1"},
            times=1,
        )
        _, kwargs = clear_content_cache.call_args
        assert kwargs["book_id"] == "book-1"
        assert kwargs["campaign_id"] == "camp-1"
