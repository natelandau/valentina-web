"""Profile route tests."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models.users import GitHubProfile
from vclient.testing import UserFactory

from vweb.lib.cache.global_context import GlobalContext

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from vclient.models import User


@pytest.fixture
def profile_user() -> User:
    """Build a user for profile tests."""
    return UserFactory.build(
        id="test-user-id",
        name_first="Test",
        name_last="User",
        username="testuser",
        email="test@example.com",
        company_id="test-company-id",
    )


@pytest.fixture
def other_user() -> User:
    """Build a second user for viewing other profiles."""
    return UserFactory.build(
        id="other-user-id",
        name_first="Other",
        name_last="Person",
        username="otherperson",
        email="other@example.com",
        company_id="test-company-id",
    )


@pytest.fixture
def profile_context(mock_global_context, profile_user, other_user) -> GlobalContext:
    """Build a GlobalContext with both users."""
    return GlobalContext(
        company=mock_global_context.company,
        users=[profile_user, other_user],
        campaigns=mock_global_context.campaigns,
        characters_by_campaign=mock_global_context.characters_by_campaign,
        resources_modified_at=mock_global_context.resources_modified_at,
    )


@pytest.fixture
def _mock_profile_api(mocker, profile_context) -> MagicMock:
    """Mock API calls for profile routes.

    Override the autouse _mock_api fixture to provide a two-user GlobalContext.
    """
    mocker.patch("vweb.lib.cache.global_context.load", return_value=profile_context)
    mocker.patch("vweb.lib.cache.global_context.clear")

    mock_svc = MagicMock()
    mock_svc.list_all_quickrolls.return_value = []
    mocker.patch("vweb.routes.profile.views.sync_users_service", return_value=mock_svc)

    return mock_svc


@pytest.fixture
def mock_profile_svc(_mock_profile_api: MagicMock) -> MagicMock:
    """Expose the mock users service for assertion in tests."""
    return _mock_profile_api


class TestProfileGet:
    """Tests for GET /profile/<user_id>."""

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_own_profile_returns_200(self, client: FlaskClient) -> None:
        """Verify own profile page renders successfully."""
        response = client.get("/profile/test-user-id")
        assert response.status_code == 200

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_profile_renders_avatar_markup(self, client: FlaskClient) -> None:
        """Verify the page header avatar renders as real HTML, not escaped text."""
        # When loading a profile page
        response = client.get("/profile/test-user-id")

        # Then the avatar markup survives autoescaping
        body = response.get_data(as_text=True)
        assert '<div class="avatar' in body
        assert "&lt;div class=" not in body

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_own_profile_shows_edit_button(self, client: FlaskClient) -> None:
        """Verify own profile shows the Edit Profile button with the correct HTMX URL."""
        response = client.get("/profile/test-user-id")
        assert (
            b"profile.edit_profile" in response.data
            or b"/profile/test-user-id/edit" in response.data
        )

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_other_profile_returns_200(self, client: FlaskClient) -> None:
        """Verify viewing another user's profile renders successfully."""
        response = client.get("/profile/other-user-id")
        assert response.status_code == 200

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_other_profile_hides_edit_button(self, client: FlaskClient) -> None:
        """Verify another user's profile omits the edit endpoint URL."""
        response = client.get("/profile/other-user-id")
        assert b"/profile/other-user-id/edit" not in response.data

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_nonexistent_user_returns_404(self, client: FlaskClient) -> None:
        """Verify 404 for a user that doesn't exist."""
        response = client.get("/profile/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_profile_renders_lazy_statistics_url(self, client: FlaskClient) -> None:
        """Verify Profile renders the /cards/statistics lazy-load URL with user_id."""
        # Given a profile for an existing user
        # When requesting the profile page
        response = client.get("/profile/test-user-id")

        # Then the rendered HTML includes the lazy-load URL scoped to the user
        assert b"/cards/statistics?" in response.data
        assert b"user_id=test-user-id" in response.data


class TestProfileEdit:
    """Tests for GET /profile/<user_id>/edit."""

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_edit_own_profile_returns_form(self, client: FlaskClient) -> None:
        """Verify edit form fragment is returned for own profile."""
        response = client.get("/profile/test-user-id/edit")
        assert response.status_code == 200
        assert b"testuser" in response.data

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_edit_other_profile_returns_403(self, client: FlaskClient) -> None:
        """Verify 403 when trying to edit another user's profile."""
        response = client.get("/profile/other-user-id/edit")
        assert response.status_code == 403

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_edit_form_has_avatar_upload_field(self, client: FlaskClient) -> None:
        """Verify the edit form renders a multipart avatar file input."""
        # Given the session user views their own edit form
        # When requesting the edit form fragment
        response = client.get("/profile/test-user-id/edit", headers={"HX-Request": "true"})

        # Then it exposes a multipart file input named avatar
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "multipart/form-data" in body
        assert 'name="avatar"' in body
        assert "file-input" in body


class TestProfilePost:
    """Tests for POST /profile/<user_id>."""

    def test_post_own_profile_updates_user(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify successful profile update calls svc.update with a UserUpdate object."""
        from vclient.models.users import UserUpdate

        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/profile/test-user-id",
            data={
                "csrf_token": csrf,
                "name_first": "Updated",
                "name_last": "Name",
                "username": "updateduser",
                "email": "updated@example.com",
            },
        )

        assert response.status_code == 200
        assert "HX-Redirect" in response.headers

        mock_profile_svc.update.assert_called_once()
        call_args = mock_profile_svc.update.call_args
        assert call_args[0][0] == "test-user-id"
        update_req: UserUpdate = call_args[1]["request"]
        assert isinstance(update_req, UserUpdate)
        assert update_req.username == "updateduser"
        assert update_req.email == "updated@example.com"
        assert update_req.name_first == "Updated"
        assert update_req.name_last == "Name"

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_post_other_profile_returns_403(self, client: FlaskClient) -> None:
        """Verify 403 when trying to POST to another user's profile."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/profile/other-user-id",
            data={
                "csrf_token": csrf,
                "username": "hacked",
                "email": "hacker@example.com",
            },
        )
        assert response.status_code == 403

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_post_missing_username_shows_error(self, client: FlaskClient) -> None:
        """Verify validation error when username is missing."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/profile/test-user-id",
            data={
                "csrf_token": csrf,
                "name_first": "Test",
                "name_last": "User",
                "username": "",
                "email": "test@example.com",
            },
        )
        assert response.status_code == 200
        assert b"Username is required" in response.data

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_post_missing_email_shows_error(self, client: FlaskClient) -> None:
        """Verify validation error when email is missing."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/profile/test-user-id",
            data={
                "csrf_token": csrf,
                "name_first": "Test",
                "name_last": "User",
                "username": "testuser",
                "email": "",
            },
        )
        assert response.status_code == 200
        assert b"Email is required" in response.data


