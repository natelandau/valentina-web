"""Tests for vweb.api_client.services.users."""

import json

import pytest
import respx

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RequestValidationError,
)
from vweb.api_client.models import (
    Asset,
    CampaignExperience,
    Note,
    PaginatedResponse,
    Quickroll,
    RollStatistics,
    User,
)


@pytest.fixture
def paginated_users_response(user_response_data) -> dict:
    """Return sample paginated users response."""
    return {
        "items": [user_response_data],
        "limit": 10,
        "offset": 0,
        "total": 1,
    }


@pytest.fixture
def asset_response_data(asset_response_data_factory) -> dict:
    """Return sample asset response data for a user."""
    return asset_response_data_factory(
        original_filename="avatar.png",
        public_url="https://example.com/avatar.png",
        user_parent_id="user123",
    )


@pytest.fixture
def experience_response_data() -> dict:
    """Return sample experience response data."""
    return {
        "campaign_id": "campaign123",
        "xp_current": 50,
        "xp_total": 100,
        "cool_points": 5,
    }


@pytest.fixture
def quickroll_response_data() -> dict:
    """Return sample quickroll response data."""
    return {
        "id": "quickroll123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "name": "Test Quickroll",
        "description": "A test quickroll",
        "user_id": "user123",
        "trait_ids": ["trait1", "trait2"],
    }


class TestUsersServiceGetPage:
    """Tests for UsersService.get_page method."""

    @respx.mock
    def test_get_page_users(self, vclient, base_url, paginated_users_response):
        """Verify get_page returns paginated User objects."""
        # Given: A mocked users list endpoint
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_users_response)

        # When: Getting a page of users
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_page()

        # Then: Returns PaginatedResponse with User objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], User)
        assert result.items[0].name_first == "Test"
        assert result.items[0].name_last == "User"
        assert result.total == 1

    @respx.mock
    def test_get_page_with_role_filter(self, vclient, base_url, paginated_users_response):
        """Verify get_page accepts role filter parameter."""
        # Given: A mocked endpoint expecting role filter
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "10", "offset": "0", "user_role": "STORYTELLER"},
        ).respond(200, json=paginated_users_response)

        # When: Getting a page with role filter
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_page(
            user_role="STORYTELLER"
        )

        # Then: Request was made with correct params
        assert route.called
        assert isinstance(result, PaginatedResponse)

    @respx.mock
    def test_get_page_with_pagination(self, vclient, base_url, user_response_data):
        """Verify get_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 25,
                "offset": 50,
                "total": 100,
            },
        )

        # When: Getting a page with custom pagination
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_page(
            limit=25, offset=50
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestUsersServiceListAll:
    """Tests for UsersService.list_all method."""

    @respx.mock
    def test_list_all_users(self, vclient, base_url, user_response_data):
        """Verify list_all returns all users across pages."""
        # Given: Mocked endpoint
        company_id = "company123"
        respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all
        result = vclient.users("on-behalf-of-user", company_id=company_id).list_all()

        # Then: Returns list of User objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], User)


class TestUsersServiceIterAll:
    """Tests for UsersService.iter_all method."""

    @respx.mock
    def test_iter_all_users(self, vclient, base_url, user_response_data):
        """Verify iter_all yields User objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company_id = "company123"
        user2 = {**user_response_data, "id": "507f1f77bcf86cd799439012", "name_first": "User 2"}
        respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 1,
                "offset": 0,
                "total": 2,
            },
        )
        respx.get(
            f"{base_url}{Endpoints.USERS.format(company_id=company_id)}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json={
                "items": [user2],
                "limit": 1,
                "offset": 1,
                "total": 2,
            },
        )

        # When: Iterating through all users
        users = list(vclient.users("on-behalf-of-user", company_id=company_id).iter_all(limit=1))

        # Then: All users are yielded as User objects
        assert len(users) == 2
        assert all(isinstance(u, User) for u in users)
        assert users[0].name_first == "Test"
        assert users[1].name_first == "User 2"


