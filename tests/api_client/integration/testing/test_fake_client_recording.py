"""Tests for FakeVClient request recording, response sequences, and override matching."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from vweb.api_client.exceptions import (
    FieldError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from vweb.api_client.registry import user_lookup_service, users_service
from vweb.api_client.testing import (
    FakeError,
    FakeResponse,
    FakeVClient,
    RecordedFile,
    Routes,
    UserDetailFactory,
    UserFactory,
    UserLookupResultFactory,
)


class TestRequestRecording:
    """FakeVClient should record what reaches the wire."""

    def test_records_method_path_params_body_and_headers(self):
        """Verify a request is recorded with its route, path params, JSON body, and headers."""
        with FakeVClient(default_company_id="co-1") as client:
            # When updating a user
            users_service("acting-user").update("u-1", name_first="Ada")

            # Then the request is recorded with everything the API received
            (request,) = client.requests
            assert request.method == "PATCH"
            assert request.route == Routes.USERS_UPDATE
            assert request.path == "/api/v1/companies/co-1/users/u-1"
            assert request.params == {"company_id": "co-1", "user_id": "u-1"}
            assert request.json["name_first"] == "Ada"
            assert request.headers["on-behalf-of"] == "acting-user"

    def test_records_query_parameters(self):
        """Verify query parameters are recorded."""
        with FakeVClient() as client:
            # When looking a user up by email
            user_lookup_service().by_email("a@example.com")

            # Then the query is recorded
            assert client.requests[0].query == {"email": "a@example.com"}

    def test_records_multipart_files(self):
        """Verify a multipart upload records its file parts."""
        with FakeVClient() as client:
            # When uploading an asset
            users_service("acting-user").upload_asset(
                "u-1", filename="a.png", content=b"png-bytes", content_type="image/png"
            )

            # Then the file part is recorded
            (request,) = client.requests_for(Routes.USERS_ASSETS_UPLOAD)
            assert request.files["data"] == RecordedFile(
                filename="a.png", content_type="image/png", content=b"png-bytes"
            )

    def test_unmatched_request_is_recorded_without_route(self):
        """Verify a request to an unknown path is recorded with no route."""
        with FakeVClient() as client:
            # When a request goes to a path no route defines
            client._http.get("/not/a/route")

            # Then it is recorded with route None
            assert client.requests[0].route is None
            assert client.requests[0].path == "/not/a/route"

    def test_clear_requests(self):
        """Verify clear_requests forgets earlier requests."""
        with FakeVClient() as client:
            # Given a recorded request
            user_lookup_service().by_email("a@example.com")

            # When clearing the recording
            client.clear_requests()

            # Then nothing is recorded
            assert client.requests == []

    def test_requests_for_filters_by_route_params_and_query(self):
        """Verify requests_for narrows by route, path params, and query."""
        with FakeVClient() as client:
            # Given requests to two users and a lookup
            users = users_service("acting-user")
            users.get("u-1")
            users.get("u-2")
            user_lookup_service().by_email("a@example.com")

            # Then each filter selects only its requests
            assert len(client.requests_for(Routes.USERS_GET)) == 2
            assert len(client.requests_for(Routes.USERS_GET, params={"user_id": "u-2"})) == 1
            assert len(client.requests_for(Routes.USERS_LOOKUP, query={"email": "b@x"})) == 0

    def test_requests_for_does_not_confuse_literal_and_parameter_segments(self):
        """Verify a request to /users/unapproved is not counted as a USERS_GET request."""
        with FakeVClient() as client:
            # When listing unapproved users
            users_service("acting-user").get_unapproved_page()

            # Then it belongs to the unapproved route only
            assert client.requests_for(Routes.USERS_GET) == []
            assert len(client.requests_for(Routes.USERS_UNAPPROVED_LIST)) == 1


class TestAssertions:
    """assert_called and assert_not_called should check recorded requests."""

    def test_assert_called_with_json_subset_and_params(self):
        """Verify assert_called matches path params and a subset of the body."""
        with FakeVClient() as client:
            # When updating a user
            users_service("acting-user").update("u-1", name_first="Ada")

            # Then a subset assertion passes and returns the request
            matched = client.assert_called(
                Routes.USERS_UPDATE,
                params={"user_id": "u-1"},
                json_subset={"name_first": "Ada"},
                times=1,
            )
            assert len(matched) == 1

    def test_assert_called_with_exact_json(self):
        """Verify assert_called compares the whole body when json is given."""
        with FakeVClient() as client:
            # When updating a user
            users_service("acting-user").update("u-1", name_first="Ada")

            # Then the exact body matches and a different body does not
            client.assert_called(Routes.USERS_UPDATE, json={"name_first": "Ada"})
            with pytest.raises(AssertionError, match="found 0"):
                client.assert_called(
                    Routes.USERS_UPDATE, json={"name_first": "Ada", "name_last": "Lovelace"}
                )

    def test_assert_called_fails_on_wrong_params_or_count(self):
        """Verify assert_called fails when no request matches or the count differs."""
        with FakeVClient() as client:
            # Given one request for u-1
            users_service("acting-user").get("u-1")

            # Then a different user id or a wrong count fails
            with pytest.raises(AssertionError, match="found 0"):
                client.assert_called(Routes.USERS_GET, params={"user_id": "u-2"})
            with pytest.raises(AssertionError, match="Expected 2"):
                client.assert_called(Routes.USERS_GET, times=2)

    def test_assert_called_fails_when_subset_value_differs(self):
        """Verify a json_subset with a wrong value fails."""
        with FakeVClient() as client:
            # Given an update request
            users_service("acting-user").update("u-1", name_first="Ada")

            # Then a mismatched subset fails
            with pytest.raises(AssertionError):
                client.assert_called(Routes.USERS_UPDATE, json_subset={"name_first": "Bob"})

    def test_assert_not_called(self):
        """Verify assert_not_called passes for unused routes and fails for used ones."""
        with FakeVClient() as client:
            # Given one request for u-1
            users_service("acting-user").get("u-1")

            # Then an unused route or other params pass, and the used route fails
            client.assert_not_called(Routes.USERS_DELETE)
            client.assert_not_called(Routes.USERS_GET, params={"user_id": "u-2"})
            with pytest.raises(AssertionError, match="Expected no"):
                client.assert_not_called(Routes.USERS_GET)

    def test_query_values_match_as_encoded(self):
        """Verify non-string query values match their wire encoding."""
        with FakeVClient() as client:
            # When fetching a page with an integer limit
            users_service("acting-user").get_page(limit=5)

            # Then an integer query filter matches
            client.assert_called(Routes.USERS_LIST, query={"limit": 5})


class TestResponseSequences:
    """set_responses should return successive responses."""

    def test_error_then_model_then_repeat(self):
        """Verify each call takes the next response and the last one repeats."""
        with FakeVClient() as client:
            # Given a 404 followed by a user
            user = UserDetailFactory.build(id="u-1")
            client.set_responses(
                Routes.USERS_GET, [FakeError(status_code=404), FakeResponse(model=user)]
            )
            users = users_service("acting-user")

            # Then the first call fails and later calls return the user
            with pytest.raises(NotFoundError):
                users.get("u-1")
            assert users.get("u-1").id == "u-1"
            assert users.get("u-1").id == "u-1"

    def test_sequence_with_items(self):
        """Verify a sequence wraps items in the route's envelope."""
        with FakeVClient() as client:
            # Given two different pages of users
            first, second = UserFactory.batch(2)
            client.set_responses(
                Routes.USERS_LIST,
                [FakeResponse(items=[first]), FakeResponse(items=[second])],
            )
            users = users_service("acting-user")

            # Then successive calls return each page
            assert [u.id for u in users.list_all()] == [first.id]
            assert [u.id for u in users.list_all()] == [second.id]

    def test_empty_sequence_is_rejected(self):
        """Verify an empty sequence raises ValueError."""
        with FakeVClient() as client, pytest.raises(ValueError, match="at least one"):
            client.set_responses(Routes.USERS_GET, [])

    def test_wrong_payload_kind_raises_type_error(self):
        """Verify a model for a paginated route raises TypeError."""
        with FakeVClient() as client, pytest.raises(TypeError, match="items"):
            client.set_responses(Routes.USERS_LIST, [FakeResponse(model=UserFactory.build())])

    def test_sequence_is_thread_safe(self):
        """Verify parallel requests each take one response and are all recorded."""
        with FakeVClient() as client:
            # Given a distinct response for each of 40 calls
            users = UserDetailFactory.batch(40)
            client.set_responses(Routes.USERS_GET, [FakeResponse(model=u) for u in users])
            service = users_service("acting-user")

            # When calling from many threads at once
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: service.get("u").id, range(40)))

            # Then every response was served once and every request recorded
            assert sorted(results) == sorted(u.id for u in users)
            assert len(client.requests) == 40


