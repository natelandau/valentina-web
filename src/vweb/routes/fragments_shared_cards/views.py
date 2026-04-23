"""Shared lazy-card endpoints.

Serve HTMX fragments for reusable cards like Statistics and Recent Dicerolls.
Parent templates drop a ``<shared.cards.X>`` wrapper and the wrapper points
its ``hx-get`` at an endpoint here.
"""

from __future__ import annotations

from flask import Blueprint, abort, g, request
from flask.views import MethodView

from vweb import catalog
from vweb.lib.api import get_recent_player_dicerolls
from vweb.lib.audit_log import (
    get_audit_log_page,
    resolve_acting_user,
    resolve_entities,
    split_changes,
)
from vweb.lib.statistics_cache import ScopeType, get_statistics

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
            statistics=get_statistics(scope_type, scope_id),
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

        rolls = get_recent_player_dicerolls(
            campaign_id=campaign_id,
            character_id=character_id,
            user_id=user_id,
            limit=request.args.get("limit", 50, type=int),
        )
        return catalog.render(
            "shared.cards.partials.RecentDiceRollsContent",
            rolls=rolls,
            col_span=request.args.get("col_span", 1, type=int),
            pagination=request.args.get("pagination", 5, type=int),
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

        Reads up to six filter query args (acting_user_id, user_id, campaign_id, book_id,
        chapter_id, character_id) plus page_size and offset. Scope-active entity IDs are
        excluded from per-row entity links to avoid redundant context.
        """
        filter_keys = (
            "acting_user_id",
            "user_id",
            "campaign_id",
            "book_id",
            "chapter_id",
            "character_id",
        )
        filters = {key: request.args.get(key, "") for key in filter_keys}
        page_size = request.args.get("page_size", 10, type=int)
        offset = request.args.get("offset", 0, type=int)

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

        return catalog.render(
            "shared.cards.partials.AuditLogContent",
            rows=rows,
            page_size=page_size,
            offset=offset,
            has_more=page.has_more,
            filters=filters,
            card_id=request.args.get("card_id", "auditlog"),
            col_span=request.args.get("col_span", 0, type=int),
            title=request.args.get("title", "Audit Log"),
            empty_message=request.args.get("empty_message", "No audit log entries"),
        )


bp.add_url_rule(
    "/audit-log",
    view_func=AuditLogCardView.as_view("audit_log"),
    methods=["GET"],
)
