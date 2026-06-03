"""Shared lazy-card endpoints.

Serve HTMX fragments for reusable cards like Statistics and Recent Dicerolls.
Parent templates drop a ``<shared.cards.X>`` wrapper and the wrapper points
its ``hx-get`` at an endpoint here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from flask import Blueprint, abort, g, request, session, url_for
from flask.views import MethodView

from vweb import catalog
from vweb.lib import cache
from vweb.lib.api import (
    fetch_campaign_or_404,
    get_characters_for_campaign,
)
from vweb.lib.audit_log import (
    ENTITY_TYPES,
    get_audit_log_page,
    resolve_acting_user,
    resolve_entities,
    split_changes,
)
from vweb.lib.character_list import (
    build_filter_options,
    filter_characters,
    present_type_options,
)

if TYPE_CHECKING:
    from vweb.lib.cache.statistics import ScopeType

bp = Blueprint("shared_cards", __name__, url_prefix="/cards")


class StatisticsCardView(MethodView):
    """Lazy statistics card, scoped by exactly one of campaign/user/character."""

    def get(self) -> str:
        """Validate exactly one scope query arg and render the statistics fragment."""
        scopes: list[tuple[ScopeType, str]] = [
            ("campaign", request.args.get("campaign_id", "")),
            ("user", request.args.get("user_id", "")),
            ("character", request.args.get("character_id", "")),
        ]
        set_scopes = [(name, value) for name, value in scopes if value]
        if len(set_scopes) != 1:
            abort(400)

        scope_type, scope_id = set_scopes[0]
        return catalog.render(
            "shared.cards.partials.StatisticsContent",
            statistics=cache.statistics.get(scope_type, scope_id),
            title=request.args.get("title", "Statistics"),
            col_span=request.args.get("col_span", 0, type=int),
        )


bp.add_url_rule(
    "/statistics",
    view_func=StatisticsCardView.as_view("statistics"),
    methods=["GET"],
)


class DiceRollsCardView(MethodView):
    """Lazy Recent Dicerolls card, scoped by at least one of campaign/user/character."""

    def get(self) -> str:
        """Validate at least one scope query arg and render the dicerolls fragment."""
        campaign_id = request.args.get("campaign_id", "")
        user_id = request.args.get("user_id", "")
        character_id = request.args.get("character_id", "")

        if not any([campaign_id, user_id, character_id]):
            abort(400)

        rolls = cache.dicerolls.recent(
            campaign_id=campaign_id,
            character_id=character_id,
            user_id=user_id,
            limit=request.args.get("limit", 25, type=int),
        )
        return catalog.render(
            "shared.cards.partials.RecentDiceRollsContent",
            rolls=rolls,
            col_span=request.args.get("col_span", 1, type=int),
            page_size=request.args.get("page_size", 5, type=int),
            title=request.args.get("title", "Recent Dicerolls"),
            empty_message=request.args.get("empty_message", "No dicerolls yet"),
        )


bp.add_url_rule(
    "/dice-rolls",
    view_func=DiceRollsCardView.as_view("dice_rolls"),
    methods=["GET"],
)


class AuditLogCardView(MethodView):
    """Lazy audit log card with server-side Prev/Next pagination.

    Trusts the caller — the parent template decides where to render the card.
    The vclient API still enforces company-scoped authorization.
    """

    def get(self) -> str:
        """Return an HTMX fragment for the audit log card, scoped by optional filter args.

        Reads up to ten filter query args (acting_user_id, user_id, campaign_id, book_id,
        chapter_id, character_id, entity_type, operation, date_from, date_to) plus
        page_size and offset. Scope-active entity IDs are excluded from per-row entity
        links to avoid redundant context.
        """
        filter_keys = (
            "acting_user_id",
            "user_id",
            "campaign_id",
            "book_id",
            "chapter_id",
            "character_id",
            "entity_type",
            "operation",
            "date_from",
            "date_to",
        )
        filters = {key: request.args.get(key, "") for key in filter_keys}
        page_size = request.args.get("page_size", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        # card_id is interpolated into JS getElementById calls and DOM id attributes in the
        # template, so restrict it to a DOM-id-safe charset to prevent injection.
        raw_card_id = request.args.get("card_id", "auditlog")
        card_id = re.sub(r"[^A-Za-z0-9_-]", "", raw_card_id) or "auditlog"

        page = get_audit_log_page(limit=page_size, offset=offset, **filters)

        # Scope-skip: hide entity links that duplicate an already-active scope filter.
        # acting_user_id filters by "who performed the action" and is NOT paired with
        # a resolved entity label; only the 5 "affected entity" filters go here.
        scope_skip_ids = {
            filters[key]
            for key in ("user_id", "campaign_id", "book_id", "chapter_id", "character_id")
            if filters[key]
        }

        context = g.global_context
        rows = []
        for log in page.items:
            field_diffs, other_entries = split_changes(log.changes)
            rows.append(
                {
                    "log": log,
                    "acting_user": resolve_acting_user(log.acting_user_id, context),
                    "entities": resolve_entities(log, context, skip_ids=scope_skip_ids),
                    "field_diffs": field_diffs,
                    "other_entries": other_entries,
                }
            )

        body_only = request.args.get("body_only", "") == "true"
        show_filters = request.args.get("show_filters", "") == "true"
        template_name = (
            "shared.cards.partials.AuditLogBody"
            if body_only
            else "shared.cards.partials.AuditLogContent"
        )
        render_kwargs: dict[str, Any] = {
            "rows": rows,
            "page_size": page_size,
            "offset": offset,
            "has_more": page.has_more,
            "filters": filters,
            "card_id": card_id,
            "empty_message": request.args.get("empty_message", "No audit log entries"),
        }
        if not body_only:
            render_kwargs["col_span"] = request.args.get("col_span", 0, type=int)
            render_kwargs["title"] = request.args.get("title", "Audit Log")
            render_kwargs["show_filters"] = show_filters
            render_kwargs["users"] = context.users if show_filters else []
            render_kwargs["entity_types"] = ENTITY_TYPES if show_filters else []
        return catalog.render(template_name, **render_kwargs)


bp.add_url_rule(
    "/audit-log",
    view_func=AuditLogCardView.as_view("audit_log"),
    methods=["GET"],
)


class CharacterListCardView(MethodView):
    """Lazy character list card with server-side player/class/type filtering.

    Scope resolves the roster the card shows, then optional filters narrow it.
    Filtering is server-side so the only client-side logic is display paging.
    """

    def _scoped_characters(self) -> list:
        """Resolve the pre-filter roster from the request's scope args.

        Campaign scope (``campaign_id`` + ``bucket`` of mine/others/all) applies
        the standard visibility rules then splits by owner; user scope
        (``user_id``) returns that user's characters across campaigns. Aborts 400
        when neither scope is supplied.
        """
        campaign_id = request.args.get("campaign_id", "")
        user_id = request.args.get("user_id", "")

        if campaign_id:
            fetch_campaign_or_404(campaign_id)
            characters = get_characters_for_campaign(campaign_id)
            bucket = request.args.get("bucket", "all")
            current_user_id = session.get("user_id", "")
            if bucket == "mine":
                return [c for c in characters if c.user_player_id == current_user_id]
            if bucket == "others":
                return [c for c in characters if c.user_player_id != current_user_id]
            return characters

        if user_id:
            owned = [c for c in g.global_context.characters if c.user_player_id == user_id]
            return sorted(owned, key=lambda character: character.name.lower())

        return abort(400)

    def get(self) -> str:
        """Return the character list card fragment (full card or body-only)."""
        base = self._scoped_characters()

        player = request.args.get("player", "").strip()
        character_class = request.args.get("char_class", "").strip()
        type_filter = request.args.get("type", "").strip()
        filtered = filter_characters(
            base,
            player_id=player or None,
            character_class=character_class or None,
            type_filter=type_filter or None,
        )

        page_size = request.args.get("page_size", 0, type=int)
        show_type = request.args.get("show_type", "") == "true"
        show_campaign = request.args.get("show_campaign", "") == "true"
        link_user_profile = request.args.get("link_user_profile", "") == "true"
        empty_message = request.args.get("empty_message", "No characters found")
        filters_active = bool(player or character_class or type_filter)

        if request.args.get("body_only", "") == "true":
            return catalog.render(
                "shared.cards.partials.CharacterListBody",
                characters=filtered,
                page_size=page_size,
                show_type=show_type,
                show_campaign=show_campaign,
                link_user_profile=link_user_profile,
                empty_message=empty_message,
                filters_active=filters_active,
            )

        # card_id is interpolated into DOM id attributes and hx-target selectors,
        # so restrict it to a DOM-id-safe charset.
        raw_card_id = request.args.get("card_id", "characterlist")
        card_id = re.sub(r"[^A-Za-z0-9_-]", "", raw_card_id) or "characterlist"

        show_filters = request.args.get("show_filters", "true") == "true"
        if show_filters:
            users_by_id = {user.id: user.username for user in g.global_context.users}
            player_options, class_options = build_filter_options(base, users_by_id)
            type_options = present_type_options(base)
        else:
            player_options, class_options, type_options = [], [], []

        # Only surface the filter control when at least one dimension can actually
        # narrow the list — a single-valued roster needs no filters.
        has_filters = len(player_options) > 1 or len(class_options) > 1 or len(type_options) > 1

        show_add_button = request.args.get("show_add_button", "") == "true"
        campaign_id = request.args.get("campaign_id", "")
        add_url = (
            url_for("character_create.selection_page", campaign_id=campaign_id)
            if show_add_button and campaign_id
            else ""
        )

        return catalog.render(
            "shared.cards.partials.CharacterListContent",
            card_id=card_id,
            title=request.args.get("title", "Characters"),
            characters=filtered,
            page_size=page_size,
            col_span=request.args.get("col_span", 0, type=int),
            show_type=show_type,
            show_campaign=show_campaign,
            link_user_profile=link_user_profile,
            show_add_button=show_add_button,
            add_url=add_url,
            has_filters=has_filters,
            empty_message=empty_message,
            filters_active=filters_active,
            campaign_id=campaign_id,
            bucket=request.args.get("bucket", "all"),
            user_id=request.args.get("user_id", ""),
            player_options=player_options,
            class_options=class_options,
            type_options=type_options,
            player=player,
            char_class=character_class,
            selected_type=type_filter,
        )


bp.add_url_rule(
    "/character-list",
    view_func=CharacterListCardView.as_view("character_list"),
    methods=["GET"],
)
