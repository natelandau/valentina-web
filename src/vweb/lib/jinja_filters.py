"""Jinja2 filters for the vweb application."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import humanize
from flask import url_for
from markdown2 import markdown
from markupsafe import Markup, escape

from vweb.lib import cache

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm


def from_markdown(value: str) -> Markup:
    """Convert a Markdown string to HTML.

    Escape the provided Markdown string to prevent HTML injection,
    then convert the escaped Markdown content to HTML.

    Args:
        value (str): The Markdown string to be converted.

    Returns:
        Safe HTML markup from the converted Markdown.
    """
    value = escape(value)
    return Markup(markdown(value).strip())  # noqa: S704


def from_markdown_no_p(value: str) -> Markup:
    """Strip enclosing paragraph marks, <p> ... </p>, which markdown() forces, and which interfere with some jinja2 layout."""
    value = escape(value)
    return Markup(re.sub("(^<P>|</P>$)", "", markdown(value), flags=re.IGNORECASE).strip())  # noqa: S704


def format_date(value: str | datetime) -> str:
    """Format a datetime or datetime string to YYYY-MM-DD.

    Args:
        value: A datetime object or ISO-format datetime string.

    Returns:
        str: The date in YYYY-MM-DD format.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    return value.strftime("%Y-%m-%d")


def humanize_date(value: str | datetime) -> str:
    """Format a datetime as a human-friendly relative time string (e.g. "3 years ago").

    Args:
        value: A datetime object or ISO-format datetime string.

    Returns:
        str: A human-readable relative time string.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    return humanize.naturaltime(value)


_ROMAN_NUMERALS: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def to_roman(value: int) -> str:
    """Render an integer as its Roman-numeral representation.

    Return an empty string for non-positive inputs (Roman numerals have no
    concept of zero or negatives).

    Args:
        value: The integer to convert.

    Returns:
        The Roman numeral string, or an empty string for value <= 0.
    """
    if value <= 0:
        return ""
    parts: list[str] = []
    remaining = value
    for amount, symbol in _ROMAN_NUMERALS:
        while remaining >= amount:
            parts.append(symbol)
            remaining -= amount
    return "".join(parts)


def normalize_string(value: str) -> str:
    """Normalize a string by removing quotes and whitespace.

    Args:
        value: The string to normalize.

    Returns:
        The normalized string.
    """
    return value.replace("'", "").replace('"', "").strip()


def _link_term_in_text(
    value: str,
    term: DictionaryTerm,
    link_type: Literal["markdown", "html"],
) -> str:
    """Wrap whole-word occurrences of a term and its synonyms in links.

    Args:
        value: The text to process.
        term: The dictionary term whose name and synonyms are matched.
        link_type: Whether to insert HTML anchors or markdown links.

    Returns:
        str: The text with this term's occurrences converted to links.
    """
    patterns = [
        re.compile(rf"\b(?<![\w/]){re.escape(name)}\b(?![\w/]|://)", re.IGNORECASE)
        for name in [term.term, *term.synonyms]
    ]

    # Escape the externally sourced URL once so quotes cannot break out of href.
    escaped_link = escape(term.link) if term.link else ""

    for pattern in patterns:
        if term.definition:
            if link_type == "html":
                value = pattern.sub(
                    lambda m: (
                        f"<a href='{url_for('dictionary.term_detail', term_id=term.id)}' class='link link-primary link-hover'>{m.group(0)}</a>"
                    ),
                    value,
                )
            else:
                value = pattern.sub(
                    lambda m: f"[{m.group(0)}]({url_for('dictionary.term', term=term.term)})",
                    value,
                )
        elif term.link:
            if link_type == "html":
                value = pattern.sub(
                    lambda m: (
                        f"<a href='{escaped_link}' class='link link-primary'>{m.group(0)}</a>"
                    ),
                    value,
                )
            else:
                value = pattern.sub(lambda m: f"[{m.group(0)}]({term.link})", value)

    return value


def link_terms(
    value: str,
    link_type: Literal["markdown", "html"],
    excludes: list[str] | None = None,
) -> str | Markup:
    """Convert dictionary terms in text to markdown or HTML links.

    Search through text for terms and synonyms that exist in the DictionaryTerm collection and convert them to links pointing to their dictionary entries in the web UI. The search is case-insensitive and only matches whole words.

    Args:
        value (str): The text to process.
        link_type (Literal["markdown", "html"]): Whether to return HTML links instead of markdown links.
        excludes: Terms to exclude from the search.

    Returns:
        str | Markup: The text with dictionary terms converted to links. HTML mode
            returns Markup so the generated anchors survive autoescaping.
    """
    if excludes is None:
        excludes = []

    if link_type == "html":
        # Escape unsafe input up front (a no-op for Markup from from_markdown) so
        # the result can be marked safe after the anchor tags are inserted.
        value = escape(value)

    excluded_terms = {x.lower() for x in excludes}
    for term in cache.dictionary.terms():
        if term.term.lower() in excluded_terms:
            continue

        value = _link_term_in_text(value, term, link_type)

    if link_type == "html":
        return Markup(value)  # noqa: S704

    return value
