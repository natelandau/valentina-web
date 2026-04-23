"""Data-access helpers using the global context on Flask's g object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import abort, g, session
from vclient import sync_dicerolls_service
from vclient.exceptions import APIError

from vweb.lib.blueprint_cache import get_all_traits
from vweb.lib.guards import is_storyteller

if TYPE_CHECKING:
    from datetime import datetime

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


@dataclass(frozen=True, slots=True)
class DiceRollDisplay:
    """Pre-resolved dice roll data shaped for the Recent Dicerolls card."""

    id: str
    character_id: str
    character_name: str
    user_id: str | None
    username: str
    num_dice: int
    dice_size: int
    num_desperation_dice: int
    trait_names: list[str]
    result_type: str | None
    result_humanized: str
    date_created: datetime


def get_recent_player_dicerolls(campaign_id: str, limit: int = 50) -> list[DiceRollDisplay]:
    """Return recent dice rolls made for player characters in a campaign.

    Fetch up to ``limit`` most-recent rolls for the campaign, keep only those
    whose character is a PLAYER-type character in the current campaign, and
    resolve user/character/trait names for compact in-card display. Since
    filtering happens after the fetch, the returned list may be shorter than
    ``limit`` when many of the recent rolls belong to storyteller/NPC
    characters — acceptable for an overview preview.

    Args:
        campaign_id: The campaign whose rolls to surface.
        limit: The maximum number of rolls to fetch from the API.

    Returns:
        Display-ready rows ordered newest first.
    """
    service = sync_dicerolls_service(
        on_behalf_of=g.requesting_user.id, company_id=session["company_id"]
    )
    page = service.get_page(campaignid=campaign_id, limit=limit, offset=0)

    ctx = g.global_context
    player_characters = {
        character.id: character
        for character in ctx.characters_by_campaign.get(campaign_id, [])
        if character.type == "PLAYER"
    }
    users_by_id = {user.id: user for user in ctx.users}
    all_traits = get_all_traits()

    # Sort newest-first locally — the API's default order is not contractually guaranteed
    rolls_newest_first = sorted(page.items, key=lambda r: r.date_created, reverse=True)

    displays: list[DiceRollDisplay] = []
    for roll in rolls_newest_first:
        character = player_characters.get(roll.character_id) if roll.character_id else None
        if character is None:
            continue

        user = users_by_id.get(roll.user_id) if roll.user_id else None
        trait_names = [all_traits[tid].name for tid in roll.trait_ids if tid in all_traits]

        displays.append(
            DiceRollDisplay(
                id=roll.id,
                character_id=character.id,
                character_name=character.name,
                user_id=user.id if user else None,
                username=user.username if user else "—",
                num_dice=roll.num_dice,
                dice_size=roll.dice_size,
                num_desperation_dice=roll.num_desperation_dice,
                trait_names=trait_names,
                result_type=roll.result.total_result_type if roll.result else None,
                result_humanized=roll.result.total_result_humanized if roll.result else "",
                date_created=roll.date_created,
            )
        )
    return displays


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