class TestUsersServiceGet:
    """Tests for UsersService.get method."""

    @respx.mock
    def test_get_user(self, vclient, base_url, user_response_data):
        """Verify getting a user returns User object."""
        # Given: A mocked user endpoint
        company_id = "company123"
        user_id = "507f1f77bcf86cd799439011"
        route = respx.get(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=user_response_data)

        # When: Getting the user
        result = vclient.users("on-behalf-of-user", company_id=company_id).get(user_id)

        # Then: Returns User object with correct data
        assert route.called
        assert isinstance(result, User)
        assert result.id == user_id
        assert result.name_first == "Test"
        assert result.name_last == "User"
        assert result.username == "testuser"
        assert result.email == "test@example.com"

    @respx.mock
    def test_get_user_not_found(self, vclient, base_url):
        """Verify getting non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "nonexistent"
        respx.get(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(404, json={"detail": "User not found"})

        # When/Then: Getting the user raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).get(user_id)

    @respx.mock
    def test_get_user_without_include_returns_detail_with_none_embeds(
        self, vclient, base_url, user_response_data
    ):
        """Verify get() with no include param returns UserDetail with None embeds."""
        from vweb.api_client.models import UserDetail

        # Given: A mocked user endpoint returning plain user data
        company_id = "company123"
        user_id = user_response_data["id"]
        route = respx.get(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=user_response_data)

        # When: Getting the user without include
        result = vclient.users("on-behalf-of-user", company_id=company_id).get(user_id)

        # Then: Returns UserDetail with None embed fields
        assert route.called
        assert isinstance(result, UserDetail)
        assert result.quickrolls is None
        assert result.notes is None
        assert result.assets is None
        assert result.characters is None

    @respx.mock
    def test_get_user_with_include_sends_repeated_query_params(
        self, vclient, base_url, user_response_data
    ):
        """Verify get() with include sends repeated query params and populates embeds."""
        # Given: A mocked endpoint returning user with embedded resources
        company_id = "company123"
        user_id = user_response_data["id"]
        payload = {**user_response_data, "quickrolls": [], "characters": []}
        route = respx.get(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=payload)

        # When: Getting user with include=["quickrolls", "characters"]
        result = vclient.users("on-behalf-of-user", company_id=company_id).get(
            user_id, include=["quickrolls", "characters"]
        )

        # Then: Request URL contains repeated include params and result has embedded data
        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "include=quickrolls" in sent_url
        assert "include=characters" in sent_url
        assert result.quickrolls == []
        assert result.characters == []
        assert result.notes is None
        assert result.assets is None


class TestUsersServiceCreate:
    """Tests for UsersService.create method."""

    @respx.mock
    def test_create_user_minimal(self, vclient, base_url, user_response_data):
        """Verify creating user with minimal data."""
        # Given: A mocked create endpoint
        company_id = "company123"
        route = respx.post(f"{base_url}{Endpoints.USERS.format(company_id=company_id)}").respond(
            201, json=user_response_data
        )

        # When: Creating a user with minimal data
        result = vclient.users("on-behalf-of-user", company_id=company_id).create(
            name_first="Test",
            name_last="User",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
        )

        # Then: Returns created User object
        assert route.called
        assert isinstance(result, User)
        assert result.name_first == "Test"
        assert result.name_last == "User"
        assert result.username == "testuser"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["name_first"] == "Test"
        assert body["name_last"] == "User"
        assert body["username"] == "testuser"
        assert body["email"] == "test@example.com"
        assert body["role"] == "PLAYER"

    @respx.mock
    def test_create_user_ignores_provider_profile(self, vclient, base_url, user_response_data):
        """Verify provider profile fields are dropped from the create request body."""
        # Given: A mocked create endpoint
        company_id = "company123"
        route = respx.post(f"{base_url}{Endpoints.USERS.format(company_id=company_id)}").respond(
            201, json=user_response_data
        )

        # When: Creating a user while passing all now-unsupported provider profiles
        result = vclient.users("on-behalf-of-user", company_id=company_id).create(
            name_first="Test",
            name_last="User",
            username="testuser",
            email="test@example.com",
            role="PLAYER",
            discord_profile={"id": "discord123", "username": "testuser"},
            google_profile={"id": "google123"},
            github_profile={"id": "github123"},
            apple_profile={"id": "apple123"},
        )

        # Then: Returns created User object
        assert route.called
        assert isinstance(result, User)

        # Then: The provider profile is not sent (writes flow through the identity endpoints)
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert "discord_profile" not in body
        assert "google_profile" not in body
        assert "github_profile" not in body
        assert "apple_profile" not in body

    def test_create_user_validation_error(self, vclient):
        """Verify validation error on invalid data raises RequestValidationError."""
        # When/Then: Creating with invalid data raises RequestValidationError
        with pytest.raises(RequestValidationError) as exc_info:
            vclient.users("on-behalf-of-user", company_id="company123").create(
                name_first="AB",
                username="abcde",
                email="test@example.com",
                role="PLAYER",
            )

        # Verify error details are accessible
        assert len(exc_info.value.errors) == 1
        assert exc_info.value.errors[0]["loc"] == ("name_first",)


class TestUsersServiceMerge:
    """Tests for UsersService.merge method."""

    @respx.mock
    def test_merge_users(self, vclient, base_url, user_response_data):
        """Verify merging users returns the primary User object."""
        # Given: A mocked merge endpoint
        company_id = "company123"
        route = respx.post(
            f"{base_url}{Endpoints.USER_MERGE.format(company_id=company_id)}"
        ).respond(200, json=user_response_data)

        # When: Merging two users
        result = vclient.users("on-behalf-of-user", company_id=company_id).merge(
            primary_user_id="primary123",
            secondary_user_id="secondary456",
        )

        # Then: Returns the primary User object
        assert route.called
        assert isinstance(result, User)

        # Verify request body
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {
            "primary_user_id": "primary123",
            "secondary_user_id": "secondary456",
        }

    @respx.mock
    def test_merge_users_not_found(self, vclient, base_url):
        """Verify merging with non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        respx.post(f"{base_url}{Endpoints.USER_MERGE.format(company_id=company_id)}").respond(
            404, json={"detail": "User not found"}
        )

        # When/Then: Merging raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).merge(
                primary_user_id="primary123",
                secondary_user_id="nonexistent",
            )


