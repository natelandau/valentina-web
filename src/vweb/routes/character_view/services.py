"""Business logic for editing trait trackers and character health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from vclient import sync_character_traits_service, sync_characters_service
from vclient.constants import TrackerAction

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vclient.models import Health, Tracker


# "set" is the sheet's name for replacing a counter's state; the API exposes it as its own endpoint.
type SheetAction = TrackerAction | Literal["set"]


@dataclass(frozen=True)
class TrackerRequest:
    """A validated tracker or health action from the sheet."""

    action: SheetAction
    current: int | None


def parse_tracker_request(
    form: Mapping[str, str], *, allowed_actions: tuple[str, ...]
) -> TrackerRequest:
    """Validate the submitted form fields for a tracker or health action.

    Args:
        form: The submitted form fields.
        allowed_actions: Actions the endpoint accepts.

    Returns:
        The validated request.

    Raises:
        ValueError: If the action or `current` is missing or invalid.
    """
    raw_action = form.get("action", "")
    if raw_action not in allowed_actions:
        msg = f"Unsupported action: {raw_action!r}"
        raise ValueError(msg)
    action = cast("SheetAction", raw_action)

    current: int | None = None
    if action == "set":
        current = int(form.get("current", ""))
        if current < 0:
            msg = "current must not be negative"
            raise ValueError(msg)

    return TrackerRequest(action=action, current=current)


def fetch_trait_tracker(
    character_id: str, character_trait_id: str, *, user_id: str, company_id: str
) -> Tracker:
    """Fetch the current state of a trait tracker."""
    return sync_character_traits_service(
        character_id=character_id, on_behalf_of=user_id, company_id=company_id
    ).get_tracker(character_trait_id)


def update_trait_tracker(
    character_id: str,
    character_trait_id: str,
    request: TrackerRequest,
    *,
    user_id: str,
    company_id: str,
) -> Tracker:
    """Apply a request to a trait tracker through the API.

    Returns:
        The tracker as stored after the change.
    """
    service = sync_character_traits_service(
        character_id=character_id, on_behalf_of=user_id, company_id=company_id
    )
    if request.action == "set":
        return service.set_tracker(character_trait_id, current=request.current)
    return service.apply_tracker_action(character_trait_id, request.action, amount=1)


def fetch_health(character_id: str, *, user_id: str, company_id: str) -> Health:
    """Fetch the current health of a character."""
    return sync_characters_service(on_behalf_of=user_id, company_id=company_id).get_health(
        character_id
    )


def update_health(
    character_id: str, request: TrackerRequest, *, user_id: str, company_id: str
) -> Health:
    """Apply a damage or heal request to a character's health through the API.

    Returns:
        The health as stored after the change.
    """
    # The health endpoint's allowed actions never include "set".
    action = cast("TrackerAction", request.action)
    return sync_characters_service(on_behalf_of=user_id, company_id=company_id).apply_health_action(
        character_id, action, amount=1
    )
