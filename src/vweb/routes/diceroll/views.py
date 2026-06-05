"""Dice roll routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, get_args
from urllib.parse import urlparse

from flask import Blueprint, abort, make_response, request, url_for
from flask.views import MethodView
from vclient.constants import DiceSize
from vclient.exceptions import APIError, ValidationError

from vweb import catalog
from vweb.lib import cache
from vweb.lib.api import get_character_and_campaign
from vweb.routes.diceroll.services import (
    get_character_traits,
    get_roll_context,
    perform_custom_roll,
    perform_quickroll,
    perform_trait_roll,
)

if TYPE_CHECKING:
    from werkzeug.wrappers import Response

bp = Blueprint("diceroll", __name__)


def _safe_back_url(character_id: str) -> str:
    """Return the page the user came from, or the character page as a fallback.

    Honors `Referer` only when it's an http(s) same-origin URL outside the dice-roll
    routes. Roll-page referrers are rejected so Back cannot ping-pong between roll
    pages (e.g. /roll/A -> /roll/B -> /roll/A).
    """
    fallback = url_for("character_view.character", character_id=character_id)
    referrer = request.referrer
    if not referrer:
        return fallback

    parsed = urlparse(referrer)
    # Reject non-http(s) schemes (javascript:, data:, vbscript:, ...) to prevent
    # script execution when the back link is clicked.
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return fallback
    if parsed.netloc and parsed.netloc != urlparse(request.host_url).netloc:
        return fallback
    if parsed.path == "/roll" or parsed.path.startswith("/roll/"):
        return fallback
    return referrer


class DiceRollContentView(MethodView):
    """Render the dice roll UI with all three tab forms."""

    def get(self, character_id: str) -> Response:
        """Return the dice roll UI as fragment (HTMX/desktop modal) or full page (mobile).

        Mobile users navigate directly to this URL via `<a href>`, getting the full-page
        version; desktop modal triggers fire an HTMX request and receive the fragment that
        slots into the modal body. The response varies on HX-Request so downstream caches
        don't serve the wrong representation.

        Args:
            character_id: The character's unique identifier.

        Returns:
            Rendered HTML, fragment for HTMX or full page wrapped in PageLayout otherwise.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            abort(404)

        roll_ctx = get_roll_context(character=character, campaign=campaign)

        if request.headers.get("HX-Request"):
            body = catalog.render(
                "diceroll.DiceRollContent",
                character=character,
                campaign=campaign,
                roll_context=roll_ctx,
            )
        else:
            body = catalog.render(
                "diceroll.DiceRollPage",
                character=character,
                campaign=campaign,
                roll_context=roll_ctx,
                back_url=_safe_back_url(character_id),
            )

        response = make_response(body)
        response.headers["Vary"] = "HX-Request"
        return response


class DiceRollCustomView(MethodView):
    """Handle custom dice roll submissions."""

    def post(self, character_id: str) -> str:
        """Process a custom roll and return the results fragment.

        Args:
            character_id: The character's unique identifier.

        Returns:
            Rendered results fragment HTML.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            abort(404)

        try:
            raw_dice_size = int(request.form.get("dice_size", "10"))
            if raw_dice_size not in get_args(DiceSize):
                abort(400)
            dice_size = cast("DiceSize", raw_dice_size)
            num_dice = int(request.form.get("num_dice", "1"))
            difficulty = int(request.form.get("difficulty", "6"))
        except ValueError:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Invalid input - please check your values.",
            )

        if dice_size not in cache.options.get().gameplay.dice_size:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Invalid dice size.",
            )

        comment = request.form.get("comment", "").strip() or None

        try:
            diceroll = perform_custom_roll(
                character=character,
                campaign=campaign,
                dice_size=dice_size,
                num_dice=num_dice,
                difficulty=difficulty,
                comment=comment,
            )
        except APIError:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Roll failed - please try again.",
            )

        return catalog.render(
            "diceroll.partials.DiceRollResults",
            diceroll=diceroll,
            difficulty=difficulty,
        )


class DiceRollTraitsView(MethodView):
    """Handle trait-based dice roll submissions."""

    def post(self, character_id: str) -> str:
        """Process a trait-based roll and return the results fragment.

        Args:
            character_id: The character's unique identifier.

        Returns:
            Rendered results fragment HTML.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            abort(404)

        trait_one_id = request.form.get("trait_one_id", "")
        if not trait_one_id:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="At least one trait must be selected.",
            )

        try:
            difficulty = int(request.form.get("difficulty", "6"))
            num_desperation_dice = int(request.form.get("num_desperation_dice", "0"))
        except ValueError:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Invalid input - please check your values.",
            )

        trait_two_id = request.form.get("trait_two_id", "").strip() or None
        comment = request.form.get("comment", "").strip() or None

        character_traits = get_character_traits(character=character)

        try:
            diceroll = perform_trait_roll(
                character=character,
                campaign=campaign,
                character_traits=character_traits,
                trait_one_id=trait_one_id,
                trait_two_id=trait_two_id,
                difficulty=difficulty,
                num_desperation_dice=num_desperation_dice,
                comment=comment,
            )
        except ValueError as e:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error=str(e),
            )
        except APIError:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Roll failed - please try again.",
            )

        return catalog.render(
            "diceroll.partials.DiceRollResults",
            diceroll=diceroll,
            difficulty=difficulty,
        )


class DiceRollQuickrollView(MethodView):
    """Handle quickroll dice roll submissions."""

    def post(self, character_id: str) -> str:
        """Process a quickroll and return the results fragment.

        Args:
            character_id: The character's unique identifier.

        Returns:
            Rendered results fragment HTML.
        """
        character, campaign = get_character_and_campaign(character_id)
        if not character or not campaign:
            abort(404)

        quickroll_id = request.form.get("quickroll_id", "")
        if not quickroll_id:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Please select a quickroll.",
            )

        try:
            difficulty = int(request.form.get("difficulty", "6"))
            num_desperation_dice = int(request.form.get("num_desperation_dice", "0"))
        except ValueError:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error="Invalid input - please check your values.",
            )

        comment = request.form.get("comment", "").strip() or None

        try:
            diceroll = perform_quickroll(
                character=character,
                quickroll_id=quickroll_id,
                difficulty=difficulty,
                num_desperation_dice=num_desperation_dice,
                comment=comment,
            )
        except ValidationError as e:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error=f"Roll failed - please try again. {e.detail}",
            )
        except APIError as e:
            return catalog.render(
                "diceroll.partials.DiceRollResults",
                error=f"Roll failed - please try again. {e.detail}",
            )

        return catalog.render(
            "diceroll.partials.DiceRollResults",
            diceroll=diceroll,
            difficulty=difficulty,
        )


bp.add_url_rule(
    "/roll/<string:character_id>",
    view_func=DiceRollContentView.as_view("content"),
    methods=["GET"],
)
bp.add_url_rule(
    "/roll/<string:character_id>/custom",
    view_func=DiceRollCustomView.as_view("custom"),
    methods=["POST"],
)
bp.add_url_rule(
    "/roll/<string:character_id>/traits",
    view_func=DiceRollTraitsView.as_view("traits"),
    methods=["POST"],
)
bp.add_url_rule(
    "/roll/<string:character_id>/quickroll",
    view_func=DiceRollQuickrollView.as_view("quickroll"),
    methods=["POST"],
)
