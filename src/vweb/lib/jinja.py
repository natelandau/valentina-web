"""Jinja configuration for the vweb application."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import humanize
import jinjax
from flask import g, url_for
from markdown2 import markdown
from markupsafe import Markup, escape

import vweb
from vweb.config import get_settings
from vweb.constants import STATIC_PATH, TEMPLATES_PATH
from vweb.routes.dictionary.cache import get_all_terms

if TYPE_CHECKING:
    from vclient.models.users import CampaignExperience


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


def normalize_string(value: str) -> str:
    """Normalize a string by removing quotes and whitespace.

    Args:
        value: The string to normalize.

    Returns:
        The normalized string.
    """
    return value.replace("'", "").replace('"', "").strip()


def user_campaign_experience(user_id: str, campaign_id: str) -> CampaignExperience | None:
    """Look up a user's experience for a specific campaign.

    Args:
        user_id: The user's unique identifier.
        campaign_id: The campaign's unique identifier.

    Returns:
        The CampaignExperience object if found, None otherwise.
    """
    user = next((u for u in g.global_context.users if u.id == user_id), None)
    if user is None:
        return None
    return next(
        (exp for exp in user.campaign_experience if exp.campaign_id == campaign_id),
        None,
    )


def link_terms(
    value: str,
    link_type: Literal["markdown", "html"],
    excludes: list[str] | None = None,
) -> str:
    """Convert dictionary terms in text to markdown or HTML links.

    Search through text for terms and synonyms that exist in the DictionaryTerm collection and convert them to links pointing to their dictionary entries in the web UI. The search is case-insensitive and only matches whole words.

    Args:
        value (str): The text to process.
        link_type (Literal["markdown", "html"]): Whether to return HTML links instead of markdown links.
        excludes: Terms to exclude from the search.

    Returns:
        str: The text with dictionary terms converted to links.
    """
    if excludes is None:
        excludes = []

    for term in get_all_terms():
        if term.term.lower() in [x.lower() for x in excludes]:
            continue

        patterns = [
            re.compile(rf"\b(?<![\w/]){re.escape(name)}\b(?![\w/]|://)", re.IGNORECASE)
            for name in [term.term, *term.synonyms]
        ]

        for pattern in patterns:
            if term.definition:
                if link_type == "html":
                    value = pattern.sub(
                        lambda m: (
                            f"<a href='{url_for('dictionary.term_detail', term_id=term.id)}' class='link link-primary link-hover'>{m.group(0)}</a>"  # noqa: B023
                        ),
                        value,
                    )
                else:
                    value = pattern.sub(
                        lambda m: f"[{m.group(0)}]({url_for('dictionary.term', term=term.term)})",  # noqa: B023
                        value,
                    )
            elif term.link:
                if link_type == "html":
                    value = pattern.sub(
                        lambda m: (
                            f"<a href='{term.link}' class='link link-primary'>{m.group(0)}</a>"  # noqa: B023
                        ),
                        value,
                    )
                else:
                    value = pattern.sub(lambda m: f"[{m.group(0)}]({term.link})", value)  # noqa: B023

    return value


def static_url(filename: str) -> str:
    """Generate a static file URL with a cache-busting query parameter.

    In development, appends the file's mtime so the browser fetches fresh
    assets after every Tailwind rebuild.  In production, uses the package
    version so there is zero per-request filesystem overhead.
    """
    from flask import url_for

    base = url_for("static", filename=filename)

    if get_settings().env == "development":
        try:
            version: int | str = (STATIC_PATH / filename).stat().st_mtime_ns
        except OSError:
            version = vweb.__version__
    else:
        version = vweb.__version__

    return f"{base}?v={version}"


def htmx_response(*parts: str) -> Markup:
    """Concatenate HTML fragments into a single HTMX response without escaping.

    Safely join rendered HTML strings (from ``render_template`` and
    ``catalog.render``) that may be a mix of plain ``str`` and ``Markup``.
    Without this, ``Markup.__radd__`` escapes any plain-string neighbors.

    Args:
        *parts: Rendered HTML strings to concatenate.

    Returns:
        Markup: The combined HTML, safe for return from a route.
    """
    return Markup("".join(parts))  # noqa: S704


def register_jinjax_catalog() -> jinjax.Catalog:
    """Create a standalone JinjaX catalog and register component folders.

    Create a JinjaX catalog with its own Jinja2 environment, register the
    shared templates folder and the templates root for blueprint page
    components, and configure custom filters.

    Returns:
        jinjax.Catalog: The configured JinjaX catalog.
    """
    catalog = jinjax.Catalog()

    catalog.add_folder(TEMPLATES_PATH)

    # Auto-discover route-specific template folders.
    # Each route package nests templates under templates/<route_name>/ so that
    # JinjaX dot-notation (e.g. "dictionary.Index") resolves via directory lookup.
    routes_path = Path(__file__).parent.parent / "routes"
    for path in sorted(routes_path.glob("*/templates")):
        catalog.add_folder(path)

    catalog.jinja_env.filters["from_markdown"] = from_markdown
    catalog.jinja_env.filters["from_markdown_no_p"] = from_markdown_no_p
    catalog.jinja_env.filters["format_date"] = format_date
    catalog.jinja_env.filters["humanize_date"] = humanize_date
    catalog.jinja_env.filters["link_terms"] = link_terms
    catalog.jinja_env.filters["normalize_string"] = normalize_string
    catalog.jinja_env.globals["user_campaign_experience"] = user_campaign_experience  # ty:ignore[invalid-assignment]
    catalog.jinja_env.add_extension("jinja2.ext.do")
    catalog.jinja_env.trim_blocks = True
    catalog.jinja_env.lstrip_blocks = True

    return catalog
