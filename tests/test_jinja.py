"""Tests for Jinja helper utilities."""

from __future__ import annotations

from vweb.lib.jinja import build_fragment_url


class TestBuildFragmentUrl:
    """Tests for build_fragment_url(endpoint, **kwargs)."""

    def test_resolves_endpoint_and_appends_query_string(self, app) -> None:
        """Verify the endpoint resolves to a URL and kwargs become a query string."""
        # Given a registered blueprint endpoint
        with app.test_request_context():
            # When building a fragment URL with kwargs
            url = build_fragment_url("static", filename="css/style.css", cache_buster="v1")

        # Then the URL includes the endpoint path and query args
        assert "/static/" in url
        assert "cache_buster=v1" in url

    def test_drops_empty_string_kwargs(self, app) -> None:
        """Verify empty-string values are omitted from the query string."""
        # Given an endpoint and a mix of filled and empty kwargs
        with app.test_request_context():
            # When building a fragment URL
            url = build_fragment_url("static", filename="x.css", empty="", other="y")

        # Then only non-empty values appear in the query string
        assert "empty=" not in url
        assert "other=y" in url

    def test_drops_none_kwargs(self, app) -> None:
        """Verify None values are omitted from the query string."""
        with app.test_request_context():
            # When building a URL with None kwargs
            url = build_fragment_url("static", filename="x.css", maybe=None, keep="v")

        # Then None values are omitted
        assert "maybe=" not in url
        assert "keep=v" in url

    def test_coerces_int_kwargs(self, app) -> None:
        """Verify integer values stringify in the query string."""
        # Given an endpoint and an int kwarg
        with app.test_request_context():
            # When building a URL with an int value
            url = build_fragment_url("static", filename="x.css", limit=50)

        # Then the int appears as a string in the query
        assert "limit=50" in url

    def test_urlencodes_special_characters(self, app) -> None:
        """Verify special characters in values are URL-encoded."""
        # Given an endpoint and a kwarg value with a space
        with app.test_request_context():
            # When building a URL
            url = build_fragment_url("static", filename="x.css", title="Hello World")

        # Then the space is URL-encoded
        assert "title=Hello+World" in url or "title=Hello%20World" in url
