"""Shared audit log helpers.

Used by both the admin audit log page and the shared lazy-loaded audit log card.
Cross-cutting infrastructure per CLAUDE.md's route-centric structure rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import url_for
from markupsafe import Markup, escape

if TYPE_CHECKING:
    from vclient.models.audit_logs import AuditLog

    from vweb.lib.global_context import GlobalContext


@dataclass(frozen=True)
class FieldDiff:
    """One field's old/new values, pre-rendered as display HTML."""

    field: str
    old: Markup
    new: Markup


@dataclass(frozen=True)
class OtherEntry:
    """A changes-dict entry whose value didn't match the canonical {old, new} shape."""

    key: str
    value: Markup


def format_change_value(value: Any) -> Markup:
    """Render a single change-dict value as safe HTML for the Old/New panel.

    None becomes a muted em-dash, booleans become Yes/No, lists and dicts become
    pretty-printed JSON inside a <pre> block, and other scalars become
    HTML-escaped strings.

    Args:
        value: The raw change value from an AuditLog.changes dict entry.

    Returns:
        Markup: Safe HTML ready to render without further escaping.
    """
    if value is None:
        return Markup('<em class="opacity-40">—</em>')
    if isinstance(value, bool):
        return Markup("Yes") if value else Markup("No")
    if isinstance(value, (list, dict)):
        pretty = json.dumps(value, indent=2, sort_keys=True, default=str)
        # Escape only chars that matter in HTML text content; leave quotes literal so
        # JSON double-quoted strings remain readable in the rendered <pre> block.
        safe_content = pretty.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # S704: safe because safe_content is built from manual &/</> replacement above,
        # not from untrusted input passed directly — ruff can't statically verify this.
        return Markup(  # noqa: S704
            f'<pre class="text-xs whitespace-pre-wrap break-words">{safe_content}</pre>'
        )
    return escape(str(value))


def split_changes(
    changes: dict[str, Any] | None,
) -> tuple[list[FieldDiff], list[OtherEntry]]:
    """Parse an AuditLog.changes dict into canonical field diffs plus off-shape entries.

    Canonical shape is `{field: {"old": ..., "new": ...}}` (extra keys tolerated).
    Anything that doesn't match — flat scalars, differently-nested dicts — surfaces
    as OtherEntry so nothing is silently dropped.

    Args:
        changes: The raw changes dict from an AuditLog entry, or None.

    Returns:
        A two-tuple of (diffs, others) where diffs contains FieldDiff objects for
        canonical entries and others contains OtherEntry objects for everything else.
    """
    diffs: list[FieldDiff] = []
    others: list[OtherEntry] = []
    if not changes:
        return diffs, others
    for key, value in changes.items():
        if isinstance(value, dict) and {"old", "new"} <= set(value.keys()):
            diffs.append(
                FieldDiff(
                    field=key,
                    old=format_change_value(value["old"]),
                    new=format_change_value(value["new"]),
                )
            )
        else:
            others.append(OtherEntry(key=key, value=format_change_value(value)))
    return diffs, others


def resolve_acting_user(
    acting_user_id: str | None,
    context: GlobalContext,
) -> tuple[str, str]:
    """Resolve the user who performed an action to a display name and profile URL.

    Falls back to the raw ID with an empty URL when the user is not in the context.
    Returns two empty strings when the ID is None or empty.

    Args:
        acting_user_id: The user ID from AuditLog.acting_user_id (may be None/empty).
        context: The request-scoped GlobalContext populated by the before_request hook.

    Returns:
        A two-tuple of (display_name, profile_url). Both are empty strings when the
        input is falsy; display_name falls back to the raw ID when unresolvable.
    """
    if not acting_user_id:
        return ("", "")

    user = next((u for u in context.users if u.id == acting_user_id), None)
    if user:
        return (user.username, url_for("profile.profile", user_id=user.id))
    return (acting_user_id, "")


def resolve_entities(
    log: AuditLog,
    context: GlobalContext,
    *,
    skip_ids: set[str] | None = None,
) -> list[tuple[str, str, str | None]]:
    """Map populated entity IDs on an audit log to (label, display_name, url) tuples.

    Checks entity IDs in a fixed order (user, campaign, character, book, chapter).
    Any ID in ``skip_ids`` is omitted — the shared audit log card uses this to hide
    entity links that duplicate an already-active scope filter.

    Args:
        log: The AuditLog entry whose entity IDs should be resolved.
        context: The request-scoped GlobalContext for looking up display names and URLs.
        skip_ids: Optional set of entity IDs to omit from the result. Defaults to None
            (no skipping).

    Returns:
        A list of (label, display_name, url_or_none) tuples, one per populated
        entity ID not in skip_ids.
    """
    skip_ids = skip_ids or set()
    results: list[tuple[str, str, str | None]] = []

    if log.user_id and log.user_id not in skip_ids:
        results.append(_resolve_user(log.user_id, context))

    if log.campaign_id and log.campaign_id not in skip_ids:
        results.append(_resolve_campaign(log.campaign_id, context))

    if log.character_id and log.character_id not in skip_ids:
        results.append(_resolve_character(log.character_id, context))

    if log.book_id and log.book_id not in skip_ids:
        results.append(_resolve_book(log.book_id, log.campaign_id, context))

    if log.chapter_id and log.chapter_id not in skip_ids:
        results.append(("Chapter", log.chapter_id, None))

    return results


def _resolve_user(user_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    user = next((u for u in context.users if u.id == user_id), None)
    if user:
        return ("User", user.username, url_for("profile.profile", user_id=user.id))
    return ("User", user_id, None)


def _resolve_campaign(campaign_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    campaign = next((c for c in context.campaigns if c.id == campaign_id), None)
    if campaign:
        return (
            "Campaign",
            campaign.name,
            url_for("campaign.campaign", campaign_id=campaign.id),
        )
    return ("Campaign", campaign_id, None)


def _resolve_character(character_id: str, context: GlobalContext) -> tuple[str, str, str | None]:
    character = next((c for c in context.characters if c.id == character_id), None)
    if character:
        return (
            "Character",
            character.name,
            url_for("character_view.character", character_id=character.id),
        )
    return ("Character", character_id, None)


def _resolve_book(
    book_id: str, campaign_id: str | None, context: GlobalContext
) -> tuple[str, str, str | None]:
    # Narrow search to the specific campaign when possible
    if campaign_id and campaign_id in context.books_by_campaign:
        books = context.books_by_campaign[campaign_id]
    else:
        books = [
            book for campaign_books in context.books_by_campaign.values() for book in campaign_books
        ]

    book = next((b for b in books if b.id == book_id), None)
    if book and campaign_id:
        return (
            "Book",
            book.name,
            url_for("book_view.book_detail", campaign_id=campaign_id, book_id=book.id),
        )
    return ("Book", book.name if book else book_id, None)
