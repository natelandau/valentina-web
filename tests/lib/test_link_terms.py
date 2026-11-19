"""Tests for the link_terms Jinja filter."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import TYPE_CHECKING

import pytest
from flask import url_for
from markupsafe import Markup

from vweb.api_client.testing import DictionaryTermFactory
from vweb.lib.jinja_filters import from_markdown, link_terms

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from vweb.api_client.models import DictionaryTerm


@pytest.fixture
def _mock_terms(mocker) -> MagicMock:
    """Patch dictionary terms to return an empty list by default."""
    return mocker.patch("vweb.lib.cache.dictionary.terms", return_value=[])


@pytest.fixture
def set_terms(_mock_terms) -> Callable:
    """Return a callable that sets the mocked term list."""

    def _set(terms: list) -> None:
        _mock_terms.return_value = terms

    return _set


class _AnchorCollector(HTMLParser):
    """Collect each anchor as a browser parser sees it: its attributes and its text."""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[list[tuple[str, str | None]], str]] = []
        self._open = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.anchors.append((attrs, ""))
            self._open = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._open = False

    def handle_data(self, data: str) -> None:
        if self._open:
            attrs, text = self.anchors[-1]
            self.anchors[-1] = (attrs, text + data)


def _anchors(html: str) -> list[tuple[list[tuple[str, str | None]], str]]:
    collector = _AnchorCollector()
    collector.feed(str(html))
    return collector.anchors


def _links(html: str) -> list[tuple[str | None, str]]:
    """Return (href, text) for every anchor in the html."""
    return [(dict(attrs).get("href"), text) for attrs, text in _anchors(html)]


def _detail(term: DictionaryTerm) -> str:
    return url_for("dictionary.term_detail", term_id=term.id)


_CELERITY = DictionaryTermFactory.build(id="t-cel", term="Celerity", definition="Speed.")
_AUSPEX = DictionaryTermFactory.build(id="t-aus", term="Auspex", definition="Senses.")
_BLOOD = DictionaryTermFactory.build(id="t-blood", term="Blood", definition="Vital fluid.")
_FORTITUDE = DictionaryTermFactory.build(
    id="t-fort", term="Fortitude", definition="Resilience.", synonyms=["Toughness"]
)
_CAMARILLA = DictionaryTermFactory.build(
    term="Camarilla", definition=None, link="https://example.com/camarilla"
)
_SABBAT = DictionaryTermFactory.build(
    id="t-sab", term="Sabbat", definition="A sect.", link="https://example.com/sabbat"
)
_ART = DictionaryTermFactory.build(term="Art", definition="A creative skill.")
_GANGREL = DictionaryTermFactory.build(term="Gangrel", definition=None, link=None)
_SCRIPT_LINK = DictionaryTermFactory.build(
    term="Camarilla", definition=None, link="javascript:alert(1)"
)


@pytest.mark.parametrize(
    ("terms", "text", "expected"),
    [
        pytest.param([_CELERITY], "Used Celerity.", [(_CELERITY, "Celerity")], id="definition"),
        pytest.param([_AUSPEX], "She used auspex.", [(_AUSPEX, "auspex")], id="case-insensitive"),
        pytest.param(
            [_BLOOD], "Blood is thick. More Blood.", [(_BLOOD, "Blood")] * 2, id="every-occurrence"
        ),
        pytest.param([_FORTITUDE], "Her Toughness.", [(_FORTITUDE, "Toughness")], id="synonym"),
        pytest.param(
            [_CAMARILLA],
            "The Camarilla rules.",
            [("https://example.com/camarilla", "Camarilla")],
            id="external-link",
        ),
        pytest.param([_SABBAT], "The Sabbat came.", [(_SABBAT, "Sabbat")], id="definition-wins"),
        pytest.param([_ART], "The artifact was old.", [], id="whole-word-only"),
        pytest.param([_GANGREL], "The Gangrel howled.", [], id="no-definition-or-link"),
        pytest.param([_SCRIPT_LINK], "The Camarilla rules.", [], id="non-http-link"),
        pytest.param([], "Some random text", [], id="no-terms"),
    ],
)
def test_html_links(app, set_terms, terms, text, expected) -> None:
    """Verify which words become links and where each link points."""
    set_terms(terms)

    with app.test_request_context():
        result = link_terms(text, "html")
        expected_links = [
            (target if isinstance(target, str) else _detail(target), word)
            for target, word in expected
        ]

    assert _links(result) == expected_links
    if not expected:
        assert str(result) == text


def test_excludes_specified_terms(app, set_terms) -> None:
    """Verify excluded terms are not linked."""
    brujah = DictionaryTermFactory.build(term="Brujah", definition="A clan.")
    ventrue = DictionaryTermFactory.build(term="Ventrue", definition="Another clan.")
    set_terms([brujah, ventrue])

    with app.test_request_context():
        result = link_terms("Brujah vs Ventrue", "html", excludes=["Brujah"])

    assert [text for _, text in _links(result)] == ["Ventrue"]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        pytest.param(
            DictionaryTermFactory.build(
                term="Elysium", definition=None, link="https://example.com/elysium"
            ),
            "[Elysium](https://example.com/elysium)",
            id="external-link",
        ),
        pytest.param(
            DictionaryTermFactory.build(id="term-1", term="Elysium", definition="Neutral ground."),
            "[Elysium](/dictionary/term/term-1)",
            id="definition",
        ),
    ],
)
def test_markdown_links(app, set_terms, term, expected) -> None:
    """Verify markdown mode wraps terms in markdown link syntax."""
    set_terms([term])

    with app.test_request_context():
        result = link_terms("Meet at the Elysium.", "markdown")

    assert expected in result


class TestHtmlSafety:
    """link_terms output is rendered unescaped, so it must never carry injected markup."""

    def test_escapes_plain_input(self, app, set_terms) -> None:
        """Verify raw HTML in plain-string input is escaped before links are added."""
        set_terms([_CELERITY])

        with app.test_request_context():
            result = link_terms("<img src=x onerror=alert(1)> Celerity", "html")

        # Markup so the generated anchors survive autoescaping
        assert isinstance(result, Markup)
        assert "<img" not in result
        assert "&lt;img" in result
        assert len(_links(result)) == 1

    def test_preserves_markup_input(self, app, set_terms) -> None:
        """Verify already-safe Markup input (e.g. from from_markdown) is not re-escaped."""
        set_terms([_CELERITY])

        with app.test_request_context():
            result = link_terms(from_markdown("**bold** Celerity"), "html")

        assert "<strong>bold</strong>" in result
        assert len(_links(result)) == 1

    def test_escapes_external_link_url(self, app, set_terms) -> None:
        """Verify quotes in an external term link cannot break out of the href attribute."""
        term = DictionaryTermFactory.build(
            term="Camarilla",
            definition=None,
            link="https://example.com/x' onmouseover='alert(1)",
        )
        set_terms([term])

        with app.test_request_context():
            result = link_terms("The Camarilla rules.", "html")

        assert "x' onmouseover=" not in result

    def test_synonym_inside_own_link_cannot_add_attributes(self, app, set_terms) -> None:
        """Verify a synonym that appears in the term's own link is not re-linked inside the href."""
        # Given a link-only term whose link contains its own synonym followed by attribute text
        term = DictionaryTermFactory.build(
            term="Aaaa",
            synonyms=["Qqqq"],
            definition=None,
            link="https://a.example/?a,Qqqq,/x-data/x-init=alert(1)//",
        )
        set_terms([term])

        with app.test_request_context():
            result = link_terms("See Aaaa here.", "html")

        # Then the browser sees one anchor with no injected attributes
        anchors = _anchors(result)
        assert len(anchors) == 1
        assert {name for name, _ in anchors[0][0]} <= {"href", "class"}

    def test_text_inside_existing_anchor_is_not_relinked(self, app, set_terms) -> None:
        """Verify terms are only linked in text outside existing anchors."""
        set_terms([_CELERITY])

        with app.test_request_context():
            result = link_terms(Markup('<a href="/x">Celerity</a> and Celerity'), "html")

        assert len(_anchors(result)) == 2

    def test_term_matching_entity_text_leaves_entity_intact(self, app, set_terms) -> None:
        """Verify a term spelled like an HTML entity name is not linked inside the entity."""
        set_terms([DictionaryTermFactory.build(term="amp", definition="Amplify.")])

        with app.test_request_context():
            result = link_terms("R&D", "html")

        assert str(result) == "R&amp;D"
