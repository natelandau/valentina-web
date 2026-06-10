"""Data-access helpers using the global context on Flask's g object."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import abort, g, session
from vclient.exceptions import APIError

from vweb.lib import cache

if TYPE_CHECKING:
    from vclient.models import CampaignBook, CampaignChapter, Character
    from vclient.models.campaigns import Campaign
    from vclient.models.users import CampaignExperience


def count_notes(service: Any, parent_id: str) -> int:
    """Return the number of notes on an entity via the given service, 0 on API error.

    Fall back to zero so a transient notes endpoint failure doesn't break the
    surrounding page render.
    """
    try:
        return len(service.list_all_notes(parent_id))
    except APIError:
        return 0


def get_characters_for_campaign(campaign_id: str) -> list[Character]:
    """Return the campaign's characters from the global context, sorted A-Z.

    The API already scopes the character list to what the requesting user may
    see (via the on-behalf-of header), so no client-side type filtering is
    applied here. Sort is case-insensitive by character name.

    Args:
        campaign_id: The campaign to list characters for.

    Returns:
        The campaign's characters, sorted by name.
    """
    characters = g.global_context.characters_by_campaign.get(campaign_id, [])
    return sorted(characters, key=lambda character: character.name.lower())


def get_remembered_campaign(campaigns: list[Campaign]) -> Campaign | None:
    """Return the session-remembered campaign if it still exists in the given list.

    The remembered id may be stale (a deleted campaign, or one belonging to a
    previously selected company), so it only counts when it resolves against
    the provided list. Shared by the index entry redirect and
    ``get_active_campaign`` so both layers agree on what "remembered" means.

    Args:
        campaigns: The campaigns to resolve the remembered id against.

    Returns:
        The remembered campaign, or None when nothing valid is remembered.
    """
    last_id = session.get("last_campaign_id")
    return next((c for c in campaigns if c.id == last_id), None)


def get_active_campaign() -> Campaign | None:
    """Return the user's currently active campaign.

    Resolve the active campaign in priority order: session-stored
    ``last_campaign_id`` when it still maps to an existing campaign, otherwise
    the most-recently-modified campaign from the user's global context.
    """
    ctx = g.get("global_context")
    if ctx is None or not ctx.campaigns:
        return None

    remembered = get_remembered_campaign(ctx.campaigns)
    if remembered is not None:
        return remembered

    return max(ctx.campaigns, key=lambda c: c.date_modified)


def get_character_and_campaign(
    character_id: str,
) -> tuple[Character | None, Campaign | None]:
    """Look up a character and its campaign from the company context.

    Args:
        character_id: The character's unique identifier.

    Returns:
        A (character, campaign) tuple; either may be None if not found.
    """
    character = next((c for c in g.global_context.characters if c.id == character_id), None)
    if character is None:
        return None, None

    campaign = next((c for c in g.global_context.campaigns if c.id == character.campaign_id), None)
    return character, campaign


def fetch_book_or_404(campaign_id: str, book_id: str) -> tuple[CampaignBook, Campaign]:
    """Look up book and campaign, abort 404 if not found.

    Args:
        campaign_id: The campaign's unique identifier.
        book_id: The book's unique identifier.

    Returns:
        A (book, campaign) tuple.

    Raises:
        werkzeug.exceptions.NotFound: If the book or campaign is not found.
    """
    campaign = next((c for c in g.global_context.campaigns if c.id == campaign_id), None)
    if campaign is None:
        abort(404)
    book = next((b for b in cache.campaign_content.books(campaign_id) if b.id == book_id), None)
    if book is None:
        abort(404)
    return book, campaign


def fetch_campaign_or_404(campaign_id: str) -> Campaign:
    """Look up a campaign by ID, abort 404 if not found.

    Args:
        campaign_id: The campaign's unique identifier.

    Returns:
        The Campaign object.

    Raises:
        werkzeug.exceptions.NotFound: If the campaign is not found.
    """
    campaign = next((c for c in g.global_context.campaigns if c.id == campaign_id), None)
    if campaign is None:
        abort(404)
    return campaign


def fetch_chapter_or_404(campaign_id: str, book_id: str, chapter_id: str) -> CampaignChapter:
    """Look up a chapter via the lazy chapters cache, abort 404 if not found.

    Assumes the caller has already verified the campaign and book exist (callers
    invoke ``fetch_book_or_404`` first); a bogus campaign/book yields an empty
    chapter list and therefore a chapter 404.

    Args:
        campaign_id: The campaign the book belongs to.
        book_id: The book's unique identifier.
        chapter_id: The chapter's unique identifier.

    Returns:
        The CampaignChapter object.
    """
    chapter = next(
        (c for c in cache.campaign_content.chapters(campaign_id, book_id) if c.id == chapter_id),
        None,
    )
    if chapter is None:
        abort(404)
    return chapter


def get_campaign_name(campaign_id: str) -> str:
    """Look up a campaign name from the global context.

    Args:
        campaign_id: The campaign's unique identifier.

    Returns:
        The campaign name, or "Unknown" if not found.
    """
    campaign = next((c for c in g.global_context.campaigns if c.id == campaign_id), None)
    return campaign.name if campaign else "Unknown"


def get_user_campaign_experience(user_id: str, campaign_id: str) -> CampaignExperience | None:
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


def validate_and_submit_experience(
    form_data: dict,
    user_id: str,
    campaign_id: str,
    on_behalf_of: str,
) -> list[str]:
    """Validate experience form data and submit to the API if valid.

    Args:
        form_data: The form data dict with 'xp' and 'cool_points' keys.
        user_id: The user receiving the experience.
        campaign_id: The campaign to award experience in.
        on_behalf_of: The user making the request (On-Behalf-Of header).

    Returns:
        A list of validation error strings (empty on success).
    """
    from vclient import sync_users_service

    errors: list[str] = []

    try:
        xp_amount = int(form_data.get("xp", "0"))
    except ValueError:
        errors.append("XP must be a whole number")
        xp_amount = 0

    try:
        cp_amount = int(form_data.get("cool_points", "0"))
    except ValueError:
        errors.append("Cool Points must be a whole number")
        cp_amount = 0

    if not errors and xp_amount == 0 and cp_amount == 0:
        errors.append("Enter at least one value greater than zero")

    if errors:
        return errors

    svc = sync_users_service(on_behalf_of=on_behalf_of, company_id=session["company_id"])

    if xp_amount > 0:
        svc.add_xp(user_id, campaign_id, amount=xp_amount)

    if cp_amount > 0:
        svc.add_cool_points(user_id, campaign_id, amount=cp_amount)

    cache.global_context.clear_current()
    return []
