"""Tests for tracker and health request parsing and API orchestration."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import CounterTrackerFactory, HealthFactory, Routes
from vweb.routes.character_view.services import (
    TrackerRequest,
    parse_tracker_request,
    update_health,
    update_trait_tracker,
)

ACTIONS = ("set", "add_stain", "remove_stain")


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        ({"action": "set", "current": "3"}, TrackerRequest(action="set", current=3)),
        ({"action": "add_stain"}, TrackerRequest(action="add_stain", current=None)),
    ],
    ids=["set-with-current", "stain-without-current"],
)
def test_parse_accepts_valid_forms(form, expected) -> None:
    """Verify a set carries its integer current and other actions need none."""
    assert parse_tracker_request(form, allowed_actions=ACTIONS) == expected


@pytest.mark.parametrize(
    ("form", "allowed"),
    [
        ({"action": "set", "current": "abc"}, ACTIONS),
        ({"action": "set", "current": "-1"}, ACTIONS),
        ({"action": "set"}, ACTIONS),
        ({"action": "explode"}, ACTIONS),
        ({}, ACTIONS),
        ({"action": "damage"}, ACTIONS),
        ({"action": "set", "current": "1"}, ("damage", "heal")),
    ],
)
def test_parse_rejects_invalid_forms(form, allowed) -> None:
    """Verify malformed requests and actions the endpoint does not allow raise ValueError."""
    with pytest.raises(ValueError):  # noqa: PT011
        parse_tracker_request(form, allowed_actions=allowed)


@pytest.mark.parametrize(
    ("request_", "route", "json"),
    [
        (
            TrackerRequest(action="set", current=3),
            Routes.CHARACTER_TRAITS_TRACKER_SET,
            {"current": 3},
        ),
        (
            TrackerRequest(action="add_stain", current=None),
            Routes.CHARACTER_TRAITS_TRACKER_ACTION,
            {"action": "add_stain", "amount": 1},
        ),
    ],
    ids=["set", "action"],
)
def test_update_trait_tracker_sends_request(app, fake_vclient, request_, route, json) -> None:
    """Verify a set replaces the counter and other actions apply one step."""
    # When updating the tracker
    with app.test_request_context():
        seed_session()
        update_trait_tracker("char-1", "ct-1", request_)

    # Then the matching endpoint receives the request
    fake_vclient.assert_called(
        route, params={"character_id": "char-1", "character_trait_id": "ct-1"}, json=json, times=1
    )


def test_update_trait_tracker_set_returns_stored_tracker(app, fake_vclient) -> None:
    """Verify a set request goes to the API and returns the stored tracker."""
    # Given the API stores current=3
    fake_vclient.set_response(
        Routes.CHARACTER_TRAITS_TRACKER_SET, model=CounterTrackerFactory.build(size=7, current=3)
    )

    # When setting the tracker
    with app.test_request_context():
        seed_session()
        result = update_trait_tracker("char-1", "ct-1", TrackerRequest(action="set", current=3))

    # Then the stored state comes back
    assert result.current == 3


def test_update_health_sends_action_with_amount_one(app, fake_vclient) -> None:
    """Verify a health action reaches the API and returns the stored health."""
    # Given the API stores one point of damage
    fake_vclient.set_response(
        Routes.CHARACTERS_HEALTH_ACTION, model=HealthFactory.build(size=5, damage=1, levels=None)
    )

    # When damaging health
    with app.test_request_context():
        seed_session()
        result = update_health("char-1", TrackerRequest(action="damage", current=None))

    # Then one point of damage is sent and the stored health comes back
    fake_vclient.assert_called(
        Routes.CHARACTERS_HEALTH_ACTION,
        params={"character_id": "char-1"},
        json={"action": "damage", "amount": 1},
        times=1,
    )
    assert result.damage == 1
