"""Tests for image upload, delete, and carousel rendering (book, chapter, character)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_delete, htmx_post
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
    from werkzeug.test import TestResponse

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

    def test_upload_sends_file_and_renders_new_asset(
        self, client, mocker, fake_vclient, image_entity, mock_asset
    ) -> None:
        """Verify a valid upload reaches the entity's upload route and renders the re-read assets."""
        # Given a privileged user and an API that accepts the upload and then lists the new asset
        mocker.patch(image_entity.guard_path, return_value=True)
        fake_vclient.set_response(image_entity.asset_upload_route, model=mock_asset)
        fake_vclient.set_response(image_entity.assets_list_route, items=[mock_asset])
        csrf = get_csrf(client)

        # When uploading an image
        response = client.post(
            image_entity.images_url,
            data={
                "csrf_token": csrf,
                "image": (io.BytesIO(VALID_JPEG), "img.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Then the file reaches the entity's upload route
        assert response.status_code == 200
        (upload,) = fake_vclient.assert_called(
            image_entity.asset_upload_route, params=image_entity.path_params, times=1
        )
        assert upload.files["data"] == RecordedFile(
            filename="img.jpg", content_type="image/jpeg", content=VALID_JPEG
        )
        # And the asset list is re-read after the upload so the new asset is rendered
        expected = [image_entity.asset_upload_route, image_entity.assets_list_route]
        assert _routes_called(fake_vclient, *expected) == expected
        assert mock_asset.public_url in response.get_data(as_text=True)

    @pytest.mark.parametrize(
        "image",
        [
            (b"junk", "file.bin", "application/octet-stream"),
            (make_image_bytes(6000, 4001), "big.png", "image/png"),
        ],
        ids=["wrong-type", "over-24-megapixels"],
    )
    def test_invalid_image_is_not_uploaded(
        self, client, mocker, fake_vclient, image_entity, image: tuple[bytes, str, str]
    ) -> None:
        """Verify an unsupported or oversized image never reaches the API and nothing re-renders."""
        # Given a privileged user
        mocker.patch(image_entity.guard_path, return_value=True)
        content, filename, mime = image

        # When uploading the invalid image
        response = client.post(
            image_entity.images_url,
            data={"csrf_token": get_csrf(client), "image": (io.BytesIO(content), filename, mime)},
            content_type="multipart/form-data",
        )

        # Then the API is untouched and only the flash is swapped in
        assert response.status_code == 200
        assert response.headers["HX-Reswap"] == "none"
        fake_vclient.assert_not_called(image_entity.asset_upload_route)
        fake_vclient.assert_not_called(image_entity.assets_list_route)

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    def test_non_editor_forbidden(
        self, client, mocker, fake_vclient, image_entity, method: str
    ) -> None:
        """Verify users who cannot manage the campaign get 403 on upload and delete."""
        # Given an unprivileged user
        mocker.patch(image_entity.guard_path, return_value=False)
        csrf = get_csrf(client)

        # When attempting an upload or delete
        if method == "POST":
            response = client.post(
                image_entity.images_url,
                data={
                    "csrf_token": csrf,
                    "image": (io.BytesIO(VALID_JPEG), "img.jpg", "image/jpeg"),
                },
                content_type="multipart/form-data",
            )
        else:
            response = client.delete(
                f"{image_entity.images_url}/asset-1", headers={"X-CSRFToken": csrf}
            )

        # Then access is forbidden and nothing reaches the API
        assert response.status_code == 403
        fake_vclient.assert_not_called(image_entity.asset_upload_route)
        fake_vclient.assert_not_called(image_entity.asset_delete_route)


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
def own_character(use_context, mock_character, mock_campaign):
    """Put the session user's own character and its campaign in the context."""
    use_context(user_role="PLAYER", campaign=mock_campaign, characters=[mock_character])
    return mock_character, mock_campaign


@pytest.fixture
def other_players_character(use_context, mock_campaign):
    """Put a character owned by another player in the context."""
    char = CharacterFactory.build(
        id="char-456", user_player_id="different-user-id", campaign_id="camp-1"
    )
    use_context(user_role="PLAYER", campaign=mock_campaign, characters=[char])
    return char


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


def _upload_character_image(client, character_id: str, data: dict) -> TestResponse:
    """POST an upload to the character images endpoint the way HTMX does."""
    return htmx_post(
        client, f"/character/{character_id}/images", data, content_type="multipart/form-data"
    )


class TestCharacterImagesTab:
    """Tests for GET /character/<id>/images."""

    @pytest.mark.parametrize("htmx", [True, False], ids=["htmx-tab", "full-page"])
    def test_images_tab_renders_assets(
        self, client, fake_vclient, own_character, sample_assets, *, htmx: bool
    ) -> None:
        """Verify the images tab shows the character's images as a tab swap or a full page."""
        char, _ = own_character
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)
        headers = {"HX-Request": "true"} if htmx else {}

        response = client.get(f"/character/{char.id}/images", headers=headers)

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        for asset in sample_assets:
            assert asset.public_url in body

    @pytest.mark.parametrize("owner", [True, False], ids=["owner", "other-player"])
    def test_delete_offered_only_to_editors(
        self, request, client, fake_vclient, sample_assets, *, owner: bool
    ) -> None:
        """Verify only users who can edit the character get delete actions on its images."""
        # Given a character owned by the session user, or by another player
        if owner:
            char, _ = request.getfixturevalue("own_character")
        else:
            char = request.getfixturevalue("other_players_character")
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)

        # When viewing the images tab
        body = client.get(f"/character/{char.id}/images", headers={"HX-Request": "true"}).get_data(
            as_text=True
        )

        # Then everyone sees the images but only the owner can delete them
        assert sample_assets[0].public_url in body
        assert (f"/character/{char.id}/images/{sample_assets[0].id}" in body) is owner


class TestCharacterImageUpload:
    """Tests for POST /character/<character_id>/images."""

    def test_owner_can_upload_image(
        self, client, fake_vclient, own_character, sample_assets
    ) -> None:
        """Verify the owner's upload reaches the API and the re-read carousel shows it."""
        # Given an API that accepts the upload and then lists the new asset with the existing ones
        char, _ = own_character
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets)
        fake_vclient.set_response(Routes.CHARACTERS_ASSETS_UPLOAD, model=sample_assets[0])

        # When uploading an image
        response = _upload_character_image(
            client, char.id, {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
        )

        # Then the file reaches the character's upload route and the carousel holds the new asset
        assert response.status_code == 200
        (upload,) = fake_vclient.assert_called(
            Routes.CHARACTERS_ASSETS_UPLOAD, params={"character_id": char.id}, times=1
        )
        assert upload.files["data"].content == VALID_PNG
        expected = [Routes.CHARACTERS_ASSETS_UPLOAD, Routes.CHARACTERS_ASSETS_LIST]
        assert _routes_called(fake_vclient, *expected) == expected
        assert sample_assets[0].public_url in response.get_data(as_text=True)

    def test_api_refused_upload_flashes_without_rerender(
        self, client, fake_vclient, own_character
    ) -> None:
        """Verify an upload the API refuses flashes its reason and leaves the carousel alone."""
        # Given an API that rejects the upload
        char, _ = own_character
        fake_vclient.set_error(
            Routes.CHARACTERS_ASSETS_UPLOAD, status_code=400, detail="Unsupported image"
        )

        # When uploading an image
        response = _upload_character_image(
            client, char.id, {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
        )

        # Then the API's reason is shown and the asset list is not re-read
        assert response.status_code == 200
        assert response.headers["HX-Reswap"] == "none"
        assert "Unsupported image" in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)

    @pytest.mark.parametrize(
        "data",
        [
            {"image": (io.BytesIO(b"not-an-image"), "doc.pdf", "application/pdf")},
            {},
            {"image": (io.BytesIO(b"x" * (MAX_IMAGE_SIZE + 1)), "huge.png", "image/png")},
        ],
        ids=["wrong-type", "missing-file", "oversized"],
    )
    def test_invalid_upload_is_not_sent(
        self, client, fake_vclient, own_character, data: dict
    ) -> None:
        """Verify an invalid or missing file never reaches the API and nothing re-renders."""
        char, _ = own_character

        response = _upload_character_image(client, char.id, data)

        assert response.status_code == 200
        assert response.headers["HX-Reswap"] == "none"
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_UPLOAD)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_LIST)

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    def test_other_players_character_forbidden(
        self, client, fake_vclient, other_players_character, method: str
    ) -> None:
        """Verify a player cannot upload or delete images on another player's character."""
        char = other_players_character
        if method == "POST":
            response = _upload_character_image(
                client, char.id, {"image": (io.BytesIO(VALID_PNG), "photo.png", "image/png")}
            )
        else:
            response = htmx_delete(client, f"/character/{char.id}/images/asset-1")

        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_UPLOAD)
        fake_vclient.assert_not_called(Routes.CHARACTERS_ASSETS_DELETE)


def test_owner_can_delete_character_image(
    client, fake_vclient, own_character, sample_assets
) -> None:
    """Verify the owner's delete reaches the API and the remaining images re-render."""
    # Given two images remain after the delete
    char, _ = own_character
    fake_vclient.set_response(Routes.CHARACTERS_ASSETS_LIST, items=sample_assets[:2])

    # When deleting an image
    response = htmx_delete(client, f"/character/{char.id}/images/asset-1")

    # Then the API deletes it and the remaining images are shown
    assert response.status_code == 200
    fake_vclient.assert_called(
        Routes.CHARACTERS_ASSETS_DELETE,
        params={"character_id": char.id, "asset_id": "asset-1"},
        times=1,
    )
    body = response.get_data(as_text=True)
    assert sample_assets[0].public_url in body
    assert sample_assets[1].public_url in body
