"""Jinja configuration for the vweb application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import jinjax
from flask import g, session, url_for

import vweb
from vweb.api_client.constants import (
    MAX_CUSTOM_FLAW_XP_COST,
    MAX_LONG_TEXT_LENGTH,
    MAX_URL_LENGTH,
    MIN_CUSTOM_FLAW_XP_COST,
)
from vweb.config import get_settings
from vweb.constants import (
    MAX_AVATAR_SIZE,
    MAX_AVATAR_SIZE_MB,
    MAX_IMAGE_SIZE,
    MAX_IMAGE_SIZE_MB,
    STATIC_PATH,
    TEMPLATES_PATH,
)
from vweb.lib import cache
from vweb.lib.api import (
    get_active_campaign,
    get_selectable_characters,
    get_user_campaign_experience,
    resolve_characters,
)
from vweb.lib.character_profile import (
    character_trait_accepts_specialties,
    character_trait_specialty_keep_rating,
)
from vweb.lib.guards import (
    can_edit_character,
    can_edit_trackers,
    can_edit_traits_free,
    can_grant_experience,
    can_manage_campaign,
    can_manage_npcs,
    is_active_role,
    is_admin,
    is_approved_user,
    is_self,
    is_storyteller,
)
from vweb.lib.jinja_filters import (
    format_date,
    from_markdown,
    from_markdown_no_p,
    humanize_date,
    link_terms,
    normalize_string,
    to_roman,
)
from vweb.lib.trait_rules import is_derived_trait
from vweb.lib.urls import is_http_url
from vweb.lib.user_display import user_display_name
from vweb.lib.user_profile import has_custom_avatar, user_avatar_url

if TYPE_CHECKING:
    from flask import Flask

    from vweb.api_client.models import User
    from vweb.config import Settings
    from vweb.lib.cache.global_context import GlobalContext


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


def approved_companies() -> dict[str, dict[str, str]]:
    """Return the session's companies the user is approved and active in, keyed by company id.

    Single source for the membership filter shared by the header company
    switcher and the select-company page.
    """
    companies = session.get("companies", {})
    return {
        company_id: data
        for company_id, data in companies.items()
        if is_active_role(data.get("role"))
    }


_THREAT_WARNING_THRESHOLD = 2
_THREAT_ERROR_THRESHOLD = 4


def threat_badge_class(value: int) -> str:
    """Map a danger/desperation level (0-5) to its daisyUI badge color class.

    Single source for the severity thresholds shared by the campaign page
    badges and the company hub campaign cards.
    """
    if value >= _THREAT_ERROR_THRESHOLD:
        return "badge-error"
    if value >= _THREAT_WARNING_THRESHOLD:
        return "badge-warning"
    return "badge-neutral"


def dice_notation(num_dice: int, dice_size: int, dice_modifier: int = 0) -> str:
    """Format a dice pool such as "5d10", with a signed modifier suffix when non-zero."""
    notation = f"{num_dice}d{dice_size}"
    return f"{notation} {dice_modifier:+d}" if dice_modifier else notation


# Labels shared by the CharacterTypeBadge chips and the character list filters.
CHARACTER_TYPE_LABELS: dict[str, str] = {
    "PLAYER": "Player Character",
    "NPC": "NPC",
    "STORYTELLER": "Storyteller Character",
}


def character_type_label(character_type: str) -> str:
    """Return the display label for a character type.

    Registered as a Jinja global so templates (the CharacterTypeBadge chip) read
    labels from the same source as the filter options, preventing drift.

    Args:
        character_type: A character type value (e.g. ``"PLAYER"``).

    Returns:
        The human-readable label, or a title-cased fallback for unknown types.
    """
    return CHARACTER_TYPE_LABELS.get(character_type, character_type.title())


def birth_year_label(birth_year: int) -> str:
    """Return a birth year for display, marking years before 1 CE as BCE.

    Args:
        birth_year: The year of birth; negative years are BCE.

    Returns:
        The year as written on a character sheet, e.g. ``"1967"`` or ``"1250 BCE"``.
    """
    return f"{-birth_year} BCE" if birth_year < 0 else str(birth_year)


def character_age_label(age: int | None, birth_year: int | None) -> str | None:
    """Return a character's age as shown on the sheet, e.g. ``"23 (B. 1967)"``.

    The API derives ``age`` from the birth year on the campaign's in-game date, so the
    two always agree. Characters without a birth year show their stored age alone.

    Args:
        age: The character's age from the API.
        birth_year: The character's birth year, when recorded.

    Returns:
        The display string, or None when neither is known.
    """
    if birth_year is None:
        return str(age) if age is not None else None
    born = f"B. {birth_year_label(birth_year)}"
    return f"{age} ({born})" if age is not None else born


def build_fragment_url(endpoint: str, **kwargs: object) -> str:
    """Build an HTMX fragment URL, dropping kwargs with empty or None values.

    Resolve ``endpoint`` via ``url_for`` with all kwargs whose values are
    non-empty and non-None. Flask sends known path variables to the URL path
    and unknown kwargs to the query string, so the same helper works for any
    endpoint — you don't need to pre-split which kwargs are path vars.

    Used by lazy-card wrappers so parents can pass sparse props without the
    URL ending up full of ``&foo=&bar=`` noise.

    Args:
        endpoint: The Flask endpoint name to resolve.
        **kwargs: Query string parameters (and any path variables the endpoint
            requires). Empty strings and ``None`` are dropped.

    Returns:
        A URL string with kwargs URL-encoded into the path and/or query.
    """
    filtered: dict[str, Any] = {
        key: value for key, value in kwargs.items() if value is not None and value != ""
    }
    return url_for(endpoint, **filtered)


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
    catalog.jinja_env.filters["to_roman"] = to_roman
    catalog.jinja_env.globals["user_campaign_experience"] = get_user_campaign_experience  # ty:ignore[invalid-assignment]
    catalog.jinja_env.globals["character_age_label"] = character_age_label  # ty:ignore[invalid-assignment]
    catalog.jinja_env.add_extension("jinja2.ext.do")
    # JinjaX builds its environment without autoescape (Jinja2 defaults it off),
    # which would let user-controlled API data reflect raw HTML into every page.
    catalog.jinja_env.autoescape = True
    catalog.jinja_env.trim_blocks = True
    catalog.jinja_env.lstrip_blocks = True

    return catalog


def configure_jinja(app: Flask, s: Settings, catalog: jinjax.Catalog) -> None:
    """Set up Jinja2 globals and sync the JinjaX catalog environment.

    Args:
        app: The Flask application instance.
        s: The application settings.
        catalog: The JinjaX catalog to sync with Flask's Jinja environment.
    """
    app.jinja_env.add_extension("jinja2.ext.loopcontrols")
    jinja_globals = cast("dict[str, Any]", app.jinja_env.globals)
    jinja_globals["catalog"] = catalog
    jinja_globals["app_name"] = s.app_name
    jinja_globals["version"] = vweb.__version__
    jinja_globals["static_url"] = static_url
    jinja_globals["build_fragment_url"] = build_fragment_url
    jinja_globals["oauth_discord_enabled"] = bool(s.oauth.discord.client_id)
    jinja_globals["oauth_github_enabled"] = bool(s.oauth.github.client_id)
    jinja_globals["oauth_google_enabled"] = bool(s.oauth.google.client_id)
    jinja_globals["oauth_apple_enabled"] = s.oauth.apple.is_configured

    def _get_global_context() -> GlobalContext | None:
        return g.get("global_context")

    jinja_globals["global_context"] = _get_global_context
    jinja_globals["active_campaign"] = get_active_campaign
    jinja_globals["get_selectable_characters"] = get_selectable_characters
    jinja_globals["resolve_characters"] = resolve_characters

    def _get_requesting_user() -> User | None:
        return g.get("requesting_user")

    jinja_globals["requesting_user"] = _get_requesting_user
    jinja_globals["get_all_traits"] = cache.blueprint.traits
    jinja_globals["character_type_label"] = character_type_label
    jinja_globals["user_display_name"] = user_display_name
    jinja_globals["get_options"] = cache.options.get
    jinja_globals["tracker_actions_for"] = cache.options.tracker_actions_for
    jinja_globals["get_system_health"] = cache.system_status.get
    jinja_globals.update(
        MAX_IMAGE_SIZE=MAX_IMAGE_SIZE,
        MAX_AVATAR_SIZE=MAX_AVATAR_SIZE,
        MAX_IMAGE_SIZE_MB=MAX_IMAGE_SIZE_MB,
        MAX_AVATAR_SIZE_MB=MAX_AVATAR_SIZE_MB,
        MAX_LONG_TEXT_LENGTH=MAX_LONG_TEXT_LENGTH,
        MAX_URL_LENGTH=MAX_URL_LENGTH,
        MIN_CUSTOM_FLAW_XP_COST=MIN_CUSTOM_FLAW_XP_COST,
        MAX_CUSTOM_FLAW_XP_COST=MAX_CUSTOM_FLAW_XP_COST,
    )
    jinja_globals["is_admin"] = is_admin
    jinja_globals["is_active_role"] = is_active_role
    jinja_globals["is_approved_user"] = is_approved_user
    jinja_globals["is_storyteller"] = is_storyteller
    jinja_globals["is_self"] = is_self
    jinja_globals["has_custom_avatar"] = has_custom_avatar
    jinja_globals["user_avatar_url"] = user_avatar_url
    jinja_globals["can_manage_campaign"] = can_manage_campaign
    jinja_globals["can_manage_npcs"] = can_manage_npcs
    jinja_globals["can_grant_experience"] = can_grant_experience
    jinja_globals["can_edit_traits_free"] = can_edit_traits_free
    jinja_globals["can_edit_character"] = can_edit_character
    jinja_globals["can_edit_trackers"] = can_edit_trackers
    jinja_globals.update(
        is_derived_trait=is_derived_trait,
        character_trait_accepts_specialties=character_trait_accepts_specialties,
        character_trait_specialty_keep_rating=character_trait_specialty_keep_rating,
        is_http_url=is_http_url,
    )

    jinja_globals["approved_companies"] = approved_companies
    jinja_globals["threat_badge_class"] = threat_badge_class
    jinja_globals["dice_notation"] = dice_notation

    def _is_authenticated() -> bool:
        """Report whether a logged-in user backs this request.

        Distinct from ``requesting_user()`` (which only resolves on pages that
        load the global context): this is true for in-flight accounts too, such
        as pending-approval and company-selection, so their forms still get CSRF.
        """
        return bool(session.get("user_id"))

    jinja_globals["is_authenticated"] = _is_authenticated

    # Sync Flask's Jinja2 environment into the catalog's environment so
    # JinjaX components have access to url_for, config, and other app globals
    catalog.jinja_env.globals.update(app.jinja_env.globals)
    catalog.jinja_env.filters.update(app.jinja_env.filters)
    catalog.jinja_env.tests.update(app.jinja_env.tests)
    catalog.jinja_env.extensions.update(app.jinja_env.extensions)
