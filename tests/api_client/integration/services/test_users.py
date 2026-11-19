"""Tests for vweb.api_client.services.users."""

import pytest
import respx

from tests.api_client.payloads import endpoint_url, page, sent_json, sent_params, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import PaginatedResponse
from vweb.api_client.testing import CampaignExperienceFactory, QuickrollFactory

COMPANY_ID = "company123"
USER_ID = "user123"
CAMPAIGN_ID = "campaign123"
QUICKROLL_ID = "quickroll123"


@pytest.fixture
def users(vclient):
    """Return a users service acting on behalf of a user."""
    return vclient.users("on-behalf-of-user", company_id=COMPANY_ID)


@pytest.fixture
def experience_response_data() -> dict:
    """Return campaign experience response data."""
    return wire(CampaignExperienceFactory.build(campaign_id=CAMPAIGN_ID))


@pytest.fixture
def quickroll_response_data() -> dict:
    """Return quickroll response data."""
    return wire(QuickrollFactory.build(id=QUICKROLL_ID, name="Test Quickroll"))


class TestUsersServiceGetPage:
    """Tests for UsersService.get_page method."""

    @respx.mock
    @pytest.mark.parametrize(
        ("kwargs", "expected_params"),
        [
            pytest.param({}, {"limit": "10", "offset": "0"}, id="defaults"),
            pytest.param({"limit": 25, "offset": 50}, {"limit": "25", "offset": "50"}, id="paging"),
            pytest.param(
                {"user_role": "STORYTELLER", "email": "a@example.com"},
                {
                    "limit": "10",
                    "offset": "0",
                    "user_role": "STORYTELLER",
                    "email": "a@example.com",
                },
                id="filters",
            ),
        ],
    )
    def test_get_page_sends_filters_and_parses_users(
        self, users, base_url, user_response_data, kwargs, expected_params
    ):
        """Verify get_page sends paging and filter params and parses the users."""
        # Given: A mocked users list endpoint
        route = respx.get(endpoint_url(base_url, Endpoints.USERS, company_id=COMPANY_ID)).respond(
            200, json=page(user_response_data)
        )

        # When: Getting a page of users
        result = users.get_page(**kwargs)

        # Then: The params are sent and the users are parsed
        assert sent_params(route) == expected_params
        assert [u.name_first for u in result.items] == ["Test"]
        assert result.total == 1


