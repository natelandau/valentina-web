"""Tests for the _FakeRouter."""

import json

import httpx2

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.testing._router import _FakeRouter


class TestFakeRouterPatternMatching:
    """Router should match requests to registered routes."""

    def test_matches_simple_endpoint(self):
        router = _FakeRouter()
        request = httpx2.Request("GET", "https://fake.test/api/v1/health")
        response = router.handle(request)
        assert response.status_code == 200

    def test_matches_parameterized_endpoint(self):
        router = _FakeRouter()
        request = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/abc123/campaigns",
        )
        response = router.handle(request)
        assert response.status_code == 200
        body = json.loads(response.content)
        assert "items" in body
        assert "total" in body

    def test_detail_endpoint_returns_single_object(self):
        router = _FakeRouter()
        request = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/abc/campaigns/c1",
        )
        response = router.handle(request)
        assert response.status_code == 200
        body = json.loads(response.content)
        assert "items" not in body
        assert "id" in body

    def test_delete_returns_204(self):
        router = _FakeRouter()
        request = httpx2.Request(
            "DELETE",
            "https://fake.test/api/v1/companies/abc/campaigns/c1",
        )
        response = router.handle(request)
        assert response.status_code == 204

    def test_unmatched_route_returns_404(self):
        router = _FakeRouter()
        request = httpx2.Request("GET", "https://fake.test/api/v1/nonexistent")
        response = router.handle(request)
        assert response.status_code == 404


class TestFakeRouterOverrides:
    """Router should support user-defined route overrides."""

    def test_override_replaces_default(self):
        router = _FakeRouter()
        custom_json = {"items": [{"id": "custom"}], "total": 1, "limit": 10, "offset": 0}
        router.add_route("GET", Endpoints.CAMPAIGNS, json=custom_json)
        request = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/abc/campaigns",
        )
        response = router.handle(request)
        body = json.loads(response.content)
        assert body["items"][0]["id"] == "custom"

    def test_override_with_status_code(self):
        router = _FakeRouter()
        router.add_route("GET", Endpoints.CAMPAIGN, json={"error": "not found"}, status_code=404)
        request = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/abc/campaigns/c1",
        )
        response = router.handle(request)
        assert response.status_code == 404

    def test_override_with_params_matches_specific_id(self):
        """Verify parameterized override only matches the specified path parameter value."""
        router = _FakeRouter()
        router.add_route(
            "GET",
            Endpoints.CAMPAIGN,
            json={"id": "campaign-aaa", "name": "Alpha"},
            params={"campaign_id": "aaa"},
        )

        # When requesting the matching campaign_id
        matched = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/co1/campaigns/aaa",
        )
        response = router.handle(matched)
        body = json.loads(response.content)
        assert body["id"] == "campaign-aaa"

        # When requesting a different campaign_id, the default factory response is used
        other = httpx2.Request(
            "GET",
            "https://fake.test/api/v1/companies/co1/campaigns/bbb",
        )
        response = router.handle(other)
        body = json.loads(response.content)
        assert body["id"] != "campaign-aaa"

    def test_multiple_parameterized_overrides(self):
        """Verify different param values return different responses."""
        router = _FakeRouter()
        router.add_route(
            "GET",
            Endpoints.CAMPAIGN,
            json={"id": "aaa", "name": "Alpha"},
            params={"campaign_id": "aaa"},
        )
        router.add_route(
            "GET",
            Endpoints.CAMPAIGN,
            json={"id": "bbb", "name": "Beta"},
            params={"campaign_id": "bbb"},
        )

        # When requesting campaign aaa
        resp_a = router.handle(
            httpx2.Request("GET", "https://fake.test/api/v1/companies/co1/campaigns/aaa")
        )
        assert json.loads(resp_a.content)["id"] == "aaa"

        # When requesting campaign bbb
        resp_b = router.handle(
            httpx2.Request("GET", "https://fake.test/api/v1/companies/co1/campaigns/bbb")
        )
        assert json.loads(resp_b.content)["id"] == "bbb"

    def test_parameterized_override_beats_generic_override(self):
        """Verify parameterized overrides take priority regardless of insertion order."""
        router = _FakeRouter()

        # Given a generic override added first
        router.add_route(
            "GET",
            Endpoints.CAMPAIGN,
            json={"id": "generic"},
        )
        # Given a parameterized override added second
        router.add_route(
            "GET",
            Endpoints.CAMPAIGN,
            json={"id": "specific"},
            params={"campaign_id": "target"},
        )

        # When requesting the targeted campaign_id
        response = router.handle(
            httpx2.Request("GET", "https://fake.test/api/v1/companies/co1/campaigns/target")
        )
        body = json.loads(response.content)
        assert body["id"] == "specific"

        # When requesting a different campaign_id, the generic override is used
        response = router.handle(
            httpx2.Request("GET", "https://fake.test/api/v1/companies/co1/campaigns/other")
        )
        body = json.loads(response.content)
        assert body["id"] == "generic"