class TestUsersServiceUpdate:
    """Tests for UsersService.update method."""

    @respx.mock
    def test_update_user_name(self, vclient, base_url, user_response_data):
        """Verify updating user name."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "507f1f77bcf86cd799439011"
        updated_data = {**user_response_data, "name_first": "Updated"}
        route = respx.patch(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the user name
        result = vclient.users("on-behalf-of-user", company_id=company_id).update(
            user_id,
            name_first="Updated",
        )

        # Then: Returns updated User object
        assert route.called
        assert isinstance(result, User)
        assert result.name_first == "Updated"

        # Verify request body
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"name_first": "Updated"}

    @respx.mock
    def test_update_user_not_found(self, vclient, base_url):
        """Verify updating non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "nonexistent"
        respx.patch(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}"
        ).respond(404, json={"detail": "User not found"})

        # When/Then: Updating raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).update(
                user_id,
                name="New Name",
            )


class TestUsersServiceDelete:
    """Tests for UsersService.delete method."""

    @respx.mock
    def test_delete_user(self, vclient, base_url):
        """Verify deleting a user."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "507f1f77bcf86cd799439011"
        route = respx.delete(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}",
        ).respond(204)

        # When: Deleting the user
        result = vclient.users("on-behalf-of-user", company_id=company_id).delete(user_id)

        # Then: Request was made and returns None
        assert route.called
        assert result is None

    @respx.mock
    def test_delete_user_not_found(self, vclient, base_url):
        """Verify deleting non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "nonexistent"
        respx.delete(
            f"{base_url}{Endpoints.USER.format(company_id=company_id, user_id=user_id)}",
        ).respond(404, json={"detail": "User not found"})

        # When/Then: Deleting raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).delete(user_id)


class TestUsersServiceGetStatistics:
    """Tests for UsersService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, vclient, base_url, statistics_response_data):
        """Verify getting user statistics."""
        # Given: A mocked statistics endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_STATISTICS.format(company_id=company_id, user_id=user_id)}",
            params={"num_top_traits": "5"},
        ).respond(200, json=statistics_response_data)

        # When: Getting statistics
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_statistics(user_id)

        # Then: Returns RollStatistics object
        assert route.called
        assert isinstance(result, RollStatistics)
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0


class TestUsersServiceGetUnapprovedPage:
    """Tests for UsersService.get_unapproved_page method."""

    @respx.mock
    def test_get_unapproved_page(self, vclient, base_url, paginated_users_response):
        """Verify get_unapproved_page returns paginated User objects."""
        # Given: A mocked unapproved users endpoint
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.USERS_UNAPPROVED_LIST.format(company_id=company_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(200, json=paginated_users_response)

        # When: Getting a page of unapproved users
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_unapproved_page()

        # Then: Returns PaginatedResponse with User objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], User)

    @respx.mock
    def test_get_unapproved_page_with_pagination(self, vclient, base_url, user_response_data):
        """Verify get_unapproved_page accepts pagination parameters."""
        # Given: A mocked endpoint expecting custom pagination
        company_id = "company123"
        route = respx.get(
            f"{base_url}{Endpoints.USERS_UNAPPROVED_LIST.format(company_id=company_id)}",
            params={"limit": "25", "offset": "50"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 25,
                "offset": 50,
                "total": 100,
            },
        )

        # When: Getting a page with custom pagination
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_unapproved_page(
            limit=25, offset=50
        )

        # Then: Request was made with correct params
        assert route.called
        assert result.limit == 25
        assert result.offset == 50


class TestUsersServiceListAllUnapproved:
    """Tests for UsersService.list_all_unapproved method."""

    @respx.mock
    def test_list_all_unapproved(self, vclient, base_url, user_response_data):
        """Verify list_all_unapproved returns all unapproved users."""
        # Given: Mocked endpoint
        company_id = "company123"
        respx.get(
            f"{base_url}{Endpoints.USERS_UNAPPROVED_LIST.format(company_id=company_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all_unapproved
        result = vclient.users("on-behalf-of-user", company_id=company_id).list_all_unapproved()

        # Then: Returns list of User objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], User)


class TestUsersServiceIterAllUnapproved:
    """Tests for UsersService.iter_all_unapproved method."""

    @respx.mock
    def test_iter_all_unapproved(self, vclient, base_url, user_response_data):
        """Verify iter_all_unapproved yields User objects across pages."""
        # Given: Mocked endpoints for multiple pages
        company_id = "company123"
        user2 = {**user_response_data, "id": "507f1f77bcf86cd799439012", "name_first": "User 2"}
        respx.get(
            f"{base_url}{Endpoints.USERS_UNAPPROVED_LIST.format(company_id=company_id)}",
            params={"limit": "1", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [user_response_data],
                "limit": 1,
                "offset": 0,
                "total": 2,
            },
        )
        respx.get(
            f"{base_url}{Endpoints.USERS_UNAPPROVED_LIST.format(company_id=company_id)}",
            params={"limit": "1", "offset": "1"},
        ).respond(
            200,
            json={
                "items": [user2],
                "limit": 1,
                "offset": 1,
                "total": 2,
            },
        )

        # When: Iterating through all unapproved users
        users = list(
            vclient.users("on-behalf-of-user", company_id=company_id).iter_all_unapproved(limit=1)
        )

        # Then: All users are yielded as User objects
        assert len(users) == 2
        assert all(isinstance(u, User) for u in users)


class TestUsersServiceApproveUser:
    """Tests for UsersService.approve_user method."""

    @respx.mock
    def test_approve_user(self, vclient, base_url, user_response_data):
        """Verify approving a user returns the updated User object."""
        # Given: A mocked approve endpoint
        company_id = "company123"
        user_id = "507f1f77bcf86cd799439011"
        approved_data = {**user_response_data, "role": "PLAYER"}
        route = respx.post(
            f"{base_url}{Endpoints.USER_APPROVE.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=approved_data)

        # When: Approving the user
        result = vclient.users("on-behalf-of-user", company_id=company_id).approve_user(
            user_id, role="PLAYER"
        )

        # Then: Returns User object with assigned role
        assert route.called
        assert isinstance(result, User)
        assert result.role == "PLAYER"

        # Verify request body
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"role": "PLAYER"}

    @respx.mock
    def test_approve_user_not_found(self, vclient, base_url):
        """Verify approving non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "nonexistent"
        respx.post(
            f"{base_url}{Endpoints.USER_APPROVE.format(company_id=company_id, user_id=user_id)}"
        ).respond(404, json={"detail": "User not found"})

        # When/Then: Approving raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).approve_user(
                user_id, role="PLAYER"
            )


