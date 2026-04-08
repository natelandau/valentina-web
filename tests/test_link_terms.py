"""Tests for the link_terms Jinja filter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import DictionaryTermFactory

from vweb.lib.jinja import link_terms

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock


@pytest.fixture
def _mock_terms(mocker) -> MagicMock:
    """Patch get_all_terms to return an empty list by default."""
    return mocker.patch("vweb.lib.jinja.get_all_terms", return_value=[])


@pytest.fixture
def set_terms(_mock_terms) -> Callable:
    """Return a callable that sets the mocked term list."""

    def _set(terms: list) -> None:
        _mock_terms.return_value = terms

    return _set


@pytest.mark.usefixtures("_mock_terms")
class TestLinkTermsNoTerms:
    """Tests for link_terms when no dictionary terms exist."""

    def test_returns_text_unchanged(self, app) -> None:
        """Verify text passes through unmodified when there are no terms."""
        with app.test_request_context():
            result = link_terms("Some random text", "html")

        assert result == "Some random text"


class TestLinkTermsDefinitionHtml:
    """Tests for HTML link generation for terms with definitions."""

    def test_wraps_matching_term(self, app, set_terms) -> None:
        """Verify a term with a definition is wrapped in an HTML link."""
        # Given a term with a definition
        term = DictionaryTermFactory.build(term="Celerity", definition="A vampire discipline.")
        set_terms([term])

        # When the filter processes text containing the term
        with app.test_request_context():
            result = link_terms("The vampire used Celerity to escape.", "html")

        # Then the term is wrapped in an anchor tag
        assert f">{term.term}<" not in result or "<a href=" in result
        assert "link link-primary link-hover" in result
        assert "Celerity" in result

    def test_case_insensitive_match(self, app, set_terms) -> None:
        """Verify matching is case-insensitive while preserving original casing."""
        # Given a term
        term = DictionaryTermFactory.build(term="Auspex", definition="Heightened senses.")
        set_terms([term])

        # When text contains the term in different casing
        with app.test_request_context():
            result = link_terms("She activated auspex.", "html")

        # Then the match preserves the original casing
        assert ">auspex<" in result
        assert "<a href=" in result

    def test_whole_word_only(self, app, set_terms) -> None:
        """Verify terms are matched as whole words, not substrings."""
        # Given a short term
        term = DictionaryTermFactory.build(term="Art", definition="A creative skill.")
        set_terms([term])

        # When text contains the term as a substring of another word
        with app.test_request_context():
            result = link_terms("The artifact was old.", "html")

        # Then the substring is not linked
        assert "<a href=" not in result

    def test_multiple_occurrences(self, app, set_terms) -> None:
        """Verify all occurrences of a term are linked."""
        # Given a term
        term = DictionaryTermFactory.build(term="Blood", definition="Vital fluid.")
        set_terms([term])

        # When text contains the term twice
        with app.test_request_context():
            result = link_terms("Blood is thicker. More Blood.", "html")

        # Then both occurrences are linked
        assert result.count("<a href=") == 2


class TestLinkTermsSynonyms:
    """Tests for synonym matching."""

    def test_matches_synonym(self, app, set_terms) -> None:
        """Verify synonyms are also linked to the term's definition page."""
        # Given a term with a synonym
        term = DictionaryTermFactory.build(
            term="Fortitude", definition="Resilience.", synonyms=["Toughness"]
        )
        set_terms([term])

        # When text contains the synonym
        with app.test_request_context():
            result = link_terms("Her Toughness was legendary.", "html")

        # Then the synonym is linked
        assert "<a href=" in result
        assert ">Toughness<" in result


class TestLinkTermsExternalLink:
    """Tests for terms with external links (no definition)."""

    def test_wraps_with_external_link(self, app, set_terms) -> None:
        """Verify a term with only a link uses the external URL."""
        # Given a term with a link but no definition
        term = DictionaryTermFactory.build(
            term="Camarilla", definition=None, link="https://example.com/camarilla"
        )
        set_terms([term])

        # When the filter processes matching text
        with app.test_request_context():
            result = link_terms("The Camarilla rules the city.", "html")

        # Then the external link is used
        assert "href='https://example.com/camarilla'" in result
        assert "link link-primary" in result

    def test_definition_takes_priority_over_link(self, app, set_terms) -> None:
        """Verify that when a term has both definition and link, definition wins."""
        # Given a term with both definition and link
        term = DictionaryTermFactory.build(
            id="term-123",
            term="Sabbat",
            definition="A vampire sect.",
            link="https://example.com/sabbat",
        )
        set_terms([term])

        # When the filter processes matching text
        with app.test_request_context():
            result = link_terms("The Sabbat attacked.", "html")

        # Then the internal definition link is used, not the external link
        assert "term-123" in result
        assert "https://example.com/sabbat" not in result


class TestLinkTermsExcludes:
    """Tests for the excludes parameter."""

    def test_excludes_specified_terms(self, app, set_terms) -> None:
        """Verify excluded terms are not linked."""
        # Given two terms
        term1 = DictionaryTermFactory.build(term="Brujah", definition="A clan.")
        term2 = DictionaryTermFactory.build(term="Ventrue", definition="Another clan.")
        set_terms([term1, term2])

        # When one term is excluded
        with app.test_request_context():
            result = link_terms("Brujah vs Ventrue", "html", excludes=["Brujah"])

        # Then only the non-excluded term is linked
        assert result.count("<a href=") == 1
        assert ">Ventrue<" in result


class TestLinkTermsNoMatch:
    """Tests for text that contains no matching terms."""

    def test_no_definition_no_link(self, app, set_terms) -> None:
        """Verify terms without definition or link are not wrapped."""
        # Given a term with neither definition nor link
        term = DictionaryTermFactory.build(term="Gangrel", definition=None, link=None)
        set_terms([term])

        # When the filter processes text containing the term
        with app.test_request_context():
            result = link_terms("The Gangrel howled.", "html")

        # Then no link is added
        assert "<a href=" not in result
        assert result == "The Gangrel howled."


class TestLinkTermsMarkdown:
    """Tests for markdown link generation."""

    def test_wraps_with_markdown_link(self, app, set_terms) -> None:
        """Verify markdown mode wraps terms with external links in markdown syntax."""
        # Given a term with an external link but no definition
        term = DictionaryTermFactory.build(
            term="Elysium", definition=None, link="https://example.com/elysium"
        )
        set_terms([term])

        # When using markdown mode
        with app.test_request_context():
            result = link_terms("Meet at the Elysium.", "markdown")

        # Then the term is wrapped in markdown link syntax
        assert "[Elysium](https://example.com/elysium)" in result
