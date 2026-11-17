"""Tests for image upload, delete, and carousel rendering (book, chapter, character)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from tests.helpers import make_image_bytes
from vweb.api_client.testing import (
    AssetFactory,
    CampaignChapterFactory,
    CharacterFactory,
    RecordedFile,
    Routes,
)
from vweb.constants import MAX_IMAGE_SIZE

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from vweb.api_client.routes import RouteSpec


VALID_JPEG = make_image_bytes(image_format="JPEG")
VALID_PNG = make_image_bytes()


def _routes_called(fake_vclient, *routes: RouteSpec) -> list[RouteSpec | None]:
    """Return which of ``routes`` the fake API received, in order, ignoring other calls."""
    return [request.route for request in fake_vclient.requests if request.route in routes]


@dataclass(frozen=True)
class ImageEntityCase:
    """Describe one image-bearing entity for the shared carousel/upload/delete tests."""

    name: str
    detail_url: str
    images_url: str
    carousel_id: str
    guard_path: str
    assets_list_route: RouteSpec
    asset_upload_route: RouteSpec
    asset_delete_route: RouteSpec
    path_params: dict[str, str]


@pytest.fixture
def mock_chapter():
    """Build a factory chapter."""
    return CampaignChapterFactory.build(
        id="ch-1",
        book_id="book-1",
        number=1,
        name="Chapter One",
        description="A beginning.",
    )


@pytest.fixture
def book_image_entity(
    mocker: MockerFixture, fake_vclient, mock_book, mock_campaign, mock_chapters
) -> ImageEntityCase:
    """Mock the book lookups and serve an empty asset list for image tests."""
    mocker.patch(
        "vweb.routes.book.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )
    mocker.patch(
        "vweb.lib.cache.campaign_content.chapters",
        return_value=mock_chapters,
    )
    fake_vclient.set_response(Routes.BOOKS_ASSETS_LIST, items=[])
    detail_url = f"/campaign/{mock_campaign.id}/book/{mock_book.id}"
    return ImageEntityCase(
        name="book",
        detail_url=detail_url,
        images_url=f"{detail_url}/images",
        carousel_id="book-carousel",
        guard_path="vweb.routes.book.views.can_manage_campaign",
        assets_list_route=Routes.BOOKS_ASSETS_LIST,
        asset_upload_route=Routes.BOOKS_ASSETS_UPLOAD,
        asset_delete_route=Routes.BOOKS_ASSETS_DELETE,
        path_params={"campaign_id": mock_campaign.id, "book_id": mock_book.id},
    )


@pytest.fixture
def chapter_image_entity(
    mocker: MockerFixture, fake_vclient, mock_book, mock_campaign, mock_chapter
) -> ImageEntityCase:
    """Mock the chapter lookups and serve empty asset and note lists for image tests."""
    mocker.patch(
        "vweb.routes.chapter.views.fetch_book_or_404",
        return_value=(mock_book, mock_campaign),
    )
    mocker.patch(
        "vweb.routes.chapter.views.fetch_chapter_or_404",
        return_value=mock_chapter,
    )
    mocker.patch(
        "vweb.lib.cache.campaign_content.chapters",
        return_value=[mock_chapter],
    )
    fake_vclient.set_response(Routes.CHAPTERS_ASSETS_LIST, items=[])
    fake_vclient.set_response(Routes.CHAPTERS_NOTES_LIST, items=[])
    detail_url = f"/campaign/{mock_campaign.id}/book/{mock_book.id}/chapter/{mock_chapter.id}"
    return ImageEntityCase(
        name="chapter",
        detail_url=detail_url,
        images_url=f"{detail_url}/images",
        carousel_id="chapter-carousel",
        guard_path="vweb.routes.chapter.views.can_manage_campaign",
        assets_list_route=Routes.CHAPTERS_ASSETS_LIST,
        asset_upload_route=Routes.CHAPTERS_ASSETS_UPLOAD,
        asset_delete_route=Routes.CHAPTERS_ASSETS_DELETE,
        path_params={
            "campaign_id": mock_campaign.id,
            "book_id": mock_book.id,
            "chapter_id": mock_chapter.id,
        },
    )


@pytest.fixture(params=["book_image_entity", "chapter_image_entity"])
def image_entity(request: pytest.FixtureRequest) -> ImageEntityCase:
    """Parametrize the shared image tests over the book and chapter entities."""
    return request.getfixturevalue(request.param)


class TestImageCarousel:
    """Tests for carousel rendering on the entity detail page."""

    def test_detail_renders_carousel_when_assets_present(
        self, client, fake_vclient, image_entity, mock_asset
    ) -> None:
        """Verify carousel renders when assets exist."""
        # Given the entity has one asset
        fake_vclient.set_response(
            image_entity.assets_list_route, items=[mock_asset], params=image_entity.path_params
        )

        # When fetching the detail page
        response = client.get(image_entity.detail_url)

        # Then the carousel and asset URL appear
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert image_entity.carousel_id in body
        assert mock_asset.public_url in body

    def test_detail_hides_carousel_when_no_assets(self, client, image_entity) -> None:
        """Verify carousel is absent when no assets exist."""
        # Given no assets (the fixture's default)

        # When fetching the detail page
        response = client.get(image_entity.detail_url)

        # Then the carousel id is not present
        assert response.status_code == 200
        assert image_entity.carousel_id not in response.get_data(as_text=True)


class TestImageUpload:
    """Tests for image upload on books and chapters."""

    def test_book_image_upload_happy_path(
        self, client, mocker, fake_vclient, book_image_entity, mock_asset
    ) -> None:
        """Verify a valid book upload re-renders the partial with the asset list read after it."""
        # Given a privileged user and an API that accepts the upload and then lists the new asset
        mocker.patch(book_image_entity.guard_path, return_value=True)
        fake_vclient.set_response(book_image_entity.asset_upload_route, model=mock_asset)
        fake_vclient.set_response(book_image_entity.assets_list_route, items=[mock_asset])
        csrf = get_csrf(client)

        # When uploading an image
        response = client.post(
            book_image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(VALID_JPEG), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then the image is uploaded to the book and the response renders the new asset
        assert response.status_code == 200
        fake_vclient.assert_called(
            book_image_entity.asset_upload_route, params=book_image_entity.path_params, times=1
        )
        expected = [book_image_entity.asset_upload_route, book_image_entity.assets_list_route]
        assert _routes_called(fake_vclient, *expected) == expected
        assert mock_asset.public_url in response.get_data(as_text=True)

    def test_chapter_image_upload_happy_path(
        self, client, mocker, fake_vclient, chapter_image_entity, mock_asset
    ) -> None:
        """Verify a valid chapter upload re-renders the partial with the asset list read after it."""
        # Given a privileged user and an API that accepts the upload and then lists the new asset
        mocker.patch(chapter_image_entity.guard_path, return_value=True)
        fake_vclient.set_response(chapter_image_entity.asset_upload_route, model=mock_asset)
        fake_vclient.set_response(chapter_image_entity.assets_list_route, items=[mock_asset])
        csrf = get_csrf(client)

        # When uploading an image
        response = client.post(
            chapter_image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(VALID_JPEG), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then the file reaches the chapter's upload route and the new asset is rendered
        assert response.status_code == 200
        (upload,) = fake_vclient.assert_called(
            chapter_image_entity.asset_upload_route,
            params=chapter_image_entity.path_params,
            times=1,
        )
        assert upload.params["chapter_id"] == "ch-1"
        assert upload.files["data"] == RecordedFile(
            filename="img.jpg", content_type="image/jpeg", content=VALID_JPEG
        )
        expected = [chapter_image_entity.asset_upload_route, chapter_image_entity.assets_list_route]
        assert _routes_called(fake_vclient, *expected) == expected
        assert mock_asset.public_url in response.get_data(as_text=True)

    def test_image_upload_rejects_wrong_type(
        self, client, mocker, fake_vclient, image_entity
    ) -> None:
        """Verify upload of an unsupported MIME type does not call the API."""
        # Given a privileged user
        mocker.patch(image_entity.guard_path, return_value=True)
        csrf = get_csrf(client)

        # When uploading a non-image file
        response = client.post(
            image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(b"junk"), "file.bin", "application/octet-stream"),
            },
            content_type="multipart/form-data",
        )

        # Then upload was not called
        assert response.status_code == 200
        fake_vclient.assert_not_called(image_entity.asset_upload_route)
        fake_vclient.assert_not_called(image_entity.assets_list_route)
        assert response.headers["HX-Reswap"] == "none"

    def test_image_upload_rejects_over_pixel_cap(
        self, client, mocker, fake_vclient, image_entity
    ) -> None:
        """Verify an image over 24 megapixels does not call the API."""
        # Given a privileged user
        mocker.patch(image_entity.guard_path, return_value=True)
        csrf = get_csrf(client)

        # When uploading a 6000 x 4001 image
        response = client.post(
            image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(make_image_bytes(6000, 4001)), "big.png", "image/png"),
            },
            content_type="multipart/form-data",
        )

        # Then upload was not called and the limit is explained
        assert response.status_code == 200
        fake_vclient.assert_not_called(image_entity.asset_upload_route)
        fake_vclient.assert_not_called(image_entity.assets_list_route)
        assert response.headers["HX-Reswap"] == "none"
        assert "max 24 megapixels" in response.get_data(as_text=True)

    def test_image_upload_forbidden_for_non_editor(
        self, client, mocker, fake_vclient, image_entity
    ) -> None:
        """Verify non-privileged users get 403 on upload."""
        # Given an unprivileged user
        mocker.patch(image_entity.guard_path, return_value=False)
        csrf = get_csrf(client)

        # When attempting an upload
        response = client.post(
            image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(b"x"), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then access is forbidden
        assert response.status_code == 403
        fake_vclient.assert_not_called(image_entity.asset_upload_route)


class TestImageDelete:
    """Tests for image delete on books and chapters."""

    def test_image_delete_happy_path(self, client, mocker, fake_vclient, image_entity) -> None:
        """Verify deletion reaches the API and re-renders without the carousel."""
        # Given a privileged user and an empty asset list after delete
        mocker.patch(image_entity.guard_path, return_value=True)
        csrf = get_csrf(client)

        # When deleting an asset
        response = client.delete(
            f"{image_entity.images_url}/asset-1",
            headers={"X-CSRFToken": csrf},
        )

        # Then delete is called and the carousel is gone
        assert response.status_code == 200
        fake_vclient.assert_called(
            image_entity.asset_delete_route,
            params={**image_entity.path_params, "asset_id": "asset-1"},
            times=1,
        )
        assert image_entity.carousel_id not in response.get_data(as_text=True)


@pytest.fixture
def mock_character_lookup(mocker, mock_character, mock_campaign):
    """Mock get_character_and_campaign to return test character and campaign."""
    mocker.patch(
        "vweb.routes.character_view.views.get_character_and_campaign",
        return_value=(mock_character, mock_campaign),
    )
    return mock_character, mock_campaign


@pytest.fixture
def sample_assets():
    """Build a list of factory assets."""
    return AssetFactory.batch(
        3,
        asset_type="image",
        mime_type="image/png",
        parent_type="character",
        parent_id="char-123",
    )


class TestCharacterImagesTabRendering:
    """Tests for GET /character/<id>/images via HTMX."""

    def test_images_tab_passes_assets_to_template(
        self, client, mocker, fake_vclient, mock_character_lookup, sample_assets
    ) -> None:
        """Verify the images tab renders with asset data."""
        # Given a mocked character service returning assets
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)

        # When requesting the images tab via HTMX
        response = client.get(
            f"/character/{char.id}/images",
            headers={"HX-Request": "true"},
        )

        # Then the response is successful and contains carousel markup
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "carousel" in body

    def test_images_tab_full_page_load_renders_assets(
        self, client, mocker, fake_vclient, mock_character_lookup, sample_assets
    ) -> None:
        """Verify hitting /character/<id>/images directly threads assets through Main.jinja."""
        # Given a mocked character service returning assets and a non-HTMX request
        _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)

        # When requesting the images tab without HX-Request
        response = client.get("/character/char-123/images")

        # Then the page renders the carousel with the asset URLs
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "image-carousel" in body
        assert sample_assets[0].public_url in body

    def test_images_tab_shows_empty_state_for_viewer(
        self, client, mocker, fake_vclient, mock_campaign
    ) -> None:
        """Verify non-editor sees viewer empty state when no images exist."""
        # Given a character owned by a different user (viewer)
        char = CharacterFactory.build(
            id="char-456",
            user_player_id="different-user-id",
            campaign_id="camp-1",
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(char, mock_campaign),
        )
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=[])

        # When requesting the images tab
        response = client.get(
            f"/character/{char.id}/images",
            headers={"HX-Request": "true"},
        )

        # Then the empty state for viewers is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "No images uploaded for this character" in body


class TestCharacterImageUpload:
    """Tests for POST /character/<character_id>/images."""

    def test_owner_can_upload_image(
        self, client, fake_vclient, mock_character_lookup, sample_assets
    ) -> None:
        """Verify character owner can upload an image and gets updated carousel."""
        # Given an API that accepts the upload and then lists the new asset with the existing ones
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_UPLOAD, model=sample_assets[0])
        csrf = get_csrf(client)

        # When uploading an image
        data = {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the file reaches the character's upload route and the carousel holds the new asset
        assert response.status_code == 200
        (upload,) = fake_vclient.assert_called(
            Routes.CHARACTERS_ASSETS_UPLOAD, params={"character_id": char.id}, times=1
        )
        assert upload.files["data"].content == VALID_PNG
        expected = [Routes.CHARACTERS_ASSETS_UPLOAD, Routes.CHARACTERS_ASSETS_LIST]
        assert _routes_called(fake_vclient, *expected) == expected
        body = response.get_data(as_text=True)
        assert "carousel" in body
        assert sample_assets[0].public_url in body

    def test_api_refused_upload_flashes_without_rerender(
        self, client, fake_vclient, mock_character_lookup
    ) -> None:
        """Verify an upload the API refuses flashes its reason and leaves the carousel alone."""
        # Given an API that rejects the upload
        char, _ = mock_character_lookup
        fake_vclient.set_error(
            Routes.CHARACTERS_ASSETS_UPLOAD, status_code=400, detail="Unsupported image"
        )
        csrf = get_csrf(client)

        # When uploading an image
        data = {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then only the flash is returned and the asset list is not re-read
        assert response.status_code == 200
        assert response.headers["HX-Reswap"] == "none"
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)
        assert "carousel" not in response.get_data(as_text=True)

    def test_non_owner_non_admin_gets_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-owner non-admin cannot upload."""
        # Given a character owned by a different user
        char = CharacterFactory.build(
            id="char-456",
            user_player_id="different-user-id",
            campaign_id="camp-1",
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(char, mock_campaign),
        )
        csrf = get_csrf(client)

        # When a non-owner tries to upload
        data = {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_invalid_mime_type_flashes_error(
        self, client, fake_vclient, mock_character_lookup
    ) -> None:
        """Verify uploading a non-image file type flashes an error."""
        # Given a character with no images
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=[])
        csrf = get_csrf(client)

        # When uploading a non-image file
        data = {"image": (io.BytesIO(b"not-an-image"), "doc.pdf", "application/pdf")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response succeeds but contains a flash error
        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_UPLOAD)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)
        assert response.headers["HX-Reswap"] == "none"

    def test_missing_file_flashes_error(self, client, fake_vclient, mock_character_lookup) -> None:
        """Verify submitting without a file flashes an error."""
        # Given a character with no images
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=[])
        csrf = get_csrf(client)

        # When submitting without a file
        response = client.post(
            f"/character/{char.id}/images",
            data={},
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response succeeds but upload was not called
        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_UPLOAD)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)
        assert response.headers["HX-Reswap"] == "none"

    def test_oversized_file_flashes_error(
        self, client, fake_vclient, mock_character_lookup
    ) -> None:
        """Verify uploading a file over the size limit flashes an error."""
        # Given a character with no images
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=[])
        csrf = get_csrf(client)

        # When uploading an oversized file
        big_data = b"x" * (MAX_IMAGE_SIZE + 1)
        data = {"image": (io.BytesIO(big_data), "huge.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the upload is rejected
        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_UPLOAD)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)
        assert response.headers["HX-Reswap"] == "none"


