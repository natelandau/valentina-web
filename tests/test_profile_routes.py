"""Profile route tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import UserFactory

from vweb.lib.global_context import GlobalContext

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
        books_by_campaign=mock_global_context.books_by_campaign,
        characters_by_campaign=mock_global_context.characters_by_campaign,
        resources_modified_at=mock_global_context.resources_modified_at,
    )


@pytest.fixture
def _mock_profile_api(mocker, profile_context) -> MagicMock:
    """Mock API calls for profile routes.

    Override the autouse _mock_api fixture to provide a two-user GlobalContext.
    """
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=profile_context)
    mocker.patch("vweb.lib.hooks.clear_global_context_cache")

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
