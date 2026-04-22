"""Tests for chapter view routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
)

from tests.conftest import get_csrf

if TYPE_CHECKING:
    from vclient.models import CampaignChapter


@pytest.fixture
def mock_campaign():
    """Build a factory campaign."""
    return CampaignFactory.build(id="camp-1")


@pytest.fixture
def mock_book():
    """Build a factory book."""
    return CampaignBookFactory.build(id="book-1", campaign_id="camp-1", name="Book One", number=1)


@pytest.fixture
def mock_chapters():
    """Build factory chapters."""
    return [
        CampaignChapterFactory.build(id="ch-1", book_id="book-1", number=1, name="Chapter One"),
        CampaignChapterFactory.build(id="ch-2", book_id="book-1", number=2, name="Chapter Two"),
        CampaignChapterFactory.build(id="ch-3", book_id="book-1", number=3, name="Chapter Three"),
    ]


@pytest.fixture
def _mock_chapter_lookup(mocker, mock_book, mock_campaign, mock_chapters) -> None:
    """Mock book lookup, chapter lookup, and chapters service for chapter detail."""
    mocker.patch(
        "vweb.routes.chapter.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )

    def _fetch_chapter(book_id: str, chapter_id: str) -> CampaignChapter:
        return next((c for c in mock_chapters if c.id == chapter_id), mock_chapters[1])

    mocker.patch(
        "vweb.routes.chapter.views.fetch_chapter_or_404",
        side_effect=_fetch_chapter,
    )
    mocker.patch(
        "vweb.routes.chapter.views.get_chapters_for_book",
        return_value=mock_chapters,
    )
    chapters_service = mocker.patch("vweb.routes.chapter.views.sync_chapters_service").return_value
    chapters_service.list_all.return_value = mock_chapters
    chapters_service.list_all_assets.return_value = []
    chapters_service.list_all_notes.return_value = []
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
            data={"name": "New Chapter", "number": "1", "csrf_token": csrf},
        )
        assert response.status_code == 403

    def test_create_returns_updated_card(
        self, client, mocker, mock_campaign, mock_book, mock_chapters
    ) -> None:
        """Privileged users can create chapters."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter",
            data={"name": "New Chapter", "number": "4", "csrf_token": csrf},
        )
        assert response.status_code == 200
        assert b"book-chapters-card" in response.data


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