class TestConnectionsCard:
    """Tests for connections rendering on the profile page."""

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_own_profile_shows_connect_for_unlinked_provider(
        self, client: FlaskClient, profile_user, other_user, mocker
    ) -> None:
        """Verify your own profile offers a Connect link for providers you lack."""
        # Given the requesting user has only a GitHub identity
        profile_user.github_profile = GitHubProfile(id="gh-1")
        profile_user.discord_profile = None
        profile_user.google_profile = None
        profile_user.apple_profile = None

        # When viewing your own profile
        response = client.get("/profile/test-user-id")

        # Then the card offers links for the unlinked providers only
        body = response.get_data(as_text=True)
        assert "Connections" in body
        assert "/auth/discord/link" in body
        assert "/auth/google/link" in body
        assert "/auth/github/link" not in body

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_other_profile_hides_connections_card(self, client: FlaskClient, other_user) -> None:
        """Verify someone else's profile does not render the Connections card."""
        # Given another user with no linked providers
        other_user.discord_profile = None
        other_user.github_profile = None
        other_user.google_profile = None
        other_user.apple_profile = None

        # When viewing the other user's profile
        response = client.get("/profile/other-user-id")

        # Then no Connections card is rendered
        body = response.get_data(as_text=True)
        assert "/auth/discord/link" not in body
        assert "Connections" not in body


