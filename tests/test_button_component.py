"""Tests for the CommonButton JinjaX component."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from flask import Flask


def _render(app: Flask, **kwargs: object) -> str:
    """Render the Button component and return the HTML output."""
    from vweb import catalog  # type: ignore[attr-defined]

    with app.test_request_context():
        return catalog.render("shared.CommonButton", **kwargs)  # type: ignore[arg-type]


class TestButtonVariants:
    """Test that each variant renders a button element."""

    @pytest.mark.parametrize("variant", ["submit", "cancel", "delete", "edit", "add"])
    def test_variant_renders_button(self, app: Flask, variant: str) -> None:
        """Verify each variant renders a button with a class attribute."""
        # When rendering a Button with the given variant
        html = _render(app, variant=variant, _content="Click")

        # Then the output is a button with classes applied
        assert "<button" in html
        assert 'class="' in html
        assert "Click" in html

    def test_submit_variant_has_submit_type(self, app: Flask) -> None:
        """Verify submit variant defaults to type='submit'."""
        html = _render(app, variant="submit", _content="Save")
        assert 'type="submit"' in html

    @pytest.mark.parametrize("variant", ["cancel", "delete", "edit", "add"])
    def test_non_submit_variants_have_button_type(self, app: Flask, variant: str) -> None:
        """Verify non-submit variants default to type='button'."""
        html = _render(app, variant=variant, _content="Click")
        assert 'type="button"' in html


class TestButtonTypeOverride:
    """Test explicit btn_type prop overrides the variant default."""

    def test_override_submit_type(self, app: Flask) -> None:
        """Verify explicit btn_type overrides the variant default."""
        html = _render(app, variant="cancel", btn_type="submit", _content="Go")
        assert 'type="submit"' in html


class TestButtonHref:
    """Test that href prop renders an <a> tag."""

    def test_href_renders_anchor(self, app: Flask) -> None:
        """Verify href prop produces an <a> element."""
        html = _render(app, variant="edit", href="/edit", _content="Edit")
        assert "<a " in html
        assert 'href="/edit"' in html
        assert "<button" not in html

    def test_href_disabled_renders_aria(self, app: Flask) -> None:
        """Verify disabled <a> gets aria-disabled and btn-disabled."""
        html = _render(app, variant="edit", href="/edit", disabled=True, _content="Edit")
        assert 'aria-disabled="true"' in html
        assert "btn-disabled" in html


class TestButtonExtraClasses:
    """Test the extra_class prop appends extra classes."""

    def test_extra_class_appended(self, app: Flask) -> None:
        """Verify the extra_class prop appends to variant classes."""
        html = _render(app, variant="submit", _content="Save", extra_class="btn-sm")
        assert "btn-sm" in html


class TestButtonDisabled:
    """Test the disabled prop."""

    def test_disabled_button(self, app: Flask) -> None:
        """Verify disabled prop adds disabled attribute to <button>."""
        html = _render(app, variant="submit", disabled=True, _content="Save")
        assert "disabled" in html


class TestButtonContent:
    """Test content slot rendering."""

    def test_icon_content(self, app: Flask) -> None:
        """Verify HTML content (icons) passes through the content slot."""
        html = _render(
            app,
            variant="add",
            _content='<i class="fa-solid fa-plus"></i> Add',
            extra_class="btn-sm",
        )
        assert '<i class="fa-solid fa-plus"></i> Add' in html


class TestButtonAttrsPassThrough:
    """Test that extra HTML attributes pass through via {{ attrs }}."""

    def test_title_passes_through(self, app: Flask) -> None:
        """Verify title attribute passes through to the rendered element."""
        html = _render(app, variant="edit", _content="Edit", _attrs={"title": "Edit item"})
        assert 'title="Edit item"' in html

    def test_data_attributes_pass_through(self, app: Flask) -> None:
        """Verify data-* attributes pass through to the rendered element."""
        html = _render(app, variant="delete", _content="Delete", _attrs={"data-id": "123"})
        assert 'data-id="123"' in html

    def test_attrs_pass_through_on_anchor(self, app: Flask) -> None:
        """Verify attributes pass through on anchor elements too."""
        html = _render(
            app, variant="edit", href="/edit", _content="Edit", _attrs={"title": "Edit item"}
        )
        assert "<a " in html
        assert 'title="Edit item"' in html


class TestButtonEdgeCases:
    """Test edge cases and fallback behavior."""

    def test_invalid_variant_falls_back_to_btn(self, app: Flask) -> None:
        """Verify invalid variant falls back to base 'btn' class."""
        html = _render(app, variant="nonexistent", _content="Click")
        assert 'class="btn"' in html

    def test_href_non_disabled_has_no_aria_disabled(self, app: Flask) -> None:
        """Verify non-disabled anchor does not have aria-disabled or btn-disabled."""
        html = _render(app, variant="edit", href="/edit", _content="Edit")
        assert "aria-disabled" not in html
        assert "btn-disabled" not in html
