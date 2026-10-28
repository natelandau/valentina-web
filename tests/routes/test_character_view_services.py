"""Tests for tracker and health request parsing and API orchestration."""

from __future__ import annotations

import pytest
from vclient.testing import CounterTrackerFactory, HealthFactory, Routes

from vweb.routes.character_view.services import (
    TrackerRequest,
    parse_tracker_request,
    update_health,
    update_trait_tracker,
)

ACTIONS = ("set", "add_stain", "remove_stain")


def test_parse_accepts_set_with_current() -> None:
    """Verify a set request carries its integer current."""
    result = parse_tracker_request({"action": "set", "current": "3"}, allowed_actions=ACTIONS)

    assert result == TrackerRequest(action="set", current=3)


def test_parse_accepts_stain_action_without_current() -> None:
    """Verify a stain action needs no current."""
    result = parse_tracker_request({"action": "add_stain"}, allowed_actions=ACTIONS)

    assert result == TrackerRequest(action="add_stain", current=None)


@pytest.mark.parametrize(
    "form",
    [
        {"action": "set", "current": "abc"},
        {"action": "set", "current": "-1"},
        {"action": "set"},
        {"action": "explode"},
        {},
        {"action": "damage"},
        {"action": "heal"},
        {"action": "spend"},
    ],
)
def test_parse_rejects_invalid_forms(form) -> None:
    """Verify malformed requests raise ValueError."""
    with pytest.raises(ValueError):  # noqa: PT011
        parse_tracker_request(form, allowed_actions=ACTIONS)


def test_parse_rejects_action_outside_allowed() -> None:
    """Verify an action the endpoint does not allow is rejected."""
    with pytest.raises(ValueError):  # noqa: PT011
        parse_tracker_request({"action": "set", "current": "1"}, allowed_actions=("damage", "heal"))


def test_update_trait_tracker_set_returns_stored_tracker(fake_vclient) -> None:
    """Verify a set request goes to the API and returns the stored tracker."""
    # Given the API stores current=3
    fake_vclient.set_response(
        Routes.CHARACTER_TRAITS_TRACKER_SET, model=CounterTrackerFactory.build(size=7, current=3)
    )

    # When setting the tracker
    result = update_trait_tracker(
        "char-1",
        "ct-1",
        TrackerRequest(action="set", current=3),
        user_id="test-user-id",
        company_id="test-company-id",
    )

    # Then the stored state comes back
    assert result.current == 3


def test_update_health_sends_action_with_amount_one(fake_vclient) -> None:
    """Verify a health action reaches the API and returns the stored health."""
    # Given the API stores one point of damage
    fake_vclient.set_response(
        Routes.CHARACTERS_HEALTH_ACTION, model=HealthFactory.build(size=5, damage=1, levels=None)
    )

    # When damaging health
    result = update_health(
        "char-1",
        TrackerRequest(action="damage", current=None),
        user_id="test-user-id",
        company_id="test-company-id",
    )

    # Then the stored damage comes back
    assert result.damage == 1