class TestErrorBodies:
    """set_error should produce bodies the client parses."""

    def test_invalid_parameters_become_field_errors(self):
        """Verify invalid_parameters populate ValidationError.field_errors."""
        with FakeVClient() as client:
            # Given a 400 with field errors
            client.set_error(
                Routes.USERS_UPDATE,
                status_code=400,
                detail="Invalid",
                invalid_parameters=[{"field": "name_first", "message": "Too long"}],
            )

            # When the update fails
            with pytest.raises(ValidationError) as exc_info:
                users_service("acting-user").update("u-1", name_first="x" * 5)

            # Then the field errors come from the body
            assert exc_info.value.field_errors == [
                FieldError(field="name_first", message="Too long")
            ]

    @pytest.mark.parametrize(
        ("status_code", "error_type"),
        [(500, ServerError), (503, ServerError), (429, RateLimitError)],
    )
    def test_retryable_errors_are_sent_once(self, status_code, error_type):
        """Verify the fake does not retry, so a faked 5xx or 429 is recorded once."""
        with FakeVClient() as client:
            # Given a retryable error on an idempotent route
            client.set_error(Routes.USERS_GET, status_code=status_code)

            # When the request fails
            with pytest.raises(error_type):
                users_service("acting-user").get("u-1")

            # Then it reached the API exactly once
            client.assert_called(Routes.USERS_GET, times=1)


