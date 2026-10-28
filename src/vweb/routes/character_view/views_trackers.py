"""Endpoints that change trait trackers and character health."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from flask import Response, abort, flash, g, request, session
from flask.views import MethodView

from vweb.lib import cache
from vweb.lib.api import API_UNAVAILABLE_ERRORS, get_character_and_campaign
from vweb.lib.catalog import catalog
from vweb.lib.character_profile import TRAIT_API_ERRORS, find_character_trait
from vweb.lib.guards import can_edit_trackers
from vweb.lib.htmx import htmx_flash_only, htmx_response_with_flash
from vweb.routes.character_view.services import (
    TrackerRequest,
    fetch_health,
    fetch_trait_tracker,
    parse_tracker_request,
    update_health,
    update_trait_tracker,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from vclient.models import Character, CharacterFullSheet, CharacterTrait, Health, Tracker

TRAIT_ACTIONS = ("set", "add_stain", "remove_stain")
HEALTH_ACTIONS = ("damage", "heal")
SAVE_FAILED_MESSAGE = "Could not save, try again."


def _refuse(message: str, status: int) -> NoReturn:
    """Stop the request: a flash for htmx, which drops non-2xx bodies, else the status code."""
    if request.headers.get("HX-Request") != "true":
        abort(status)
    flash(message, "error")
    abort(htmx_flash_only())


def _authorized_character(character_id: str) -> Character:
    """Return the character, or refuse the request when it is missing or not editable."""
    character, _campaign = get_character_and_campaign(character_id)
    if character is None:
        _refuse("Character not found. Reload the page.", 404)
    if not can_edit_trackers(character):
        _refuse("You cannot change this character's trackers.", 403)
    return character


def _parse_or_abort(allowed_actions: tuple[str, ...]) -> TrackerRequest:
    """Parse the submitted form or abort with 400."""
    try:
        return parse_tracker_request(request.form, allowed_actions=allowed_actions)
    except ValueError:
        abort(400)


def _api_ids() -> dict[str, str]:
    return {"user_id": g.requesting_user.id, "company_id": session["company_id"]}


def _render_tracker(character: Character, character_trait: CharacterTrait, tracker: Tracker) -> str:
    return catalog.render(
        "character_view.partials.TraitTracker",
        character=character,
        character_trait=character_trait.model_copy(update={"tracker": tracker}),
    )


def _render_health(character: Character, health: Health) -> str:
    return catalog.render("character_view.partials.HealthTrack", character=character, health=health)


def _store_tracker(character_id: str, character_trait_id: str, tracker: Tracker) -> None:
    """Write a tracker returned by the API into the cached sheet."""

    def apply(sheet: CharacterFullSheet) -> None:
        character_trait = find_character_trait(sheet, character_trait_id)
        if character_trait is not None:
            character_trait.tracker = tracker

    cache.character_sheet.update(character_id, apply)


def _store_health(character_id: str, health: Health) -> None:
    """Write the health returned by the API into the cached sheet."""

    def apply(sheet: CharacterFullSheet) -> None:
        sheet.character.health = health

    cache.character_sheet.update(character_id, apply)


def _recover[T](
    detail: str | None,
    *,
    refetch: Callable[[], T],
    store: Callable[[T], None],
    render: Callable[[T], str],
    fallback: T | None,
) -> Response | str:
    """Flash the API's rejection and redraw the current state so the page matches the server.

    Args:
        detail: The API's explanation of the rejection, if any.
        refetch: Read the current state from the API.
        store: Write the refetched state into the cached sheet.
        render: Render the state as the swapped-in partial.
        fallback: State to draw when the refetch fails; None leaves the page as it is.

    Returns:
        The redrawn partial with the flash, or only the flash when there is nothing to draw.
    """
    flash(detail or "Could not update", "error")
    state: T | None
    try:
        state = refetch()
    except API_UNAVAILABLE_ERRORS:
        state = fallback
    else:
        store(state)
    if state is None:
        return htmx_flash_only()
    return htmx_response_with_flash(render(state))


def _save_failed(character_id: str) -> Response:
    """Drop the cached sheet and flash a retry hint after the API call itself failed."""
    # A timeout can arrive after the API applied the change, so the cached sheet is suspect.
    cache.character_sheet.clear(character_id)
    flash(SAVE_FAILED_MESSAGE, "error")
    return htmx_flash_only()


class TraitTrackerView(MethodView):
    """Apply an action to a trait tracker."""

    def post(self, character_id: str, character_trait_id: str) -> Response | str:
        """Apply the submitted action and re-render the tracker.

        Returns:
            The tracker partial.
        """
        character = _authorized_character(character_id)
        tracker_request = _parse_or_abort(TRAIT_ACTIONS)

        full_sheet = cache.character_sheet.get(character_id, g.requesting_user.id)
        character_trait = find_character_trait(full_sheet, character_trait_id)
        if character_trait is None:
            _refuse("That trait is no longer on the sheet. Reload the page.", 404)

        try:
            tracker = update_trait_tracker(
                character_id, character_trait_id, tracker_request, **_api_ids()
            )
        except TRAIT_API_ERRORS as error:
            return _recover(
                error.detail,
                refetch=lambda: fetch_trait_tracker(character_id, character_trait_id, **_api_ids()),
                store=lambda fresh: _store_tracker(character_id, character_trait_id, fresh),
                render=lambda fresh: _render_tracker(character, character_trait, fresh),
                fallback=character_trait.tracker,
            )
        except API_UNAVAILABLE_ERRORS:
            return _save_failed(character_id)

        _store_tracker(character_id, character_trait_id, tracker)
        return _render_tracker(character, character_trait, tracker)


class HealthView(MethodView):
    """Apply an action to a character's health."""

    def post(self, character_id: str) -> Response | str:
        """Apply the submitted damage or heal and re-render the health track.

        Returns:
            The health partial.
        """
        character = _authorized_character(character_id)
        tracker_request = _parse_or_abort(HEALTH_ACTIONS)

        try:
            health = update_health(character_id, tracker_request, **_api_ids())
        except TRAIT_API_ERRORS as error:
            return _recover(
                error.detail,
                refetch=lambda: fetch_health(character_id, **_api_ids()),
                store=lambda fresh: _store_health(character_id, fresh),
                render=lambda fresh: _render_health(character, fresh),
                fallback=None,
            )
        except API_UNAVAILABLE_ERRORS:
            return _save_failed(character_id)

        _store_health(character_id, health)
        return _render_health(character, health)
