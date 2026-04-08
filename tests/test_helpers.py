"""Tests for shared test assertion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.testing import CampaignFactory, CharacterFactory, UserFactory

from tests.helpers import (
    assert_has_element,
    assert_has_hx_attr,
    assert_redirects_to,
    assert_shows_error,
    assert_shows_success,
    assert_success,
    build_global_context,
    make_cache_store_mock,
    setup_form_options,
)
from vweb.lib.global_context import GlobalContext

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def make_response() -> Callable[..., MagicMock]:
    """Build a mock response with given status and body."""

    def _factory(status_code: int = 200, body: str = "") -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.get_data.return_value = body
        resp.headers = {}
        return resp

    return _factory


class TestAssertSuccess:
    """Tests for assert_success."""

    def test_passes_on_200(self, make_response):
        resp = make_response(status_code=200)
        assert_success(resp)

    def test_fails_on_non_200(self, make_response):
        resp = make_response(status_code=404)
        with pytest.raises(AssertionError):
            assert_success(resp)


class TestAssertShowsError:
    """Tests for assert_shows_error."""

    def test_passes_when_alert_error_present(self, make_response):
        resp = make_response(body='<div class="alert alert-error">Bad</div>')
        assert_shows_error(resp)

    def test_fails_when_no_alert_error(self, make_response):
        resp = make_response(body="<div>OK</div>")
        with pytest.raises(AssertionError):
            assert_shows_error(resp)


class TestAssertShowsSuccess:
    """Tests for assert_shows_success."""

    def test_passes_when_alert_success_present(self, make_response):
        resp = make_response(body='<div class="alert alert-success">OK</div>')
        assert_shows_success(resp)

    def test_fails_when_no_alert_success(self, make_response):
        resp = make_response(body="<div>OK</div>")
        with pytest.raises(AssertionError):
            assert_shows_success(resp)


class TestAssertRedirectsTo:
    """Tests for assert_redirects_to."""

    def test_passes_on_302_with_matching_location(self, make_response):
        resp = make_response(status_code=302)
        resp.headers["Location"] = "/dashboard"
        assert_redirects_to(resp, "/dashboard")

    def test_fails_on_wrong_status(self, make_response):
        resp = make_response(status_code=200)
        resp.headers["Location"] = "/dashboard"
        with pytest.raises(AssertionError):
            assert_redirects_to(resp, "/dashboard")

    def test_fails_on_wrong_location(self, make_response):
        resp = make_response(status_code=302)
        resp.headers["Location"] = "/other"
        with pytest.raises(AssertionError):
            assert_redirects_to(resp, "/dashboard")


class TestAssertHasElement:
    """Tests for assert_has_element."""

    def test_finds_element_by_id(self, make_response):
        resp = make_response(body='<div id="my-element">content</div>')
        assert_has_element(resp, id="my-element")

    def test_fails_when_id_missing(self, make_response):
        resp = make_response(body="<div>content</div>")
        with pytest.raises(AssertionError):
            assert_has_element(resp, id="my-element")

    def test_finds_element_by_name(self, make_response):
        resp = make_response(body='<input name="username" />')
        assert_has_element(resp, name="username")

    def test_fails_when_name_missing(self, make_response):
        resp = make_response(body='<input name="email" />')
        with pytest.raises(AssertionError):
            assert_has_element(resp, name="username")

    def test_raises_when_no_criteria(self, make_response):
        resp = make_response(body="<div>content</div>")
        with pytest.raises(ValueError, match="at least one"):
            assert_has_element(resp)


class TestAssertHasHxAttr:
    """Tests for assert_has_hx_attr."""

    def test_finds_attr_without_value(self, make_response):
        resp = make_response(body='<div hx-get="/api/data">content</div>')
        assert_has_hx_attr(resp, "hx-get")

    def test_finds_attr_with_value(self, make_response):
        resp = make_response(body='<div hx-get="/api/data">content</div>')
        assert_has_hx_attr(resp, "hx-get", "/api/data")

    def test_fails_when_attr_missing(self, make_response):
        resp = make_response(body="<div>content</div>")
        with pytest.raises(AssertionError):
            assert_has_hx_attr(resp, "hx-get")

    def test_fails_when_value_wrong(self, make_response):
        resp = make_response(body='<div hx-get="/other">content</div>')
        with pytest.raises(AssertionError):
            assert_has_hx_attr(resp, "hx-get", "/api/data")


class TestBuildGlobalContext:
    """Tests for build_global_context."""

    def test_requires_user_role(self):
        with pytest.raises(TypeError):
            build_global_context()

    def test_returns_global_context_with_defaults(self):
        ctx = build_global_context(user_role="PLAYER")
        assert isinstance(ctx, GlobalContext)
        assert ctx.company is not None
        assert len(ctx.users) == 1
        assert len(ctx.campaigns) == 1

    def test_user_has_requested_role(self):
        ctx = build_global_context(user_role="STORYTELLER")
        user = ctx.users[0]
        assert user.role == "STORYTELLER"

    def test_accepts_custom_user(self):
        custom_user = UserFactory.build(name_first="Ada", role="PLAYER")
        ctx = build_global_context(user_role="PLAYER", user=custom_user)
        assert ctx.users[0].name_first == "Ada"

    def test_raises_on_role_mismatch_with_custom_user(self):
        custom_user = UserFactory.build(role="STORYTELLER")
        with pytest.raises(ValueError, match="conflicts"):
            build_global_context(user_role="PLAYER", user=custom_user)

    def test_accepts_custom_campaign(self):
        custom_campaign = CampaignFactory.build(name="My Campaign")
        ctx = build_global_context(user_role="PLAYER", campaign=custom_campaign)
        assert ctx.campaigns[0].name == "My Campaign"

    def test_accepts_characters(self):
        chars = CharacterFactory.batch(2)
        ctx = build_global_context(user_role="PLAYER", characters=chars)
        campaign_id = ctx.campaigns[0].id
        assert ctx.characters_by_campaign[campaign_id] == chars


class TestMakeCacheStoreMock:
    """Tests for make_cache_store_mock."""

    def test_returns_dict_backed_store(self, mocker):
        store = make_cache_store_mock(mocker, "vweb.lib.options_cache.cache")
        assert isinstance(store, dict)

    def test_set_and_get(self, mocker):
        store = make_cache_store_mock(mocker, "vweb.lib.options_cache.cache")
        from vweb.lib.options_cache import cache

        cache.set("key", "value")
        assert store["key"] == "value"
        assert cache.get("key") == "value"

    def test_delete(self, mocker):
        store = make_cache_store_mock(mocker, "vweb.lib.options_cache.cache")
        from vweb.lib.options_cache import cache

        cache.set("key", "value")
        cache.delete("key")
        assert "key" not in store

    def test_clear(self, mocker):
        store = make_cache_store_mock(mocker, "vweb.lib.options_cache.cache")
        from vweb.lib.options_cache import cache

        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert len(store) == 0


class TestSetupFormOptions:
    """Tests for setup_form_options."""

    def test_patches_target_module(self, mocker):
        setup_form_options(mocker, "vweb.routes.character_create.picker_views.fetch_form_options")
        from vweb.routes.character_create.picker_views import fetch_form_options

        result = fetch_form_options()
        assert "character_classes" in result

    def test_accepts_overrides(self, mocker):
        setup_form_options(
            mocker,
            "vweb.routes.character_create.picker_views.fetch_form_options",
            character_classes=["MAGE"],
        )
        from vweb.routes.character_create.picker_views import fetch_form_options

        result = fetch_form_options()
        assert result["character_classes"] == ["MAGE"]