class TestOverridePrecedence:
    """The most specific matching override should win, then the most recent."""

    def test_query_override_applies_only_to_matching_query(self):
        """Verify a query override answers only requests with that query value."""
        with FakeVClient() as client:
            # Given a lookup result only for one email
            match = UserLookupResultFactory.build(user_id="by-email")
            client.set_response(Routes.USERS_LOOKUP, items=[match], query={"email": "a@x"})
            lookup = user_lookup_service()

            # Then that email gets the override and other queries do not
            assert [r.user_id for r in lookup.by_email("a@x")] == ["by-email"]
            assert [r.user_id for r in lookup.by_discord_id("123")] != ["by-email"]

    def test_query_override_beats_generic_override(self):
        """Verify a query-specific override beats a generic one registered later."""
        with FakeVClient() as client:
            # Given an email-specific result and a later generic empty result
            match = UserLookupResultFactory.build(user_id="by-email")
            client.set_response(Routes.USERS_LOOKUP, items=[match], query={"email": "a@x"})
            client.set_response(Routes.USERS_LOOKUP, items=[])
            lookup = user_lookup_service()

            # Then the specific one answers its query and the generic one the rest
            assert [r.user_id for r in lookup.by_email("a@x")] == ["by-email"]
            assert lookup.by_discord_id("123") == []

    def test_more_values_beat_fewer(self):
        """Verify an override pinning path and query beats one pinning only the path."""
        with FakeVClient(default_company_id="co-1") as client:
            # Given a page for co-1 and a different page for co-1 at offset 100
            first, second = UserFactory.batch(2)
            client.set_response(
                Routes.USERS_LIST,
                items=[second],
                params={"company_id": "co-1"},
                query={"offset": 100},
            )
            client.set_response(Routes.USERS_LIST, items=[first], params={"company_id": "co-1"})
            users = users_service("acting-user")

            # Then the request with that offset gets the more specific override
            assert users.get_page(offset=100).items[0].id == second.id
            assert users.get_page(offset=0).items[0].id == first.id

    def test_tie_goes_to_latest_override(self):
        """Verify the most recently registered override wins among equals."""
        with FakeVClient() as client:
            # Given two generic overrides for the same route
            old, new = UserDetailFactory.batch(2)
            client.set_response(Routes.USERS_GET, model=old)
            client.set_response(Routes.USERS_GET, model=new)

            # Then the later one answers
            assert users_service("acting-user").get("u-1").id == new.id

    def test_override_does_not_answer_a_more_literal_route(self):
        """Verify a USERS_GET override does not answer /users/unapproved."""
        with FakeVClient() as client:
            # Given a USERS_GET error override
            client.set_error(Routes.USERS_GET, status_code=404)

            # Then the unapproved list still gets its default response
            page = users_service("acting-user").get_unapproved_page()
            assert len(page.items) == 1
