"""Tests for character image upload and delete views."""

from __future__ import annotations

import io

import pytest
from vclient.testing import AssetFactory, CampaignFactory, CharacterFactory

from tests.conftest import get_csrf


@pytest.fixture
def mock_character():
    """Build a factory character owned by the test session user."""
    return CharacterFactory.build(
        id="char-123",
        name="Test Character",
        campaign_id="camp-1",
        user_player_id="test-user-id",
    )


@pytest.fixture
def mock_campaign():
    """Build a factory campaign."""
    return CampaignFactory.build(id="camp-1", name="Test Campaign")


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


class TestImagesTabRendering:
    """Tests for GET /character/<id>/images via HTMX."""

    def test_images_tab_passes_assets_to_template(
        self, client, mocker, mock_character_lookup, sample_assets
    ) -> None:
        """Verify the images tab renders with asset data."""
        # Given a mocked character service returning assets
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = sample_assets

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
        self, client, mocker, mock_character_lookup, sample_assets
    ) -> None:
        """Verify hitting /character/<id>/images directly threads assets through Main.jinja."""
        # Given a mocked character service returning assets and a non-HTMX request
        _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = sample_assets

        # When requesting the images tab without HX-Request
        response = client.get("/character/char-123/images")

        # Then the page renders the carousel with the asset URLs
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "image-carousel" in body
        assert sample_assets[0].public_url in body

    def test_images_tab_shows_empty_state_for_viewer(self, client, mocker, mock_campaign) -> None:
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
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = []

        # When requesting the images tab
        response = client.get(
            f"/character/{char.id}/images",
            headers={"HX-Request": "true"},
        )

        # Then the empty state for viewers is shown
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "No images uploaded for this character" in body


class TestImageUpload:
    """Tests for POST /character/<character_id>/images."""

    def test_owner_can_upload_image(
        self, client, mocker, mock_character_lookup, sample_assets
    ) -> None:
        """Verify character owner can upload an image and gets updated carousel."""
        # Given a mocked character service
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.upload_asset.return_value = sample_assets[0]
        mock_svc.list_all_assets.return_value = sample_assets
        csrf = get_csrf(client)

        # When uploading an image
        data = {"image": (io.BytesIO(b"fake-image-data"), "photo.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the upload succeeds and returns updated content
        assert response.status_code == 200
        mock_svc.upload_asset.assert_called_once()
        body = response.get_data(as_text=True)
        assert "carousel" in body

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
        data = {"image": (io.BytesIO(b"fake-image-data"), "photo.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_invalid_mime_type_flashes_error(self, client, mocker, mock_character_lookup) -> None:
        """Verify uploading a non-image file type flashes an error."""
        # Given a mocked character service
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = []
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
        mock_svc.upload_asset.assert_not_called()

    def test_missing_file_flashes_error(self, client, mocker, mock_character_lookup) -> None:
        """Verify submitting without a file flashes an error."""
        # Given a mocked character service
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = []
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
        mock_svc.upload_asset.assert_not_called()

    def test_oversized_file_flashes_error(self, client, mocker, mock_character_lookup) -> None:
        """Verify uploading a file over 10MB flashes an error."""
        # Given a mocked character service
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = []
        csrf = get_csrf(client)

        # When uploading an oversized file
        big_data = b"x" * (10 * 1024 * 1024 + 1)
        data = {"image": (io.BytesIO(big_data), "huge.png", "image/png")}
        response = client.post(
            f"/character/{char.id}/images",
            data=data,
            content_type="multipart/form-data",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the upload is rejected
        assert response.status_code == 200
        mock_svc.upload_asset.assert_not_called()


class TestImageDelete:
    """Tests for DELETE /character/<character_id>/images/<asset_id>."""

    def test_owner_can_delete_image(self, client, mocker, mock_character_lookup) -> None:
        """Verify character owner can delete an image."""
        # Given a mocked character service
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = []
        csrf = get_csrf(client)

        # When deleting an image
        response = client.delete(
            f"/character/{char.id}/images/asset-1",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the delete succeeds
        assert response.status_code == 200
        mock_svc.delete_asset.assert_called_once_with(char.id, "asset-1")

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
        self, client, mocker, mock_character_lookup, sample_assets
    ) -> None:
        """Verify delete returns the updated images content fragment."""
        # Given a mocked character service with remaining assets
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mock_svc.list_all_assets.return_value = sample_assets[:2]
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
