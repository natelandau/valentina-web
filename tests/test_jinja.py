"""Tests for Jinja helper utilities."""

from __future__ import annotations

from flask import flash
from vclient.testing import CampaignBookFactory, CampaignFactory

import vweb
from vweb.lib.jinja import build_fragment_url


class TestCatalogAutoescape:
    """Tests for HTML autoescaping in the JinjaX catalog environment."""

    def test_catalog_autoescape_enabled(self) -> None:
        """Verify the JinjaX catalog environment has autoescaping unconditionally enabled."""
        # Assert `is True` rather than truthiness: a select_autoescape callable would
        # also be truthy while disabling escaping for .jinja files.
        assert vweb.catalog.jinja_env.autoescape is True

    def test_component_escapes_malicious_prop(self, app) -> None:
        """Verify user-controlled fields are escaped when rendered by a component."""
        # Given a book whose name contains an XSS payload
        campaign = CampaignFactory.build(id="camp-1")
        book = CampaignBookFactory.build(
            id="book-1",
            name='"><script>alert(1)</script>',
            number=1,
            description="A description",
        )

        # When the edit form renders the book
        with app.test_request_context():
            html = vweb.catalog.render("book.partials.BookEditForm", book=book, campaign=campaign)

        # Then the payload is escaped, not reflected raw
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestFlashMessageIcons:
    """Tests for flash toast icon rendering under autoescaping."""

    def test_flash_icon_renders_svg(self, app) -> None:
        """Verify flash toast icons render as real SVG markup, not escaped text."""
        # Given a flashed message in a request context
        with app.test_request_context():
            flash("Saved!", "success")

            # When the flash container renders
            html = vweb.catalog.render("shared.layout.FlashMessage")

        # Then the icon markup survives autoescaping
        assert "<svg" in html
        assert "&lt;svg" not in html


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
