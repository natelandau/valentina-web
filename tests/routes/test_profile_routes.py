"""Profile route tests: viewing, editing, avatars, and experience."""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_post
from tests.helpers import make_image_bytes
from vweb.api_client.models.users import CampaignExperience, GitHubProfile
from vweb.api_client.testing import Routes, UserFactory
from vweb.constants import MAX_AVATAR_SIZE
from vweb.lib.cache.global_context import GlobalContext

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

    from vweb.api_client.constants import GrantXPPermission
    from vweb.api_client.models import User

VALID_FORM = {"username": "testuser", "email": "test@example.com"}


@pytest.fixture
def profile_user() -> User:
    """Build the session user, linked only to GitHub."""
    return UserFactory.build(
        id="test-user-id",
        name_first="Test",
        name_last="User",
        username="testuser",
        email="test@example.com",
        company_id="test-company-id",
        github_profile=GitHubProfile(id="gh-1"),
        discord_profile=None,
        google_profile=None,
        apple_profile=None,
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


@pytest.fixture(autouse=True)
def _mock_profile_api(use_context, profile_context) -> None:
    """Serve the two-user GlobalContext."""
    use_context(profile_context)


def _post_profile(
    client: FlaskClient, user_id: str = "test-user-id", **fields: object
) -> TestResponse:
    """POST the profile edit form as a multipart HTMX request."""
    return htmx_post(client, f"/profile/{user_id}", fields, content_type="multipart/form-data")


class TestProfileGet:
    """Tests for GET /profile/<user_id>."""

    @pytest.mark.parametrize("own", [True, False], ids=["own", "other"])
    def test_edit_and_connect_offered_only_on_own_profile(
        self, client: FlaskClient, *, own: bool
    ) -> None:
        """Verify only your own profile links to editing and to connecting unlinked providers."""
        user_id = "test-user-id" if own else "other-user-id"

        response = client.get(f"/profile/{user_id}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert (f"/profile/{user_id}/edit" in body) is own
        assert ("/auth/discord/link" in body) is own
        assert ("/auth/google/link" in body) is own
        assert "/auth/github/link" not in body

    def test_nonexistent_user_returns_404(self, client: FlaskClient) -> None:
        """Verify 404 for a user that doesn't exist."""
        assert client.get("/profile/nonexistent-id").status_code == 404

    def test_header_shows_resolved_avatar(self, client: FlaskClient, profile_user: User) -> None:
        """Verify the header renders the user's resolved avatar as an image, not escaped text."""
        profile_user.avatar_url = "https://cdn.example.com/custom.webp"

        body = client.get("/profile/test-user-id").get_data(as_text=True)

        assert re.search(r'<img[^>]*src="https://cdn\.example\.com/custom\.webp"', body)

    def test_lazy_loads_user_statistics(self, client: FlaskClient) -> None:
        """Verify the profile lazy-loads statistics scoped to the user."""
        body = client.get("/profile/test-user-id").get_data(as_text=True)

        assert "/cards/statistics?" in body
        assert "user_id=test-user-id" in body


class TestProfileEditForm:
    """Tests for GET /profile/<user_id>/edit."""

    def test_own_edit_form_is_prefilled_and_accepts_avatar(self, client: FlaskClient) -> None:
        """Verify the edit form holds the user's values and accepts an avatar upload."""
        response = client.get("/profile/test-user-id/edit", headers={"HX-Request": "true"})

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'value="testuser"' in body
        assert "multipart/form-data" in body
        assert 'name="avatar"' in body


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/profile/other-user-id/edit"), ("POST", "/profile/other-user-id")],
    ids=["edit-form", "submit"],
)
def test_cannot_edit_another_users_profile(
    client: FlaskClient, fake_vclient, method: str, path: str
) -> None:
    """Verify a user can neither open nor submit another user's profile form."""
    data = {
        "csrf_token": get_csrf(client),
        "username": "hacked",
        "email": "hacker@example.com",
        "avatar": (io.BytesIO(make_image_bytes()), "me.png", "image/png"),
    }

    response = client.open(
        path,
        method=method,
        data=data if method == "POST" else None,
        content_type="multipart/form-data" if method == "POST" else None,
    )

    assert response.status_code == 403
    assert fake_vclient.requests == []


class TestProfilePost:
    """Tests for POST /profile/<user_id>."""

    def test_valid_update_is_sent_and_redirects(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a successful profile update sends the new fields and reloads the profile."""
        response = _post_profile(
            client,
            name_first="Updated",
            name_last="Name",
            username="updateduser",
            email="updated@example.com",
        )

        assert response.headers["HX-Redirect"] == "/profile/test-user-id"
        fake_vclient.assert_called(
            Routes.USERS_UPDATE,
            params={"user_id": "test-user-id"},
            json={
                "username": "updateduser",
                "email": "updated@example.com",
                "name_first": "Updated",
                "name_last": "Name",
            },
            times=1,
        )

    @pytest.mark.parametrize(
        "fields",
        [
            {"username": "", "email": "kept@example.com"},
            {"username": "keptuser", "email": ""},
            {"username": "keptuser", "email": "not-an-email"},
            {"username": "keptuser", "email": "kept@example.com", "name_first": "Al"},
        ],
        ids=["missing-username", "missing-email", "invalid-email", "short-first-name"],
    )
    def test_invalid_form_rerenders_without_saving(
        self, client: FlaskClient, fake_vclient, fields: dict[str, str]
    ) -> None:
        """Verify an invalid form re-renders with the entered values and sends nothing."""
        response = _post_profile(client, **fields)

        assert response.status_code == 200
        assert "HX-Redirect" not in response.headers
        body = response.get_data(as_text=True)
        for value in fields.values():
            if value:
                assert f'value="{value}"' in body
        fake_vclient.assert_not_called(Routes.USERS_UPDATE)

    def test_conflict_rerenders_form_with_api_message(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a taken username re-renders the form with the API's message."""
        fake_vclient.set_error(
            Routes.USERS_UPDATE, status_code=409, detail="Username is already in use"
        )

        response = _post_profile(client, username="taken", email="updated@example.com")

        assert response.status_code == 200
        assert "HX-Redirect" not in response.headers
        assert "Username is already in use" in response.get_data(as_text=True)

    @pytest.mark.parametrize("avatar_changed", [True, False], ids=["avatar-removed", "no-avatar"])
    def test_conflict_refreshes_context_only_after_avatar_change(
        self, client: FlaskClient, fake_vclient, mocker, *, avatar_changed: bool
    ) -> None:
        """Verify a refused update still shows the avatar outcome and drops the stale context."""
        # Given an update the API refuses, with or without a successful avatar removal
        fake_vclient.set_error(
            Routes.USERS_UPDATE, status_code=409, detail="Username is already in use"
        )
        clear = mocker.patch("vweb.routes.profile.views.cache.global_context.clear_current")
        extra = {"remove_avatar": "1"} if avatar_changed else {}

        # When submitting the form
        response = _post_profile(client, username="taken", email="u@example.com", **extra)

        # Then the flash container is swapped in with the form, and the context is
        # cleared only when the avatar changed
        assert 'hx-swap-oob="true"' in response.get_data(as_text=True)
        assert clear.called is avatar_changed


class TestProfileAvatar:
    """Tests for avatar upload and removal through the profile form."""

    def test_valid_avatar_is_uploaded(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a valid avatar file reaches the API and the profile reloads."""
        response = _post_profile(
            client, **VALID_FORM, avatar=(io.BytesIO(make_image_bytes()), "me.png", "image/png")
        )

        assert "HX-Redirect" in response.headers
        (upload,) = fake_vclient.assert_called(
            Routes.USERS_AVATAR_UPLOAD, params={"user_id": "test-user-id"}, times=1
        )
        assert upload.files["data"].filename == "me.png"

    @pytest.mark.parametrize(
        ("avatar", "expect_upload", "expect_delete"),
        [
            (None, False, True),
            ((make_image_bytes(), "me.png", "image/png"), True, False),
            ((b"not-an-image", "doc.pdf", "application/pdf"), False, False),
        ],
        ids=["remove-only", "new-file-wins", "rejected-file-keeps-avatar"],
    )
    def test_remove_checkbox_reverts_only_without_a_new_file(
        self,
        client: FlaskClient,
        fake_vclient,
        avatar: tuple[bytes, str, str] | None,
        *,
        expect_upload: bool,
        expect_delete: bool,
    ) -> None:
        """Verify remove deletes the avatar only when no file was supplied, even a rejected one."""
        extra = {"avatar": (io.BytesIO(avatar[0]), avatar[1], avatar[2])} if avatar else {}

        _post_profile(client, **VALID_FORM, remove_avatar="on", **extra)

        assert bool(fake_vclient.requests_for(Routes.USERS_AVATAR_UPLOAD)) is expect_upload
        assert bool(fake_vclient.requests_for(Routes.USERS_AVATAR_DELETE)) is expect_delete

    @pytest.mark.parametrize(
        "avatar",
        [
            (b"not-an-image", "doc.pdf", "application/pdf"),
            (b"x" * (MAX_AVATAR_SIZE + 1), "huge.png", "image/png"),
            (make_image_bytes(6000, 4001), "huge.png", "image/png"),
        ],
        ids=["wrong-type", "oversized", "over-24-megapixels"],
    )
    def test_invalid_avatar_is_not_uploaded(
        self, client: FlaskClient, fake_vclient, avatar: tuple[bytes, str, str]
    ) -> None:
        """Verify an unsupported, oversized, or too-large image is never uploaded."""
        content, filename, mime = avatar

        response = _post_profile(client, **VALID_FORM, avatar=(io.BytesIO(content), filename, mime))

        assert response.status_code == 200
        fake_vclient.assert_not_called(Routes.USERS_AVATAR_UPLOAD)


class TestExperience:
    """Tests for the profile experience card and grant form."""

    @pytest.fixture
    def experienced_user(self, profile_user: User, profile_context: GlobalContext) -> str:
        """Give the session user experience in the context's campaign."""
        campaign = profile_context.campaigns[0]
        profile_user.campaign_experience = [
            CampaignExperience(
                id="ce-1",
                user_id=profile_user.id,
                campaign_id=campaign.id,
                xp_current=7,
                xp_total=1234,
                cool_points=3,
            )
        ]
        return campaign.id

    @pytest.fixture
    def grant_permission(self, profile_context: GlobalContext):
        """Set the company's grant-experience permission."""

        def _set(value: GrantXPPermission) -> None:
            profile_context.company.settings.permission_grant_xp = value

        return _set

    def test_card_shows_lifetime_totals_per_campaign(
        self, client: FlaskClient, profile_context: GlobalContext, experienced_user: str
    ) -> None:
        """Verify the experience card lists each campaign's experience and lifetime totals."""
        response = client.get("/profile/test-user-id/experience", headers={"HX-Request": "true"})

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert profile_context.campaigns[0].name in body
        assert "1,234" in body

    def test_card_for_unknown_user_returns_404(self, client: FlaskClient) -> None:
        """Verify the experience card 404s for a user who does not exist."""
        assert client.get("/profile/nobody/experience").status_code == 404

    @pytest.mark.parametrize(
        ("setting", "target", "allowed"),
        [
            ("STORYTELLER", "test-user-id", False),
            ("PLAYER", "test-user-id", True),
            ("PLAYER", "other-user-id", False),
            ("UNRESTRICTED", "other-user-id", True),
        ],
        ids=["denied", "player-self", "player-other", "unrestricted"],
    )
    @pytest.mark.parametrize("endpoint", ["form", "submit"])
    def test_grant_respects_company_permission(
        self,
        client: FlaskClient,
        fake_vclient,
        grant_permission,
        experienced_user: str,
        *,
        setting: GrantXPPermission,
        target: str,
        allowed: bool,
        endpoint: str,
    ) -> None:
        """Verify a player may open and submit the grant form only as the company allows."""
        # Given a PLAYER under the company's grant setting
        grant_permission(setting)
        base = f"/profile/{target}/experience/{experienced_user}"

        # When opening the form or submitting a grant
        if endpoint == "form":
            response = client.get(f"{base}/form", headers={"HX-Request": "true"})
        else:
            response = htmx_post(client, base, {"xp": "5", "cool_points": "0"})

        # Then it is allowed or forbidden, and a forbidden grant never reaches the API
        assert (response.status_code != 403) is allowed
        if not allowed:
            fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_XP_ADD)

    def test_grant_sends_xp_and_refreshes_card(
        self, client: FlaskClient, fake_vclient, grant_permission, experienced_user: str
    ) -> None:
        """Verify a grant reaches the API and the experience card reloads."""
        grant_permission("UNRESTRICTED")

        response = htmx_post(
            client,
            f"/profile/other-user-id/experience/{experienced_user}",
            {"xp": "5", "cool_points": "0"},
        )

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.USERS_EXPERIENCE_XP_ADD,
            params={"user_id": "other-user-id"},
            json_subset={"amount": 5, "campaign_id": experienced_user},
            times=1,
        )
        assert 'hx-get="/profile/other-user-id/experience"' in response.get_data(as_text=True)

    def test_invalid_grant_rerenders_form_without_calling_api(
        self, client: FlaskClient, fake_vclient, grant_permission, experienced_user: str
    ) -> None:
        """Verify an invalid amount re-renders the form with the entry and grants nothing."""
        grant_permission("UNRESTRICTED")

        response = htmx_post(
            client,
            f"/profile/other-user-id/experience/{experienced_user}",
            {"xp": "-1", "cool_points": "0"},
        )

        assert response.status_code == 200
        assert 'value="-1"' in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_XP_ADD)