class TestProfileAvatar:
    """Tests for avatar upload/remove via POST /profile/<user_id>."""

    def test_owner_can_upload_avatar(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify a user can upload an avatar and the service is called."""
        from tests.conftest import get_csrf

        # Given the session user and a valid image
        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "username": "testuser",
            "email": "test@example.com",
            "avatar": (io.BytesIO(b"fake-image-bytes"), "me.png", "image/png"),
        }

        # When posting the edit form with an avatar file
        response = client.post(
            "/profile/test-user-id", data=data, content_type="multipart/form-data"
        )

        # Then the avatar is uploaded and the page redirects
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers
        mock_profile_svc.upload_avatar.assert_called_once()
        assert mock_profile_svc.upload_avatar.call_args[0][0] == "test-user-id"

    def test_remove_avatar_calls_delete(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify the remove checkbox triggers delete_avatar."""
        from tests.conftest import get_csrf

        # Given the remove checkbox is checked and no new file is supplied
        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "username": "testuser",
            "email": "test@example.com",
            "remove_avatar": "on",
        }

        # When posting the edit form
        response = client.post(
            "/profile/test-user-id", data=data, content_type="multipart/form-data"
        )

        # Then the custom avatar is deleted
        assert response.status_code == 200
        mock_profile_svc.delete_avatar.assert_called_once_with("test-user-id")

    def test_uploaded_file_takes_priority_over_remove(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify a new file is uploaded even if remove is also set."""
        from tests.conftest import get_csrf

        # Given both a new file and the remove checkbox
        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "username": "testuser",
            "email": "test@example.com",
            "remove_avatar": "on",
            "avatar": (io.BytesIO(b"fake-image-bytes"), "me.png", "image/png"),
        }

        # When posting the edit form
        client.post("/profile/test-user-id", data=data, content_type="multipart/form-data")

        # Then upload wins and delete is not called
        mock_profile_svc.upload_avatar.assert_called_once()
        mock_profile_svc.delete_avatar.assert_not_called()

    def test_invalid_avatar_type_is_rejected(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify a non-image file is not uploaded."""
        from tests.conftest import get_csrf

        # Given a PDF masquerading as an avatar
        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "username": "testuser",
            "email": "test@example.com",
            "avatar": (io.BytesIO(b"not-an-image"), "doc.pdf", "application/pdf"),
        }

        # When posting the edit form
        response = client.post(
            "/profile/test-user-id", data=data, content_type="multipart/form-data"
        )

        # Then the upload is rejected
        assert response.status_code == 200
        mock_profile_svc.upload_avatar.assert_not_called()

    def test_oversized_avatar_is_rejected(
        self, client: FlaskClient, mock_profile_svc: MagicMock
    ) -> None:
        """Verify a file over 5 MB is not uploaded."""
        from tests.conftest import get_csrf

        # Given a 5 MB + 1 byte image
        csrf = get_csrf(client)
        big = b"x" * (5 * 1024 * 1024 + 1)
        data = {
            "csrf_token": csrf,
            "username": "testuser",
            "email": "test@example.com",
            "avatar": (io.BytesIO(big), "huge.png", "image/png"),
        }

        # When posting the edit form
        response = client.post(
            "/profile/test-user-id", data=data, content_type="multipart/form-data"
        )

        # Then the upload is rejected
        assert response.status_code == 200
        mock_profile_svc.upload_avatar.assert_not_called()

    @pytest.mark.usefixtures("_mock_profile_api")
    def test_non_self_avatar_upload_returns_403(self, client: FlaskClient) -> None:
        """Verify a user cannot upload an avatar to another profile."""
        from tests.conftest import get_csrf

        # Given a post to another user's profile
        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "username": "otherperson",
            "email": "other@example.com",
            "avatar": (io.BytesIO(b"fake"), "me.png", "image/png"),
        }

        # When posting the edit form
        response = client.post(
            "/profile/other-user-id", data=data, content_type="multipart/form-data"
        )

        # Then it is forbidden
        assert response.status_code == 403