class TestUsersServiceDenyUser:
    """Tests for UsersService.deny_user method."""

    @respx.mock
    def test_deny_user(self, vclient, base_url):
        """Verify denying a user returns None."""
        # Given: A mocked deny endpoint
        company_id = "company123"
        user_id = "507f1f77bcf86cd799439011"
        route = respx.post(
            f"{base_url}{Endpoints.USER_DENY.format(company_id=company_id, user_id=user_id)}"
        ).respond(204)

        # When: Denying the user
        result = vclient.users("on-behalf-of-user", company_id=company_id).deny_user(user_id)

        # Then: Request was made and returns None
        assert route.called
        assert result is None

    @respx.mock
    def test_deny_user_not_found(self, vclient, base_url):
        """Verify denying non-existent user raises NotFoundError."""
        # Given: A mocked endpoint returning 404
        company_id = "company123"
        user_id = "nonexistent"
        respx.post(
            f"{base_url}{Endpoints.USER_DENY.format(company_id=company_id, user_id=user_id)}"
        ).respond(404, json={"detail": "User not found"})

        # When/Then: Denying raises NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("on-behalf-of-user", company_id=company_id).deny_user(user_id)


class TestUsersServiceAssets:
    """Tests for UsersService asset methods."""

    @respx.mock
    def test_get_assets_page(self, vclient, base_url, asset_response_data):
        """Verify getting a page of user assets."""
        # Given: A mocked assets endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_ASSETS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [asset_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Getting a page of assets
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_assets_page(user_id)

        # Then: Returns PaginatedResponse with Asset objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Asset)

    @respx.mock
    def test_list_all_assets(self, vclient, base_url, asset_response_data):
        """Verify list_all_assets returns all assets."""
        # Given: A mocked assets endpoint
        company_id = "company123"
        user_id = "user123"
        respx.get(
            f"{base_url}{Endpoints.USER_ASSETS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "100", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [asset_response_data],
                "limit": 100,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Calling list_all_assets
        result = vclient.users("on-behalf-of-user", company_id=company_id).list_all_assets(user_id)

        # Then: Returns list of Asset objects
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Asset)

    @respx.mock
    def test_get_asset(self, vclient, base_url, asset_response_data):
        """Verify getting a specific asset."""
        # Given: A mocked asset endpoint
        company_id = "company123"
        user_id = "user123"
        asset_id = "asset123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_ASSET.format(company_id=company_id, user_id=user_id, asset_id=asset_id)}"
        ).respond(200, json=asset_response_data)

        # When: Getting the asset
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_asset(
            user_id, asset_id
        )

        # Then: Returns Asset object
        assert route.called
        assert isinstance(result, Asset)
        assert result.id == "asset123"

    @respx.mock
    def test_delete_asset(self, vclient, base_url):
        """Verify deleting an asset."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        asset_id = "asset123"
        route = respx.delete(
            f"{base_url}{Endpoints.USER_ASSET.format(company_id=company_id, user_id=user_id, asset_id=asset_id)}"
        ).respond(204)

        # When: Deleting the asset
        vclient.users("on-behalf-of-user", company_id=company_id).delete_asset(user_id, asset_id)

        # Then: Request was made
        assert route.called

    @respx.mock
    def test_upload_asset(self, vclient, base_url, asset_response_data):
        """Verify uploading an asset."""
        # Given: A mocked upload endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.post(
            f"{base_url}{Endpoints.USER_ASSET_UPLOAD.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=asset_response_data)

        # When: Uploading an asset
        result = vclient.users("on-behalf-of-user", company_id=company_id).upload_asset(
            user_id,
            filename="test.png",
            content=b"fake image content",
            content_type="image/png",
        )

        # Then: Returns Asset object
        assert route.called
        assert isinstance(result, Asset)
        assert result.id == "asset123"


class TestUsersServiceExperience:
    """Tests for UsersService experience methods."""

    @respx.mock
    def test_get_experience(self, vclient, base_url, experience_response_data):
        """Verify getting user experience for a campaign."""
        # Given: A mocked experience endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_EXPERIENCE_CAMPAIGN.format(company_id=company_id, user_id=user_id, campaign_id=campaign_id)}"
        ).respond(200, json=experience_response_data)

        # When: Getting experience
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_experience(
            user_id, campaign_id
        )

        # Then: Returns CampaignExperience object
        assert route.called
        assert isinstance(result, CampaignExperience)
        assert result.campaign_id == "campaign123"

    @respx.mock
    def test_add_xp(self, vclient, base_url, experience_response_data):
        """Verify adding XP to a user."""
        # Given: A mocked add XP endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        updated_data = {**experience_response_data, "xp_current": 150, "xp_total": 200}
        route = respx.post(
            f"{base_url}{Endpoints.USER_EXPERIENCE_XP_ADD.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=updated_data)

        # When: Adding XP
        result = vclient.users("on-behalf-of-user", company_id=company_id).add_xp(
            user_id, campaign_id, amount=100
        )

        # Then: Returns updated CampaignExperience object
        assert route.called
        assert isinstance(result, CampaignExperience)
        assert result.xp_current == 150

    @respx.mock
    def test_remove_xp(self, vclient, base_url, experience_response_data):
        """Verify removing XP from a user."""
        # Given: A mocked remove XP endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        updated_data = {**experience_response_data, "xp_current": 25}
        route = respx.post(
            f"{base_url}{Endpoints.USER_EXPERIENCE_XP_REMOVE.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=updated_data)

        # When: Removing XP
        result = vclient.users("on-behalf-of-user", company_id=company_id).remove_xp(
            user_id, campaign_id, amount=25
        )

        # Then: Returns updated CampaignExperience object
        assert route.called
        assert isinstance(result, CampaignExperience)
        assert result.xp_current == 25

    @respx.mock
    def test_add_cool_points(self, vclient, base_url, experience_response_data):
        """Verify adding cool points to a user."""
        # Given: A mocked add CP endpoint
        company_id = "company123"
        user_id = "user123"
        campaign_id = "campaign123"
        updated_data = {**experience_response_data, "cool_points": 10}
        route = respx.post(
            f"{base_url}{Endpoints.USER_EXPERIENCE_CP_ADD.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=updated_data)

        # When: Adding cool points
        result = vclient.users("on-behalf-of-user", company_id=company_id).add_cool_points(
            user_id, campaign_id, amount=5
        )

        # Then: Returns updated CampaignExperience object
        assert route.called
        assert isinstance(result, CampaignExperience)
        assert result.cool_points == 10

    @respx.mock
    @pytest.mark.parametrize("method", ["add_xp", "remove_xp", "add_cool_points"])
    @pytest.mark.parametrize("amount", [0, -5])
    def test_non_positive_amount_rejected(self, vclient, method, amount):
        """Verify an amount below 1 raises RequestValidationError before any request."""
        # Given: A users service
        users = vclient.users("on-behalf-of-user", company_id="company123")

        # When/Then: A non-positive amount fails client-side validation
        with pytest.raises(RequestValidationError):
            getattr(users, method)("user123", "campaign123", amount=amount)

        # Then: No request was sent
        assert not respx.calls


class TestUsersServiceNotes:
    """Tests for UsersService note methods."""

    @respx.mock
    def test_get_notes_page(self, vclient, base_url, note_response_data):
        """Verify get_notes_page returns paginated Note objects."""
        # Given: A mocked notes list endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_NOTES.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [note_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Getting a page of notes
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_notes_page(user_id)

        # Then: Returns PaginatedResponse with Note objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Note)

    @respx.mock
    def test_get_note(self, vclient, base_url, note_response_data):
        """Verify getting a specific note returns Note object."""
        # Given: A mocked note endpoint
        company_id = "company123"
        user_id = "user123"
        note_id = "note123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_NOTE.format(company_id=company_id, user_id=user_id, note_id=note_id)}"
        ).respond(200, json=note_response_data)

        # When: Getting the note
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_note(
            user_id, note_id
        )

        # Then: Returns Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.id == "note123"

    @respx.mock
    def test_create_note(self, vclient, base_url, note_response_data):
        """Verify creating a note returns Note object."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.post(
            f"{base_url}{Endpoints.USER_NOTES.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=note_response_data)

        # When: Creating a note
        result = vclient.users("on-behalf-of-user", company_id=company_id).create_note(
            user_id,
            title="Test Note",
            content="This is test content",
        )

        # Then: Returns created Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.title == "Test Note"

    @respx.mock
    def test_update_note(self, vclient, base_url, note_response_data):
        """Verify updating a note returns Note object."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        note_id = "note123"
        updated_data = {**note_response_data, "title": "Updated Title"}
        route = respx.patch(
            f"{base_url}{Endpoints.USER_NOTE.format(company_id=company_id, user_id=user_id, note_id=note_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the note
        result = vclient.users("on-behalf-of-user", company_id=company_id).update_note(
            user_id,
            note_id,
            title="Updated Title",
        )

        # Then: Returns updated Note object
        assert route.called
        assert isinstance(result, Note)
        assert result.title == "Updated Title"

    @respx.mock
    def test_delete_note(self, vclient, base_url):
        """Verify deleting a note."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        note_id = "note123"
        route = respx.delete(
            f"{base_url}{Endpoints.USER_NOTE.format(company_id=company_id, user_id=user_id, note_id=note_id)}"
        ).respond(204)

        # When: Deleting the note
        vclient.users("on-behalf-of-user", company_id=company_id).delete_note(user_id, note_id)

        # Then: Request was made
        assert route.called


