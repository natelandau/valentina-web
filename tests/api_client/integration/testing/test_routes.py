"""Integration tests for FakeVClient.set_response() and set_error()."""

import pytest

from tests.api_client.payloads import wire
from vweb.api_client.constants import REQUEST_ID_HEADER
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.registry import books_service, campaigns_service, users_service
from vweb.api_client.routes import Routes
from vweb.api_client.testing import CampaignBookFactory, CampaignFactory, FakeVClient, UserFactory


class TestSetResponsePaginated:
    """set_response() should correctly handle paginated routes."""

    @pytest.mark.parametrize("as_dicts", [False, True], ids=["models", "dicts"])
    @pytest.mark.parametrize("count", [0, 2])
    def test_items_are_served_as_a_page(self, count, as_dicts):
        """Verify items given as models or dicts come back as a page with a matching total."""
        with FakeVClient() as client:
            # Given users set on a paginated route
            users = UserFactory.batch(count)
            items = [wire(u) for u in users] if as_dicts else users
            client.set_response(Routes.USERS_LIST, items=items)

            # When getting a page of users
            result = users_service("on-behalf-of-user").get_page()

            # Then the page holds exactly those users and reports their count
            assert [u.id for u in result.items] == [u.id for u in users]
            assert result.total == count


class TestSetResponseSingle:
    """set_response() should correctly handle single-object routes."""

    @pytest.mark.parametrize(
        ("route", "factory", "as_dict", "call"),
        [
            (
                Routes.CAMPAIGNS_GET,
                CampaignFactory,
                False,
                lambda obj_id: campaigns_service("on-behalf-of-user").get(obj_id),
            ),
            (
                Routes.CAMPAIGNS_GET,
                CampaignFactory,
                True,
                lambda obj_id: campaigns_service("on-behalf-of-user").get(obj_id),
            ),
            (
                Routes.BOOKS_RENUMBER,
                CampaignBookFactory,
                False,
                lambda obj_id: books_service("campaign123", "on-behalf-of-user").renumber(
                    obj_id, 5
                ),
            ),
        ],
        ids=["get-model", "get-dict", "put-model"],
    )
    def test_model_is_served(self, route, factory, as_dict, call):
        """Verify a model or dict set on a single-object route is what the service returns."""
        with FakeVClient() as client:
            # Given a model set on the route
            obj = factory.build()
            client.set_response(route, model=wire(obj) if as_dict else obj)

            # When calling the service
            result = call(obj.id)

            # Then the model is returned
            assert result.id == obj.id


class TestSetError:
    """set_error() should make routes return error responses."""

    def test_error_carries_detail_and_code(self):
        """Verify set_error raises the mapped exception with the given detail and code."""
        with FakeVClient() as client:
            # Given a 404 with a custom detail and code
            client.set_error(
                Routes.CAMPAIGNS_GET,
                status_code=404,
                detail="Campaign not found",
                code="CAMPAIGN_NOT_FOUND",
            )

            # When fetching a campaign
            # Then the error exposes the detail and code
            with pytest.raises(NotFoundError, match="Campaign not found") as exc_info:
                campaigns_service("on-behalf-of-user").get("nonexistent")
            assert exc_info.value.code == "CAMPAIGN_NOT_FOUND"


class TestSetResponseWithParams:
    """set_response() and set_error() with params should apply only to matching path values."""

    def test_params_override_with_generic_fallback(self):
        """Verify parameterized override wins over generic for matching ID."""
        with FakeVClient() as client:
            # Given a generic override and a parameterized override
            generic = CampaignFactory.build()
            specific = CampaignFactory.build()
            client.set_response(Routes.CAMPAIGNS_GET, model=generic)
            client.set_response(
                Routes.CAMPAIGNS_GET,
                model=specific,
                params={"campaign_id": "target-id"},
            )

            svc = campaigns_service("on-behalf-of-user")

            # Then the targeted campaign gets the parameterized override
            assert svc.get("target-id").id == specific.id

            # Then a different campaign gets the generic fallback
            assert svc.get("other-id").id == generic.id

    def test_set_error_with_params(self):
        """Verify set_error with params only errors for the matching ID."""
        with FakeVClient() as client:
            # Given a 404 error only for a specific campaign
            client.set_error(
                Routes.CAMPAIGNS_GET,
                status_code=404,
                params={"campaign_id": "missing"},
            )

            svc = campaigns_service("on-behalf-of-user")

            # When fetching the missing campaign
            with pytest.raises(NotFoundError):
                svc.get("missing")

            # When fetching a different campaign, the default response is used
            result = svc.get("other")
            assert result.id is not None


class TestSetResponseValidation:
    """set_response() should enforce correct kwarg usage per route style."""

    @pytest.mark.parametrize(
        ("route", "kwargs", "match"),
        [
            (Routes.USERS_LIST, {"model": UserFactory.build()}, r"paginated.*items"),
            (Routes.CAMPAIGNS_GET, {"items": [CampaignFactory.build()]}, r"single object.*model"),
            (
                Routes.CAMPAIGNS_GET,
                {"model": CampaignFactory.build(), "total": 5},
                r"'total' and 'offset' need a paginated route",
            ),
        ],
        ids=["paginated-needs-items", "single-needs-model", "total-needs-paginated"],
    )
    def test_wrong_payload_kind_raises_type_error(self, route, kwargs, match):
        """Verify passing the payload kind the route does not return raises TypeError."""
        with FakeVClient() as client, pytest.raises(TypeError, match=match):
            client.set_response(route, **kwargs)


class TestRequestIdHeader:
    """FakeVClient should include X-Request-Id header on all responses."""

    def test_each_response_has_a_unique_request_id(self):
        """Verify every successful response carries its own X-Request-Id."""
        with FakeVClient() as client:
            # When making two requests
            response1 = client._http.get("/api/v1/companies")
            response2 = client._http.get("/api/v1/companies")

            # Then each carries a request ID and they differ
            assert response1.headers[REQUEST_ID_HEADER] != response2.headers[REQUEST_ID_HEADER]

    def test_error_body_request_id_matches_header(self):
        """Verify an error response carries the same request ID in its header and body."""
        with FakeVClient() as client:
            # Given a route set to return 404
            client.set_error(Routes.CAMPAIGNS_GET, status_code=404)

            # When fetching a campaign
            response = client._http.get("/api/v1/companies/fake-company/campaigns/camp1")

            # Then body request_id matches header
            assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]
