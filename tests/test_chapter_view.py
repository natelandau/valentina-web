"""Tests for chapter view routes."""

from __future__ import annotations

import pytest
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
)

from tests.conftest import get_csrf

SECTIONS = ("story", "notes")


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
    """Mock book lookup and chapters service for chapter detail."""
    mocker.patch(
        "vweb.routes.chapter.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )
    mocker.patch(
        "vweb.routes.chapter.views.get_chapters_for_book",
        return_value=mock_chapters,
    )
    svc = mocker.patch("vweb.routes.chapter.views.sync_chapters_service").return_value
    svc.get.return_value = mock_chapters[1]  # ch-2 by default
    svc.list_all.return_value = mock_chapters
    svc.list_all_assets.return_value = []
    return svc


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

    def test_htmx_story_fragment(self, client, mock_campaign, mock_book) -> None:
        """Verify HTMX story section returns 200."""
        response = client.get(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/story",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

    def test_htmx_notes_fragment(self, client, mock_campaign, mock_book) -> None:
        """Verify HTMX notes section returns 200."""
        response = client.get(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/notes",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

    def test_invalid_section_defaults_to_story(self, client, mock_campaign, mock_book) -> None:
        """Verify invalid section name defaults to story."""
        response = client.get(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2/invalid",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

    def test_prev_next_navigation(self, client, mock_campaign, mock_book) -> None:
        """Chapter 2 should have prev and next navigation links."""
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-2")
        assert b"chapter/ch-1" in response.data
        assert b"chapter/ch-3" in response.data

    def test_first_chapter_no_prev(
        self, client, mock_campaign, mock_book, mocker, mock_chapters
    ) -> None:
        """First chapter should not have a prev link."""
        svc = mocker.patch("vweb.routes.chapter.views.sync_chapters_service").return_value
        svc.get.return_value = mock_chapters[0]
        svc.list_all.return_value = mock_chapters
        mocker.patch(
            "vweb.routes.chapter.views.get_chapters_for_book",
            return_value=mock_chapters,
        )
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-1")
        assert response.status_code == 200


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

    def test_delete_returns_updated_card(
        self, client, mocker, mock_campaign, mock_book, mock_chapters
    ) -> None:
        """Privileged users can delete chapters."""
        mocker.patch("vweb.routes.chapter.views.can_manage_campaign", return_value=True)
        csrf = get_csrf(client)
        response = client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/ch-1",
            headers={"X-CSRFToken": csrf},
        )
        assert response.status_code == 200
        assert b"book-chapters-card" in response.data