class TestUsersServiceQuickrolls:
    """Tests for UsersService quickroll methods."""

    @respx.mock
    def test_get_quickrolls_page(self, vclient, base_url, quickroll_response_data):
        """Verify get_quickrolls_page returns paginated Quickroll objects."""
        # Given: A mocked quickrolls list endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_QUICKROLLS.format(company_id=company_id, user_id=user_id)}",
            params={"limit": "10", "offset": "0"},
        ).respond(
            200,
            json={
                "items": [quickroll_response_data],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
        )

        # When: Getting a page of quickrolls
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_quickrolls_page(
            user_id
        )

        # Then: Returns PaginatedResponse with Quickroll objects
        assert route.called
        assert isinstance(result, PaginatedResponse)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Quickroll)

    @respx.mock
    def test_get_quickroll(self, vclient, base_url, quickroll_response_data):
        """Verify getting a specific quickroll returns Quickroll object."""
        # Given: A mocked quickroll endpoint
        company_id = "company123"
        user_id = "user123"
        quickroll_id = "quickroll123"
        route = respx.get(
            f"{base_url}{Endpoints.USER_QUICKROLL.format(company_id=company_id, user_id=user_id, quickroll_id=quickroll_id)}"
        ).respond(200, json=quickroll_response_data)

        # When: Getting the quickroll
        result = vclient.users("on-behalf-of-user", company_id=company_id).get_quickroll(
            user_id, quickroll_id
        )

        # Then: Returns Quickroll object
        assert route.called
        assert isinstance(result, Quickroll)
        assert result.id == "quickroll123"

    @respx.mock
    def test_create_quickroll(self, vclient, base_url, quickroll_response_data):
        """Verify creating a quickroll returns Quickroll object."""
        # Given: A mocked create endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.post(
            f"{base_url}{Endpoints.USER_QUICKROLLS.format(company_id=company_id, user_id=user_id)}"
        ).respond(201, json=quickroll_response_data)

        # When: Creating a quickroll
        result = vclient.users("on-behalf-of-user", company_id=company_id).create_quickroll(
            user_id,
            name="Test Quickroll",
            description="A test quickroll",
            trait_ids=["trait1", "trait2"],
        )

        # Then: Returns created Quickroll object
        assert route.called
        assert isinstance(result, Quickroll)
        assert result.name == "Test Quickroll"

    @respx.mock
    def test_update_quickroll(self, vclient, base_url, quickroll_response_data):
        """Verify updating a quickroll returns Quickroll object."""
        # Given: A mocked update endpoint
        company_id = "company123"
        user_id = "user123"
        quickroll_id = "quickroll123"
        updated_data = {**quickroll_response_data, "name": "Updated Name"}
        route = respx.patch(
            f"{base_url}{Endpoints.USER_QUICKROLL.format(company_id=company_id, user_id=user_id, quickroll_id=quickroll_id)}"
        ).respond(200, json=updated_data)

        # When: Updating the quickroll
        result = vclient.users("on-behalf-of-user", company_id=company_id).update_quickroll(
            user_id,
            quickroll_id,
            name="Updated Name",
        )

        # Then: Returns updated Quickroll object
        assert route.called
        assert isinstance(result, Quickroll)
        assert result.name == "Updated Name"

    @respx.mock
    def test_delete_quickroll(self, vclient, base_url):
        """Verify deleting a quickroll."""
        # Given: A mocked delete endpoint
        company_id = "company123"
        user_id = "user123"
        quickroll_id = "quickroll123"
        route = respx.delete(
            f"{base_url}{Endpoints.USER_QUICKROLL.format(company_id=company_id, user_id=user_id, quickroll_id=quickroll_id)}"
        ).respond(204)

        # When: Deleting the quickroll
        vclient.users("on-behalf-of-user", company_id=company_id).delete_quickroll(
            user_id, quickroll_id
        )

        # Then: Request was made
        assert route.called


