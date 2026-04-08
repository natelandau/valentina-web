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
    """Mock the chapters service for book detail page."""
    svc = mocker.patch("vweb.routes.book.views.sync_chapters_service").return_value
    svc.list_all.return_value = mock_chapters
    return svc


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
