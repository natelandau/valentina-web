"""Tests that keep the route specs the single source of truth for every API route."""

import ast
from pathlib import Path

import pytest

import vweb.api_client.services as services_pkg
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.routes import ResponseStyle, Routes, RouteSpec
from vweb.api_client.services.base import BaseService
from vweb.api_client.testing import FakeVClient
from vweb.api_client.testing._router import _FACTORY_MAP

ALL_ROUTES: dict[str, RouteSpec] = {
    name: value for name, value in vars(Routes).items() if not name.startswith("_")
}
MODEL_STYLES = {ResponseStyle.SINGLE, ResponseStyle.LIST, ResponseStyle.PAGINATED}
ENDPOINT_PATTERNS = {
    value for name, value in vars(Endpoints).items() if name.isupper() and isinstance(value, str)
}
SERVICES_DIR = Path(services_pkg.__file__).parent

# Low-level request helpers that take a raw path, so a service calling them would
# restate a verb or model that a route spec already states.
RAW_REQUEST_HELPERS = {
    "_request",
    "_get",
    "_post",
    "_put",
    "_patch",
    "_delete",
    "_get_paginated",
    "_iter_all_pages",
    "_format_endpoint",
}


@pytest.mark.parametrize(("name", "route"), ALL_ROUTES.items())
def test_route_is_well_formed(name: str, route: RouteSpec) -> None:
    """Verify each route names a known path and carries a model exactly when its style needs one."""
    assert isinstance(route, RouteSpec), name
    assert route.pattern in ENDPOINT_PATTERNS, name
    assert (route.model_class is not None) == (route.style in MODEL_STYLES), name
    if route.style in {ResponseStyle.LIST, ResponseStyle.PAGINATED, ResponseStyle.RAW_JSON}:
        assert route.method == "GET", name


@pytest.mark.parametrize(
    ("name", "route"),
    [(name, route) for name, route in ALL_ROUTES.items() if route.model_class is not None],
)
def test_fake_can_serve_route_model(name: str, route: RouteSpec) -> None:
    """Verify the fake client has a factory for every route model so it can answer by default."""
    assert route.model_class in _FACTORY_MAP, name


def _service_modules() -> list[Path]:
    return sorted(path for path in SERVICES_DIR.glob("*.py") if path.name != "base.py")


@pytest.mark.parametrize("path", _service_modules(), ids=lambda path: path.name)
def test_services_call_routes_only_through_specs(path: Path) -> None:
    """Verify services reach the API only through route specs, never a raw path or verb."""
    tree = ast.parse(path.read_text())

    raw_calls = [
        f"line {node.lineno}: self.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr in RAW_REQUEST_HELPERS
    ]
    endpoint_refs = [
        f"line {node.lineno}: Endpoints"
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "Endpoints"
    ]
    unknown_routes = [
        f"line {node.lineno}: Routes.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Routes"
        and node.attr not in ALL_ROUTES
    ]

    assert raw_calls == []
    assert endpoint_refs == []
    assert unknown_routes == []


def test_helper_rejects_route_of_wrong_style() -> None:
    """Verify a route helper refuses a route whose response it cannot parse."""
    with FakeVClient() as client:
        service = BaseService(client)

        # When reading a paginated route as a single object
        # Then the mismatch is reported instead of sending the request
        with pytest.raises(TypeError, match="returns paginated, not single"):
            service._call(Routes.COMPANIES_LIST)