class TestUsersServiceCollectionMethods:
    """Tests for the list, iterate, and page methods that wrap paginated routes."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "args", "kwargs", "endpoint", "expected_params", "item"),
        [
            pytest.param(
                "list_all",
                (),
                {"user_role": "PLAYER", "email": "a@example.com"},
                Endpoints.USERS,
                {"limit": "100", "offset": "0", "user_role": "PLAYER", "email": "a@example.com"},
                "user",
                id="list_all",
            ),
            pytest.param(
                "iter_all",
                (),
                {"user_role": "PLAYER"},
                Endpoints.USERS,
                {"limit": "100", "offset": "0", "user_role": "PLAYER"},
                "user",
                id="iter_all",
            ),
            pytest.param(
                "get_unapproved_page",
                (),
                {"limit": 25, "offset": 50},
                Endpoints.USERS_UNAPPROVED_LIST,
                {"limit": "25", "offset": "50"},
                "user",
                id="get_unapproved_page",
            ),
            pytest.param(
                "list_all_unapproved",
                (),
                {},
                Endpoints.USERS_UNAPPROVED_LIST,
                {"limit": "100", "offset": "0"},
                "user",
                id="list_all_unapproved",
            ),
            pytest.param(
                "iter_all_unapproved",
                (),
                {},
                Endpoints.USERS_UNAPPROVED_LIST,
                {"limit": "100", "offset": "0"},
                "user",
                id="iter_all_unapproved",
            ),
            pytest.param(
                "get_quickrolls_page",
                (USER_ID,),
                {},
                Endpoints.USER_QUICKROLLS,
                {"limit": "10", "offset": "0"},
                "quickroll",
                id="get_quickrolls_page",
            ),
            pytest.param(
                "list_all_quickrolls",
                (USER_ID,),
                {},
                Endpoints.USER_QUICKROLLS,
                {"limit": "100", "offset": "0"},
                "quickroll",
                id="list_all_quickrolls",
            ),
            pytest.param(
                "iter_all_quickrolls",
                (USER_ID,),
                {},
                Endpoints.USER_QUICKROLLS,
                {"limit": "100", "offset": "0"},
                "quickroll",
                id="iter_all_quickrolls",
            ),
        ],
    )
    def test_collection_method_requests_route_and_parses_items(
        self,
        users,
        base_url,
        user_response_data,
        quickroll_response_data,
        method,
        args,
        kwargs,
        endpoint,
        expected_params,
        item,
    ):
        """Verify each collection method requests its route and parses the items."""
        # Given: The route returns one page holding one item
        payload = user_response_data if item == "user" else quickroll_response_data
        route = respx.get(
            endpoint_url(base_url, endpoint, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(200, json=page(payload))

        # When: Calling the collection method
        result = getattr(users, method)(*args, **kwargs)
        items = result.items if isinstance(result, PaginatedResponse) else list(result)

        # Then: The route gets the expected params and the item is parsed
        assert sent_params(route) == expected_params
        assert [i.id for i in items] == [payload["id"]]


class TestUsersServiceGet:
    """Tests for UsersService.get method."""

    @respx.mock
    def test_get_user_without_include(self, users, base_url, user_response_data):
        """Verify get() sends no include param and leaves embeds unset."""
        # Given: A mocked user endpoint returning plain user data
        user_id = user_response_data["id"]
        route = respx.get(
            endpoint_url(base_url, Endpoints.USER, company_id=COMPANY_ID, user_id=user_id)
        ).respond(200, json=user_response_data)

        # When: Getting the user without include
        result = users.get(user_id)

        # Then: No query is sent, the user is parsed, and embeds are None
        assert not sent_params(route)
        assert result.id == user_id
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert result.quickrolls is None
        assert result.notes is None
        assert result.assets is None
        assert result.characters is None

    @respx.mock
    def test_get_user_with_include_sends_repeated_query_params(
        self, users, base_url, user_response_data
    ):
        """Verify get() with include sends repeated query params and populates embeds."""
        # Given: A mocked endpoint returning user with embedded resources
        user_id = user_response_data["id"]
        payload = {**user_response_data, "quickrolls": [], "characters": []}
        route = respx.get(
            endpoint_url(base_url, Endpoints.USER, company_id=COMPANY_ID, user_id=user_id)
        ).respond(200, json=payload)

        # When: Getting user with include=["quickrolls", "characters"]
        result = users.get(user_id, include=["quickrolls", "characters"])

        # Then: Each include is a separate query param and the embeds are populated
        assert route.calls.last.request.url.params.get_list("include") == [
            "quickrolls",
            "characters",
        ]
        assert result.quickrolls == []
        assert result.characters == []
        assert result.notes is None
        assert result.assets is None


class TestUsersServiceCreate:
    """Tests for UsersService.create method."""

    @respx.mock
    def test_create_user_sends_fields_and_drops_provider_profiles(
        self, users, base_url, user_response_data
    ):
        """Verify create sends the user fields and never the provider profiles."""
        # Given: A mocked create endpoint
        route = respx.post(endpoint_url(base_url, Endpoints.USERS, company_id=COMPANY_ID)).respond(
            201, json=user_response_data
        )

        # When: Creating a user while passing provider profiles
        result = users.create(
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

        # Then: Only the user fields are sent, since identities flow through their own endpoints
        assert sent_json(route) == {
            "name_first": "Test",
            "name_last": "User",
            "username": "testuser",
            "email": "test@example.com",
            "role": "PLAYER",
        }
        assert result.username == "testuser"

    @respx.mock
    def test_create_user_validation_error(self, users):
        """Verify invalid data raises RequestValidationError naming the field, before sending."""
        # When/Then: Creating with a too-short first name fails client-side
        with pytest.raises(RequestValidationError) as exc_info:
            users.create(
                name_first="AB",
                username="abcde",
                email="test@example.com",
                role="PLAYER",
            )

        assert [e["loc"] for e in exc_info.value.errors] == [("name_first",)]
        assert not respx.calls


class TestUsersServiceMerge:
    """Tests for UsersService.merge method."""

    @respx.mock
    def test_merge_users(self, users, base_url, user_response_data):
        """Verify merging users sends both ids and returns the primary User."""
        # Given: A mocked merge endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.USER_MERGE, company_id=COMPANY_ID)
        ).respond(200, json=user_response_data)

        # When: Merging two users
        result = users.merge(primary_user_id="primary123", secondary_user_id="secondary456")

        # Then: Both ids are sent and the primary user is returned
        assert sent_json(route) == {
            "primary_user_id": "primary123",
            "secondary_user_id": "secondary456",
        }
        assert result.id == user_response_data["id"]


class TestUsersServiceUpdate:
    """Tests for UsersService.update method."""

    @respx.mock
    @pytest.mark.parametrize(
        ("kwargs", "expected_body"),
        [
            pytest.param({"name_first": "Updated"}, {"name_first": "Updated"}, id="set"),
            pytest.param(
                {"username": "renamed", "name_first": None, "name_last": None},
                {"username": "renamed", "name_first": None, "name_last": None},
                id="explicit-null-clears",
            ),
        ],
    )
    def test_update_user_sends_only_given_fields(
        self, users, base_url, user_response_data, kwargs, expected_body
    ):
        """Verify update sends only the fields passed, keeping explicit nulls."""
        # Given: A mocked update endpoint
        route = respx.patch(
            endpoint_url(base_url, Endpoints.USER, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(200, json={**user_response_data, "name_first": "Updated"})

        # When: Updating the user
        result = users.update(USER_ID, **kwargs)

        # Then: Only the given fields are sent and the response is parsed
        assert sent_json(route) == expected_body
        assert result.name_first == "Updated"


class TestUsersServiceNoContentActions:
    """Tests for user actions that return no body."""

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "http_method", "endpoint"),
        [
            pytest.param("delete", "DELETE", Endpoints.USER, id="delete"),
            pytest.param("deny_user", "POST", Endpoints.USER_DENY, id="deny_user"),
        ],
    )
    def test_action_hits_user_route(self, users, base_url, method, http_method, endpoint):
        """Verify the action sends the right method to the user's route and returns None."""
        # Given: A mocked endpoint returning 204
        route = respx.route(
            method=http_method,
            url=endpoint_url(base_url, endpoint, company_id=COMPANY_ID, user_id=USER_ID),
        )
        route.respond(204)

        # When: Running the action
        result = getattr(users, method)(USER_ID)

        # Then: The route was called and nothing is returned
        assert route.call_count == 1
        assert result is None


