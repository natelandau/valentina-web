"""Tests for book image upload, delete, and carousel rendering."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from vclient.testing import (
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
)

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
    ]


@pytest.fixture
def mock_asset():
    """Build a stand-in asset object."""
    return SimpleNamespace(
        id="asset-1",
        public_url="https://cdn.example.com/img.jpg",
        original_filename="img.jpg",
    )


@pytest.fixture
def _mock_book_lookup(mocker, mock_book, mock_campaign) -> None:
    """Mock the book/campaign lookup."""
    mocker.patch(
        "vweb.routes.book.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )


@pytest.fixture
def _mock_chapters_service(mocker, mock_chapters) -> None:
    """Mock the chapters service."""
    svc = mocker.patch("vweb.routes.book.views.sync_chapters_service").return_value
    svc.list_all.return_value = mock_chapters


@pytest.fixture
def mock_books_svc(mocker):
    """Mock the books service factory and return the underlying service mock."""
    return mocker.patch("vweb.routes.book.views.sync_books_service").return_value


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookImageCarousel:
    """Tests for carousel rendering on the book detail page."""

    def test_book_detail_renders_carousel_when_assets_present(
        self, client, mock_books_svc, mock_asset, mock_book, mock_campaign
    ) -> None:
        """Verify carousel renders when assets exist."""
        # Given the book has one asset
        mock_books_svc.list_all_assets.return_value = [mock_asset]

        # When fetching the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")

        # Then the carousel and asset URL appear
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "book-carousel" in body
        assert mock_asset.public_url in body

    def test_book_detail_hides_carousel_when_no_assets(
        self, client, mock_books_svc, mock_book, mock_campaign
    ) -> None:
        """Verify carousel is absent when no assets exist."""
        # Given no assets
        mock_books_svc.list_all_assets.return_value = []

        # When fetching the book detail page
        response = client.get(f"/campaign/{mock_campaign.id}/book/{mock_book.id}")

        # Then the carousel id is not present
        assert response.status_code == 200
        assert "book-carousel" not in response.get_data(as_text=True)


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookImageUpload:
    """Tests for image upload."""

    def test_book_image_upload_happy_path(
        self, client, mocker, mock_books_svc, mock_asset, mock_book, mock_campaign
    ) -> None:
        """Verify a valid upload re-renders the partial with the new asset."""
        # Given a privileged user and a successful upload
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        mock_books_svc.list_all_assets.return_value = [mock_asset]
        csrf = get_csrf(client)

        # When uploading an image
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/images",
            data={
                "csrf_token": csrf,
                "image": (BytesIO(b"fakeimage"), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then upload is called and the response renders the new asset
        assert response.status_code == 200
        mock_books_svc.upload_asset.assert_called_once()
        assert mock_asset.public_url in response.get_data(as_text=True)

    def test_book_image_upload_rejects_wrong_type(
        self, client, mocker, mock_books_svc, mock_book, mock_campaign
    ) -> None:
        """Verify upload of an unsupported MIME type does not call the API."""
        # Given a privileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        mock_books_svc.list_all_assets.return_value = []
        csrf = get_csrf(client)

        # When uploading a non-image file
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/images",
            data={
                "csrf_token": csrf,
                "image": (BytesIO(b"junk"), "file.bin", "application/octet-stream"),
            },
            content_type="multipart/form-data",
        )

        # Then upload was not called
        assert response.status_code == 200
        mock_books_svc.upload_asset.assert_not_called()

    def test_book_image_upload_forbidden_for_non_editor(
        self, client, mocker, mock_books_svc, mock_book, mock_campaign
    ) -> None:
        """Verify non-privileged users get 403 on upload."""
        # Given an unprivileged user
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=False)
        csrf = get_csrf(client)

        # When attempting an upload
        response = client.post(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/images",
            data={
                "csrf_token": csrf,
                "image": (BytesIO(b"x"), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then access is forbidden
        assert response.status_code == 403
        mock_books_svc.upload_asset.assert_not_called()


@pytest.mark.usefixtures("_mock_book_lookup", "_mock_chapters_service")
class TestBookImageDelete:
    """Tests for image delete."""

    def test_book_image_delete_happy_path(
        self, client, mocker, mock_books_svc, mock_book, mock_campaign
    ) -> None:
        """Verify deletion calls the service and re-renders without the carousel."""
        # Given a privileged user and an empty asset list after delete
        mocker.patch("vweb.routes.book.views.can_manage_campaign", return_value=True)
        mock_books_svc.list_all_assets.return_value = []
        csrf = get_csrf(client)

        # When deleting an asset
        response = client.delete(
            f"/campaign/{mock_campaign.id}/book/{mock_book.id}/images/asset-1",
            headers={"X-CSRFToken": csrf},
        )

        # Then delete is called and the carousel is gone
        assert response.status_code == 200
        mock_books_svc.delete_asset.assert_called_once_with("book-1", "asset-1")
        assert "book-carousel" not in response.get_data(as_text=True)
