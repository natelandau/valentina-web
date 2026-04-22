"""Data-access helpers using the global context on Flask's g object."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import abort, g, session
from vclient.exceptions import APIError

from vweb.lib.guards import is_storyteller

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


def get_visible_characters_for_campaign(campaign_id: str) -> list[Character]:
    """Return characters in the campaign visible to the current user, sorted A-Z.

    Apply the standard visibility rule: everyone sees PLAYER-type characters;
    only storytellers (and admins) additionally see STORYTELLER-type characters.
    Sort is case-insensitive by character name.

    Args:
        campaign_id: The campaign to list characters for.

    Returns:
        A sorted list of visible characters.
    """
    all_characters = g.global_context.characters_by_campaign.get(campaign_id, [])
    privileged = is_storyteller()
    visible = [
        character
        for character in all_characters
        if character.type == "PLAYER" or (privileged and character.type == "STORYTELLER")
    ]
    return sorted(visible, key=lambda character: character.name.lower())


def get_active_campaign() -> Campaign | None:
    """Return the user's currently active campaign.

    Resolve the active campaign in priority order: session-stored
    ``last_campaign_id`` when it still maps to an existing campaign, otherwise
    the most-recently-modified campaign from the user's global context.
    """
    ctx = g.get("global_context")
    if ctx is None or not ctx.campaigns:
        return None

    last_id = session.get("last_campaign_id")
    selected = next((c for c in ctx.campaigns if c.id == last_id), None)
    if selected is not None:
        return selected

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


def _get_book_and_campaign(
    book_id: str,
) -> tuple[CampaignBook | None, Campaign | None]:
    """Look up a book and its campaign from the global context.

    Args:
        book_id: The book's unique identifier.

    Returns:
        A (book, campaign) tuple; either may be None if not found.
    """
    for books in g.global_context.books_by_campaign.values():
        for book in books:
            if book.id == book_id:
                campaign = next(
                    (c for c in g.global_context.campaigns if c.id == book.campaign_id),
                    None,
                )
                return book, campaign
    return None, None


def fetch_book_or_404(campaign_id: str, book_id: str) -> tuple[CampaignBook, Campaign]:
    """Look up book and campaign, abort 404 if not found.

    Args:
        campaign_id: The campaign's unique identifier.
        book_id: The book's unique identifier.

    Returns:
        A (book, campaign) tuple.

    Raises:
        werkzeug.exceptions.NotFound: If the book or campaign is not found,
            or the campaign ID doesn't match.
    """
    book, campaign = _get_book_and_campaign(book_id)
    if book is None or campaign is None or campaign.id != campaign_id:
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


def get_books_for_campaign(campaign_id: str) -> list[CampaignBook]:
    """Return books for a campaign from the global context, sorted by number.

    Use this in page-load reads where `g.global_context` is fresh. For
    post-mutation reads inside the same request, call the books service
    directly — the global context is stale until the next request.

    Args:
        campaign_id: The campaign's unique identifier.

    Returns:
        A list of CampaignBook ordered by `number` ascending.
    """
    books = g.global_context.books_by_campaign.get(campaign_id, [])
    return sorted(books, key=lambda b: b.number)


def get_chapters_for_book(book_id: str) -> list[CampaignChapter]:
    """Return chapters for a book from the global context, sorted by number.

    Use this in page-load reads where `g.global_context` is fresh. For
    post-mutation reads inside the same request, call the chapters service
    directly — the global context is stale until the next request.

    Args:
        book_id: The book's unique identifier.

    Returns:
        A list of CampaignChapter ordered by `number` ascending.
    """
    chapters = g.global_context.chapters_by_book.get(book_id, [])
    return sorted(chapters, key=lambda c: c.number)


def fetch_chapter_or_404(book_id: str, chapter_id: str) -> CampaignChapter:
    """Look up a chapter from the global context, abort 404 if not found.

    Args:
        book_id: The book's unique identifier.
        chapter_id: The chapter's unique identifier.

    Returns:
        The CampaignChapter object.
    """
    chapters = g.global_context.chapters_by_book.get(book_id, [])
    chapter = next((c for c in chapters if c.id == chapter_id), None)
    if chapter is None:
        abort(404)
    return chapter


def get_chapter_count_for_campaign(campaign_id: str) -> int:
    """Count chapters across every book in a campaign using the global context.

    Args:
        campaign_id: The campaign's unique identifier.

    Returns:
        The total number of chapters across every book in the campaign.
    """
    books = g.global_context.books_by_campaign.get(campaign_id, [])
    return sum(len(g.global_context.chapters_by_book.get(b.id, [])) for b in books)


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

    from vweb.lib.global_context import clear_global_context_cache

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

    clear_global_context_cache(session["company_id"], session["user_id"])
    return []