class TestUsersServiceGetStatistics:
    """Tests for UsersService.get_statistics method."""

    @respx.mock
    def test_get_statistics(self, users, base_url, statistics_response_data):
        """Verify get_statistics sends the default top-trait count and parses the stats."""
        # Given: A mocked statistics endpoint
        route = respx.get(
            endpoint_url(
                base_url, Endpoints.USER_STATISTICS, company_id=COMPANY_ID, user_id=USER_ID
            )
        ).respond(200, json=statistics_response_data)

        # When: Getting statistics
        result = users.get_statistics(USER_ID)

        # Then: The default param is sent and the stats are parsed
        assert sent_params(route) == {"num_top_traits": "5"}
        assert result.total_rolls == 100
        assert result.success_percentage == 50.0


class TestUsersServiceApproveUser:
    """Tests for UsersService.approve_user method."""

    @respx.mock
    def test_approve_user(self, users, base_url, user_response_data):
        """Verify approving a user sends the role and returns the updated User."""
        # Given: A mocked approve endpoint
        route = respx.post(
            endpoint_url(base_url, Endpoints.USER_APPROVE, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(200, json={**user_response_data, "role": "PLAYER"})

        # When: Approving the user
        result = users.approve_user(USER_ID, role="PLAYER")

        # Then: The role is sent and the user is returned with it
        assert sent_json(route) == {"role": "PLAYER"}
        assert result.role == "PLAYER"


class TestUsersServiceExperience:
    """Tests for UsersService experience methods."""

    @respx.mock
    def test_get_experience(self, users, base_url, experience_response_data):
        """Verify getting user experience for a campaign."""
        # Given: A mocked experience endpoint
        route = respx.get(
            endpoint_url(
                base_url,
                Endpoints.USER_EXPERIENCE_CAMPAIGN,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                campaign_id=CAMPAIGN_ID,
            )
        ).respond(200, json=experience_response_data)

        # When: Getting experience
        result = users.get_experience(USER_ID, CAMPAIGN_ID)

        # Then: The campaign experience is returned
        assert route.call_count == 1
        assert result.campaign_id == CAMPAIGN_ID

    @respx.mock
    @pytest.mark.parametrize(
        ("method", "endpoint"),
        [
            pytest.param("add_xp", Endpoints.USER_EXPERIENCE_XP_ADD, id="add_xp"),
            pytest.param("remove_xp", Endpoints.USER_EXPERIENCE_XP_REMOVE, id="remove_xp"),
            pytest.param("add_cool_points", Endpoints.USER_EXPERIENCE_CP_ADD, id="add_cp"),
        ],
    )
    def test_experience_change_sends_amount_and_campaign(
        self, users, base_url, experience_response_data, method, endpoint
    ):
        """Verify each experience change posts the amount and campaign to its route."""
        # Given: A mocked experience change endpoint
        route = respx.post(
            endpoint_url(base_url, endpoint, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(201, json={**experience_response_data, "xp_current": 150})

        # When: Changing the experience
        result = getattr(users, method)(USER_ID, CAMPAIGN_ID, amount=25)

        # Then: The amount and campaign are sent and the new experience is returned
        assert sent_json(route) == {"amount": 25, "campaign_id": CAMPAIGN_ID}
        assert result.xp_current == 150

    @respx.mock
    @pytest.mark.parametrize("method", ["add_xp", "remove_xp", "add_cool_points"])
    @pytest.mark.parametrize("amount", [0, -5])
    def test_non_positive_amount_rejected(self, users, method, amount):
        """Verify an amount below 1 raises RequestValidationError before any request."""
        # When/Then: A non-positive amount fails client-side validation
        with pytest.raises(RequestValidationError):
            getattr(users, method)(USER_ID, CAMPAIGN_ID, amount=amount)

        # Then: No request was sent
        assert not respx.calls


class TestUsersServiceQuickrolls:
    """Tests for UsersService quickroll methods."""

    @respx.mock
    def test_get_quickroll(self, users, base_url, quickroll_response_data):
        """Verify getting a specific quickroll returns it."""
        # Given: A mocked quickroll endpoint
        route = respx.get(
            endpoint_url(
                base_url,
                Endpoints.USER_QUICKROLL,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                quickroll_id=QUICKROLL_ID,
            )
        ).respond(200, json=quickroll_response_data)

        # When: Getting the quickroll
        result = users.get_quickroll(USER_ID, QUICKROLL_ID)

        # Then: The quickroll is returned
        assert route.call_count == 1
        assert result.id == QUICKROLL_ID

    @respx.mock
    def test_create_quickroll(self, users, base_url, quickroll_response_data):
        """Verify creating a quickroll sends its fields and returns it."""
        # Given: A mocked create endpoint
        route = respx.post(
            endpoint_url(
                base_url, Endpoints.USER_QUICKROLLS, company_id=COMPANY_ID, user_id=USER_ID
            )
        ).respond(201, json=quickroll_response_data)

        # When: Creating a quickroll
        result = users.create_quickroll(
            USER_ID,
            name="Test Quickroll",
            description="A test quickroll",
            trait_ids=["trait1", "trait2"],
        )

        # Then: The fields are sent and the quickroll is returned
        assert sent_json(route) == {
            "name": "Test Quickroll",
            "description": "A test quickroll",
            "trait_ids": ["trait1", "trait2"],
        }
        assert result.name == "Test Quickroll"

    @respx.mock
    def test_update_quickroll(self, users, base_url, quickroll_response_data):
        """Verify updating a quickroll sends only the changed fields."""
        # Given: A mocked update endpoint
        route = respx.patch(
            endpoint_url(
                base_url,
                Endpoints.USER_QUICKROLL,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                quickroll_id=QUICKROLL_ID,
            )
        ).respond(200, json={**quickroll_response_data, "name": "Updated Name"})

        # When: Updating the quickroll
        result = users.update_quickroll(USER_ID, QUICKROLL_ID, name="Updated Name")

        # Then: Only the name is sent and the updated quickroll is returned
        assert sent_json(route) == {"name": "Updated Name"}
        assert result.name == "Updated Name"

    @respx.mock
    def test_delete_quickroll(self, users, base_url):
        """Verify deleting a quickroll calls its route."""
        # Given: A mocked delete endpoint
        route = respx.delete(
            endpoint_url(
                base_url,
                Endpoints.USER_QUICKROLL,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                quickroll_id=QUICKROLL_ID,
            )
        ).respond(204)

        # When: Deleting the quickroll
        users.delete_quickroll(USER_ID, QUICKROLL_ID)

        # Then: The route was called
        assert route.call_count == 1


class TestUsersServiceIdentities:
    """Tests for UsersService link_identity and unlink_identity methods."""

    @respx.mock
    def test_link_identity(self, vclient, base_url, user_response_data):
        """Verify linking sends the credential on behalf of the user and returns the User."""
        # Given: A mocked identities endpoint
        route = respx.post(
            endpoint_url(
                base_url, Endpoints.USER_IDENTITIES, company_id=COMPANY_ID, user_id=USER_ID
            )
        ).respond(200, json=user_response_data)

        # When: Linking an apple identity to the user
        result = vclient.users(USER_ID, company_id=COMPANY_ID).link_identity(
            USER_ID, provider="apple", token="eyJraWQi..."
        )

        # Then: The credential is sent on behalf of the user
        assert sent_json(route) == {"provider": "apple", "token": "eyJraWQi..."}
        assert route.calls.last.request.headers["On-Behalf-Of"] == USER_ID
        assert result.id == user_response_data["id"]

    @respx.mock
    def test_link_identity_empty_token_fails_client_side(self, vclient):
        """Verify an empty token raises RequestValidationError before any request."""
        # When/Then: Client-side validation rejects the empty token
        with pytest.raises(RequestValidationError):
            vclient.users(USER_ID, company_id=COMPANY_ID).link_identity(
                USER_ID, provider="apple", token=""
            )

        assert not respx.calls

    @respx.mock
    def test_unlink_identity(self, vclient, base_url, user_response_data):
        """Verify unlinking deletes the provider's identity on behalf of the user."""
        # Given: A mocked provider identity endpoint
        route = respx.delete(
            endpoint_url(
                base_url,
                Endpoints.USER_IDENTITY,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                provider="discord",
            )
        ).respond(200, json=user_response_data)

        # When: Disconnecting the discord identity from the user
        result = vclient.users(USER_ID, company_id=COMPANY_ID).unlink_identity(
            USER_ID, provider="discord"
        )

        # Then: The request acts on behalf of the user and returns the updated User
        assert route.calls.last.request.headers["On-Behalf-Of"] == USER_ID
        assert result.id == user_response_data["id"]


class TestUsersServiceAvatar:
    """Tests for UsersService avatar methods."""

    @respx.mock
    def test_upload_avatar(self, vclient, base_url, user_response_data):
        """Verify uploading an avatar PUTs the file as multipart and returns the User."""
        # Given: A mocked avatar endpoint returning a user with a new avatar_url
        route = respx.put(
            endpoint_url(base_url, Endpoints.USER_AVATAR, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(200, json={**user_response_data, "avatar_url": "https://cdn.example.com/a.webp"})

        # When: Uploading an avatar on the user's own behalf
        result = vclient.users(USER_ID, company_id=COMPANY_ID).upload_avatar(
            USER_ID,
            filename="pic.png",
            content=b"fake image content",
            content_type="image/png",
        )

        # Then: The file is sent as multipart on behalf of the user
        request = route.calls.last.request
        assert request.headers["On-Behalf-Of"] == USER_ID
        assert "multipart/form-data" in request.headers["content-type"]
        assert b'filename="pic.png"' in request.content
        assert b"Content-Type: image/png" in request.content
        assert b"fake image content" in request.content
        assert result.avatar_url == "https://cdn.example.com/a.webp"

    @respx.mock
    def test_delete_avatar(self, vclient, base_url, user_response_data):
        """Verify deleting an avatar parses the 200 body into the updated User."""
        # Given: A mocked avatar endpoint returning the user with avatar_url cleared
        route = respx.delete(
            endpoint_url(base_url, Endpoints.USER_AVATAR, company_id=COMPANY_ID, user_id=USER_ID)
        ).respond(200, json={**user_response_data, "avatar_url": None})

        # When: Removing the avatar
        result = vclient.users(USER_ID, company_id=COMPANY_ID).delete_avatar(USER_ID)

        # Then: The updated User is returned and the request acts on behalf of the user
        assert route.calls.last.request.headers["On-Behalf-Of"] == USER_ID
        assert result.id == user_response_data["id"]
        assert result.avatar_url is None
