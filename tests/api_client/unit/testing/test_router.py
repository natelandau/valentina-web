"""Tests for the _FakeRouter."""

import json
import re
from collections.abc import Callable

import httpx2
import pytest

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.routes import Routes, RouteSpec
from vweb.api_client.testing._router import _FakeRouter

BASE = "https://fake.test"


def _url(pattern: str, **params: str) -> str:
    """Fill a route pattern's path parameters, defaulting each to ``<name>-1``."""
    path = re.sub(r"\{([^}]+)\}", lambda m: params.get(m[1], f"{m[1]}-1"), pattern)
    return f"{BASE}{path}"


def _handle(router: _FakeRouter, method: str, pattern: str, **params: str) -> httpx2.Response:
    return router.handle(httpx2.Request(method, _url(pattern, **params)))


@pytest.mark.parametrize(
    ("route", "status", "check_body"),
    [
        pytest.param(
            Routes.CAMPAIGNS_GET,
            200,
            lambda body: "id" in body and "items" not in body,
            id="single",
        ),
        pytest.param(
            Routes.CAMPAIGNS_LIST,
            200,
            lambda body: len(body["items"]) == body["total"] == 1,
            id="paginated",
        ),
        pytest.param(
            Routes.USERS_LOOKUP,
            200,
            lambda body: isinstance(body, list) and len(body) == 1,
            id="list",
        ),
        pytest.param(Routes.OPTIONS_GET, 200, lambda body: body == {}, id="raw-json"),
        pytest.param(Routes.CAMPAIGNS_DELETE, 204, None, id="no-content"),
    ],
)
def test_default_response_matches_route_style(
    route: RouteSpec, status: int, check_body: Callable[[object], bool] | None
) -> None:
    """Verify each route answers by default in the envelope its response style calls for."""
    response = _handle(_FakeRouter(), route.method, route.pattern)

    assert response.status_code == status
    if check_body is None:
        assert response.content == b""
    else:
        assert check_body(json.loads(response.content))


def test_unmatched_route_returns_404() -> None:
    """Verify a path that names no API route gets a 404."""
    response = _FakeRouter().handle(httpx2.Request("GET", f"{BASE}/api/v1/nonexistent"))

    assert response.status_code == 404


class TestFakeRouterOverrides:
    """Router should support user-defined route overrides."""

    def test_override_replaces_default(self) -> None:
        """Verify an override answers in place of the default, with its own status and body."""
        router = _FakeRouter()
        router.add_route("GET", Endpoints.CAMPAIGN, json={"error": "gone"}, status_code=404)

        response = _handle(router, "GET", Endpoints.CAMPAIGN)

        assert response.status_code == 404
        assert json.loads(response.content) == {"error": "gone"}

    def test_override_without_body_sends_empty_response(self) -> None:
        """Verify an override with no JSON sends an empty body."""
        router = _FakeRouter()
        router.add_route("GET", Endpoints.CAMPAIGN, json=None, status_code=204)

        response = _handle(router, "GET", Endpoints.CAMPAIGN)

        assert response.status_code == 204
        assert response.content == b""

    def test_parameterized_overrides_match_only_their_ids(self) -> None:
        """Verify overrides pinned to path values answer only those values."""
        router = _FakeRouter()
        for campaign_id in ("aaa", "bbb"):
            router.add_route(
                "GET",
                Endpoints.CAMPAIGN,
                json={"id": campaign_id},
                params={"campaign_id": campaign_id},
            )

        def body_for(campaign_id: str) -> dict:
            response = _handle(router, "GET", Endpoints.CAMPAIGN, campaign_id=campaign_id)
            return json.loads(response.content)

        assert body_for("aaa")["id"] == "aaa"
        assert body_for("bbb")["id"] == "bbb"
        assert body_for("ccc")["id"] not in {"aaa", "bbb"}

    def test_parameterized_override_beats_generic_override(self) -> None:
        """Verify a pinned override wins over a generic one regardless of insertion order."""
        router = _FakeRouter()
        router.add_route("GET", Endpoints.CAMPAIGN, json={"id": "generic"})
        router.add_route(
            "GET", Endpoints.CAMPAIGN, json={"id": "specific"}, params={"campaign_id": "target"}
        )

        target = _handle(router, "GET", Endpoints.CAMPAIGN, campaign_id="target")
        other = _handle(router, "GET", Endpoints.CAMPAIGN, campaign_id="other")

        assert json.loads(target.content)["id"] == "specific"
        assert json.loads(other.content)["id"] == "generic"


class TestFakeRouterPathHandling:
    """Router should honor custom methods, ad-hoc patterns, and encoded path values."""

    def test_add_route_with_unlisted_method_on_known_pattern(self) -> None:
        """Verify an override answers a method that no default route has for its pattern."""
        router = _FakeRouter()
        router.add_route("PUT", Endpoints.CAMPAIGN, json={"id": "put"})

        response = _handle(router, "PUT", Endpoints.CAMPAIGN)

        assert response.status_code == 200
        assert json.loads(response.content) == {"id": "put"}

    def test_ad_hoc_override_answers_only_its_own_path(self) -> None:
        """Verify an override on an unlisted pattern answers that path and no other."""
        router = _FakeRouter()
        router.add_route("GET", "/api/v1/experimental/{thing_id}", json={"ok": True})

        matched = router.handle(httpx2.Request("GET", f"{BASE}/api/v1/experimental/t1"))
        other = router.handle(httpx2.Request("GET", f"{BASE}/api/v1/nonexistent"))

        assert json.loads(matched.content) == {"ok": True}
        assert other.status_code == 404

    def test_encoded_slash_in_path_value_stays_one_segment(self) -> None:
        """Verify a percent-encoded slash in an id resolves the route and decodes the value."""
        router = _FakeRouter()

        response = _handle(router, "GET", Endpoints.CAMPAIGN, campaign_id="a%2Fb")

        assert response.status_code == 200
        (recorded,) = router.requests
        assert recorded.route is not None
        assert recorded.params["campaign_id"] == "a/b"