class TestUsersServiceFactoryMethod:
    """Tests for VClient.users factory method."""

    def test_users_method_returns_service(self, vclient):
        """Verify users method returns UsersService instance."""
        # When: Calling the users method
        service = vclient.users("on-behalf-of-user", company_id="company123")

        # Then: Returns a UsersService instance
        from vweb.api_client.services.users import UsersService

        assert isinstance(service, UsersService)

    def test_users_method_creates_new_instance(self, vclient):
        """Verify users method creates new instance each call."""
        # When: Calling the users method multiple times
        service1 = vclient.users("on-behalf-of-user", company_id="company123")
        service2 = vclient.users("on-behalf-of-user", company_id="company123")

        # Then: Returns different instances (not cached)
        assert service1 is not service2

    def test_users_method_stores_company_id(self, vclient):
        """Verify users method stores company_id on the service."""
        # When: Calling the users method with a company_id
        service = vclient.users("on-behalf-of-user", company_id="company123")

        # Then: The service has the company_id stored
        assert service._company_id == "company123"


class TestUsersServiceLinkIdentity:
    """Tests for UsersService.link_identity method."""

    @respx.mock
    def test_link_identity_success(self, vclient, base_url, user_response_data):
        """Verify linking a provider identity returns the updated User."""
        # Given: A mocked identities endpoint
        company_id = "company123"
        route = respx.post(
            f"{base_url}{Endpoints.USER_IDENTITIES.format(company_id=company_id, user_id='user123')}"
        ).respond(200, json=user_response_data)

        # When: Linking an apple identity to the user
        result = vclient.users("user123", company_id=company_id).link_identity(
            "user123",
            provider="apple",
            token="eyJraWQi...",
        )

        # Then: The updated User is returned and the body carries the credential
        assert route.called
        assert isinstance(result, User)
        body = json.loads(route.calls.last.request.content)
        assert body == {"provider": "apple", "token": "eyJraWQi..."}

        # Then: The request acts on behalf of the user
        assert route.calls.last.request.headers["On-Behalf-Of"] == "user123"

    @respx.mock
    def test_link_identity_conflict(self, vclient, base_url):
        """Verify a 409 response raises ConflictError with its code."""
        # Given: The identity already belongs to another user
        company_id = "company123"
        respx.post(
            f"{base_url}{Endpoints.USER_IDENTITIES.format(company_id=company_id, user_id='user123')}"
        ).respond(
            409,
            json={
                "detail": "This identity is already linked to another user.",
                "code": "IDENTITY_ALREADY_LINKED",
            },
        )

        # When/Then: The conflict surfaces with its code
        with pytest.raises(ConflictError) as exc_info:
            vclient.users("user123", company_id=company_id).link_identity(
                "user123",
                provider="apple",
                token="eyJraWQi...",
            )
        assert exc_info.value.code == "IDENTITY_ALREADY_LINKED"

    @respx.mock
    def test_link_identity_forbidden(self, vclient, base_url):
        """Verify a 403 response raises AuthorizationError."""
        # Given: A non-admin acting on another user's account
        company_id = "company123"
        respx.post(
            f"{base_url}{Endpoints.USER_IDENTITIES.format(company_id=company_id, user_id='other456')}"
        ).respond(
            403,
            json={"detail": "Only the user themselves or an admin can link identities"},
        )

        # When/Then: The request is denied
        with pytest.raises(AuthorizationError):
            vclient.users("user123", company_id=company_id).link_identity(
                "other456",
                provider="apple",
                token="eyJraWQi...",
            )

    @respx.mock
    def test_link_identity_missing_token_fails_client_side(self, vclient):
        """Verify an empty token raises RequestValidationError before any request."""
        # When/Then: Client-side validation rejects the empty token
        with pytest.raises(RequestValidationError):
            vclient.users("user123", company_id="company123").link_identity(
                "user123",
                provider="apple",
                token="",
            )


