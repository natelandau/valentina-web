"""Tests for the CommonButton JinjaX component."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from flask import Flask


def _render(app: Flask, **kwargs: Any) -> str:
    """Render the Button component and return the HTML output."""
    from vweb.lib.catalog import catalog

    with app.test_request_context():
        return catalog.render("shared.CommonButton", **kwargs)


@pytest.mark.parametrize(
    ("variant", "btn_type", "expected_type"),
    [
        ("submit", "", "submit"),
        ("cancel", "", "button"),
        ("delete", "", "button"),
        ("edit", "", "button"),
        ("add", "", "button"),
        ("cancel", "submit", "submit"),
    ],
)
def test_button_type(app: Flask, variant: str, btn_type: str, expected_type: str) -> None:
    """Verify only submit buttons submit a form unless btn_type overrides the variant."""
    html = _render(app, variant=variant, btn_type=btn_type, _content="Click")

    assert f'type="{expected_type}"' in html


@pytest.mark.parametrize("disabled", [True, False])
def test_disabled_button(app: Flask, *, disabled: bool) -> None:
    """Verify the disabled prop sets the disabled attribute on a button."""
    html = _render(app, variant="submit", disabled=disabled, _content="Save")

    assert bool(re.search(r"\sdisabled[\s>]", html)) is disabled


@pytest.mark.parametrize("disabled", [True, False])
def test_href_renders_anchor(app: Flask, *, disabled: bool) -> None:
    """Verify href renders a link, marked aria-disabled only when disabled."""
    html = _render(app, variant="edit", href="/edit", disabled=disabled, _content="Edit")

    assert 'href="/edit"' in html
    assert "<button" not in html
    assert ('aria-disabled="true"' in html) is disabled


@pytest.mark.parametrize("href", ["", "/edit"])
def test_attrs_pass_through(app: Flask, href: str) -> None:
    """Verify extra HTML attributes reach both button and anchor elements."""
    html = _render(
        app,
        variant="edit",
        href=href,
        _content="Edit",
        _attrs={"title": "Edit item", "data-id": "123"},
    )

    assert 'title="Edit item"' in html
    assert 'data-id="123"' in html


def test_extra_attrs_quotes_not_escaped(app: Flask) -> None:
    """Verify extra_attrs renders with intact quotes (not entity-escaped) under autoescape."""
    # Given a raw HTMX attribute string with quoted values
    attrs = 'hx-get="/profile/u1/edit" hx-target="#form" hx-swap="innerHTML"'

    # When rendering a button with that extra_attrs prop
    html = _render(app, variant="edit", _content="Edit", extra_attrs=attrs)

    # Then the attribute quotes survive autoescaping
    assert 'hx-get="/profile/u1/edit"' in html
    assert "&#34;" not in html