class TestCharacterImageDelete:
    """Tests for DELETE /character/<character_id>/images/<asset_id>."""

    def test_owner_can_delete_image(self, client, fake_vclient, mock_character_lookup) -> None:
        """Verify character owner can delete an image."""
        # Given a character with no images
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=[])
        csrf = get_csrf(client)

        # When deleting an image
        response = client.delete(
            f"/character/{char.id}/images/asset-1",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the delete succeeds
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.CHARACTERS_ASSETS_DELETE,
            params={"character_id": char.id, "asset_id": "asset-1"},
            times=1,
        )

    def test_non_owner_non_admin_gets_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-owner non-admin cannot delete."""
        # Given a character owned by a different user
        char = CharacterFactory.build(
            id="char-456",
            user_player_id="different-user-id",
            campaign_id="camp-1",
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(char, mock_campaign),
        )
        csrf = get_csrf(client)

        # When a non-owner tries to delete
        response = client.delete(
            f"/character/{char.id}/images/asset-1",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_delete_returns_updated_carousel(
        self, client, mocker, fake_vclient, mock_character_lookup, sample_assets
    ) -> None:
        """Verify delete returns the updated images content fragment."""
        # Given a mocked character service with remaining assets
        char, _ = mock_character_lookup
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets[:2])
        csrf = get_csrf(client)

        # When deleting an image
        response = client.delete(
            f"/character/{char.id}/images/asset-1",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response contains the updated carousel
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "carousel" in body