class TestUsersServiceUnlinkIdentity:
    """Tests for UsersService.unlink_identity method."""

    @respx.mock
    def test_unlink_identity_success(self, vclient, base_url, user_response_data):
        """Verify unlinking a provider identity returns the updated User."""
        # Given: A mocked provider identity endpoint
        company_id = "company123"
        route = respx.delete(
            f"{base_url}{Endpoints.USER_IDENTITY.format(company_id=company_id, user_id='user123', provider='discord')}"
        ).respond(200, json=user_response_data)

        # When: Disconnecting the discord identity from the user
        result = vclient.users("user123", company_id=company_id).unlink_identity(
            "user123",
            provider="discord",
        )

        # Then: The updated User is returned
        assert route.called
        assert isinstance(result, User)

        # Then: The request acts on behalf of the user
        assert route.calls.last.request.headers["On-Behalf-Of"] == "user123"

    @respx.mock
    def test_unlink_identity_not_linked(self, vclient, base_url):
        """Verify a 404 response raises NotFoundError with its code."""
        # Given: The user has no identity from the requested provider
        company_id = "company123"
        respx.delete(
            f"{base_url}{Endpoints.USER_IDENTITY.format(company_id=company_id, user_id='user123', provider='github')}"
        ).respond(
            404,
            json={
                "detail": "The user has no github identity linked.",
                "code": "IDENTITY_NOT_LINKED",
            },
        )

        # When/Then: The missing identity surfaces with its code
        with pytest.raises(NotFoundError) as exc_info:
            vclient.users("user123", company_id=company_id).unlink_identity(
                "user123",
                provider="github",
            )
        assert exc_info.value.code == "IDENTITY_NOT_LINKED"

    @respx.mock
    def test_unlink_identity_last_identity_conflict(self, vclient, base_url):
        """Verify a 409 response raises ConflictError with its code."""
        # Given: The provider is the user's only linked identity
        company_id = "company123"
        respx.delete(
            f"{base_url}{Endpoints.USER_IDENTITY.format(company_id=company_id, user_id='user123', provider='google')}"
        ).respond(
            409,
            json={
                "detail": "Cannot remove the last remaining identity.",
                "code": "LAST_IDENTITY",
            },
        )

        # When/Then: The conflict surfaces with its code
        with pytest.raises(ConflictError) as exc_info:
            vclient.users("user123", company_id=company_id).unlink_identity(
                "user123",
                provider="google",
            )
        assert exc_info.value.code == "LAST_IDENTITY"

    @respx.mock
    def test_unlink_identity_forbidden(self, vclient, base_url):
        """Verify a 403 response raises AuthorizationError."""
        # Given: A non-admin acting on another user's account
        company_id = "company123"
        respx.delete(
            f"{base_url}{Endpoints.USER_IDENTITY.format(company_id=company_id, user_id='other456', provider='apple')}"
        ).respond(
            403,
            json={"detail": "Only the user themselves or an admin can unlink identities"},
        )

        # When/Then: The request is denied
        with pytest.raises(AuthorizationError):
            vclient.users("user123", company_id=company_id).unlink_identity(
                "other456",
                provider="apple",
            )


