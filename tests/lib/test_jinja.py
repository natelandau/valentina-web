"""Tests for Jinja helper utilities."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from flask import flash, g

import vweb
from vweb.api_client.testing import CampaignBookFactory, CampaignFactory, CharacterFactory
from vweb.lib.jinja import (
    build_fragment_url,
    character_born_label,
    dice_notation,
    threat_badge_class,
)


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


def test_flash_message_markup_not_escaped(app) -> None:
    """Verify the flash toast's own markup is not autoescaped into visible text."""
    # Given a flashed message in a request context
    with app.test_request_context():
        flash("Saved!", "success")

        # When the flash container renders
        html = vweb.catalog.render("shared.layout.FlashMessage")

    # Then no escaped markup leaks into the page
    assert "Saved!" in html
    assert "&lt;" not in html


@pytest.mark.parametrize(
    ("kwargs", "present", "absent"),
    [
        ({"cache_buster": "v1"}, ["/static/", "cache_buster=v1"], []),
        ({"empty": "", "other": "y"}, ["other=y"], ["empty="]),
        ({"maybe": None, "keep": "v"}, ["keep=v"], ["maybe="]),
        ({"limit": 50}, ["limit=50"], []),
        ({"title": "Hello World"}, ["title=Hello+World"], []),
    ],
)
def test_build_fragment_url(app, kwargs, present, absent) -> None:
    """Verify kwargs become an encoded query string, dropping empty and None values."""
    with app.test_request_context():
        url = build_fragment_url("static", filename="x.css", **kwargs)

    for fragment in present:
        assert fragment in url
    for fragment in absent:
        assert fragment not in url


def test_threat_badge_class_thresholds() -> None:
    """Verify danger levels group into three severity bands at 2 and 4."""
    # Compare bands, not class names, so the colors can change freely
    bands = [threat_badge_class(level) for level in range(6)]

    assert bands[0] == bands[1]
    assert bands[2] == bands[3]
    assert bands[4] == bands[5]
    assert len({bands[0], bands[2], bands[4]}) == 3


@pytest.mark.parametrize(
    ("modifier", "expected"),
    [(0, "5d10"), (1, "5d10 +1"), (-2, "5d10 -2")],
)
def test_dice_notation(modifier, expected) -> None:
    """Verify the modifier is appended with its sign only when non-zero."""
    assert dice_notation(num_dice=5, dice_size=10, dice_modifier=modifier) == expected


@pytest.mark.parametrize(
    ("in_game_date", "date_of_birth", "age", "status", "expected"),
    [
        (date(1990, 6, 1), date(1960, 3, 15), 30, "ALIVE", "15 Mar 1960"),
        (date(1990, 6, 1), None, 23, "ALIVE", "c. 1967"),
        (date(1990, 6, 1), None, 2000, "ALIVE", "c. 11 BCE"),
        (date(1990, 6, 1), None, 1990, "ALIVE", "c. 1 BCE"),
        (date(1990, 6, 1), None, 23, "DEAD", None),
        (date(1990, 6, 1), None, None, "ALIVE", None),
        (None, date(1960, 3, 15), 30, "ALIVE", None),
    ],
)
def test_character_born_label(app, in_game_date, date_of_birth, age, status, expected) -> None:
    """Verify the Born row: a date of birth as recorded, an estimate from age, nothing undated."""
    # Given a character in a campaign with the in-game date under test
    campaign = CampaignFactory.build(id="camp-1", in_game_date=in_game_date)
    character = CharacterFactory.build(
        campaign_id="camp-1", date_of_birth=date_of_birth, age=age, status=status
    )

    # When building the label in a request whose context holds that campaign
    with app.test_request_context():
        g.global_context = SimpleNamespace(campaigns=[campaign])
        label = character_born_label(character)

    # Then it matches the rules for the Born row
    assert label == expected