class TestUsersServiceAvatar:
    """Tests for UsersService avatar methods."""

    @respx.mock
    def test_upload_avatar_success(self, vclient, base_url, user_response_data):
        """Verify uploading an avatar PUTs multipart data and returns the updated User."""
        # Given: A mocked avatar endpoint returning a user with a new avatar_url
        company_id = "company123"
        user_id = "user123"
        updated = {**user_response_data, "avatar_url": "https://cdn.example.com/a.webp"}
        route = respx.put(
            f"{base_url}{Endpoints.USER_AVATAR.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=updated)

        # When: Uploading an avatar on the user's own behalf
        result = vclient.users("user123", company_id=company_id).upload_avatar(
            user_id,
            filename="pic.png",
            content=b"fake image content",
            content_type="image/png",
        )

        # Then: The updated User is returned with the new avatar_url
        assert route.called
        assert isinstance(result, User)
        assert result.avatar_url == "https://cdn.example.com/a.webp"

        # Then: The request is multipart and acts on behalf of the user
        assert route.calls.last.request.headers["On-Behalf-Of"] == "user123"
        assert "multipart/form-data" in route.calls.last.request.headers["content-type"]

    @respx.mock
    def test_upload_avatar_guesses_content_type(self, vclient, base_url, user_response_data):
        """Verify content_type is inferred from the filename when not provided."""
        # Given: A mocked avatar endpoint
        company_id = "company123"
        user_id = "user123"
        route = respx.put(
            f"{base_url}{Endpoints.USER_AVATAR.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=user_response_data)

        # When: Uploading without an explicit content_type
        result = vclient.users("user123", company_id=company_id).upload_avatar(
            user_id,
            filename="pic.png",
            content=b"fake image content",
        )

        # Then: The request succeeds and returns a User
        assert route.called
        assert isinstance(result, User)

    @respx.mock
    def test_delete_avatar_success(self, vclient, base_url, user_response_data):
        """Verify deleting an avatar returns the updated User body (200, not 204)."""
        # Given: A mocked avatar endpoint returning the user with avatar_url cleared
        company_id = "company123"
        user_id = "user123"
        updated = {**user_response_data, "avatar_url": None}
        route = respx.delete(
            f"{base_url}{Endpoints.USER_AVATAR.format(company_id=company_id, user_id=user_id)}"
        ).respond(200, json=updated)

        # When: Removing the avatar
        result = vclient.users("user123", company_id=company_id).delete_avatar(user_id)

        # Then: The updated User is returned and acts on behalf of the user
        assert route.called
        assert isinstance(result, User)
        assert result.avatar_url is None
        assert route.calls.last.request.headers["On-Behalf-Of"] == "user123"

    @respx.mock
    def test_delete_avatar_not_found(self, vclient, base_url):
        """Verify a 404 response raises NotFoundError."""
        # Given: The avatar endpoint returns 404
        company_id = "company123"
        user_id = "user123"
        respx.delete(
            f"{base_url}{Endpoints.USER_AVATAR.format(company_id=company_id, user_id=user_id)}"
        ).respond(404, json={"detail": "User not found"})

        # When/Then: The error surfaces as NotFoundError
        with pytest.raises(NotFoundError):
            vclient.users("user123", company_id=company_id).delete_avatar(user_id)
